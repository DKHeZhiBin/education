from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from app.domain.knowledge import (
    KnowledgeCitation,
    RetrievedErrorPattern,
    RetrievedHint,
    RetrievedProblemPattern,
    RetrievedSolutionOutline,
    RetrievedSolutionStep,
    RetrievedSourceFact,
)
from app.domain.search_index import SearchProjection
from app.domain.vector_store import QdrantTeachingPayload, VerifierVersionPayload
from app.models.knowledge import (
    DocumentChunk,
    KnowledgeDocument,
    KnowledgeProblem,
    KnowledgeSolution,
)


class ProductionIndexProjector:
    """Builds validated, disclosure-aware search projections from approved ORM rows."""

    def __init__(self, *, embedding_model: str, index_version: str) -> None:
        if not embedding_model.strip():
            raise ValueError("EMBEDDING_MODEL is required for production indexing")
        self.embedding_model = embedding_model
        self.index_version = index_version

    def project_problem(self, problem: KnowledgeProblem) -> list[SearchProjection]:
        if problem.content_status != "approved":
            raise ValueError("only approved problems can be projected")
        citation = self._problem_citation(problem)
        projections = [self._problem_pattern(problem, citation)]
        projections.extend(
            self._solution_outline(problem, solution, citation)
            for solution in problem.solutions
            if solution.review_status == "approved"
            and solution.verification_status in {"partial", "verified"}
        )
        projections.extend(
            self._error_pattern(problem, link, citation)
            for link in problem.error_pattern_links
            if link.active and link.error_pattern.active and link.solution_step.active
        )
        projections.extend(
            self._hint(problem, hint, citation)
            for hint in problem.hint_blueprints
            if hint.active and hint.review_status == "approved"
        )
        return projections

    def project_document(self, document: KnowledgeDocument) -> list[SearchProjection]:
        if document.review_status != "approved" or document.lifecycle_status != "active":
            raise ValueError("only approved active documents can be projected")
        return [
            self._source_fact(document, chunk)
            for chunk in document.chunks
            if chunk.enabled
        ]

    def _problem_pattern(
        self,
        problem: KnowledgeProblem,
        citation: KnowledgeCitation,
    ) -> SearchProjection:
        conditions = [
            self._clip(str(item.get("statement", "")), 300)
            for item in [
                *(problem.explicit_conditions_json or []),
                *(problem.implicit_conditions_json or []),
            ]
            if str(item.get("statement", "")).strip()
        ][:10]
        target = problem.target_json or {}
        target_summary = self._join_text(
            [target.get("action"), target.get("target_object"), *target.get("constraints", [])],
            400,
        )
        methods = [
            solution.method_name
            for solution in problem.solutions
            if solution.review_status == "approved"
            and solution.verification_status in {"partial", "verified"}
        ][:5]
        difficulty_sources = self._difficulty_sources(problem.difficulty_factors_json)
        teaching = RetrievedProblemPattern(
            problem_id=problem.id,
            structure_summary=self._clip(
                problem.normalized_statement or problem.statement, 700
            ),
            condition_schema=conditions,
            target_schema=target_summary or self._clip(problem.statement, 400),
            method_names=methods,
            knowledge_point_codes=(problem.knowledge_point_codes_json or [])[:12],
            difficulty_factors=difficulty_sources[:8],
            disclosure_level=2 if methods else 1,
            score=0,
            citation=citation,
        )
        search_text = self._join_text([
            problem.statement,
            problem.normalized_statement,
            *conditions,
            target_summary,
            problem.problem_type,
            problem.content_type,
            *(problem.knowledge_point_codes_json or []),
            *difficulty_sources,
        ])
        return self._projection(
            entity_type="problem_pattern",
            entity_id=problem.id,
            problem=problem,
            search_text=search_text,
            source_hash=problem.content_hash,
            teaching=teaching,
            citation=citation,
            disclosure_level=teaching.disclosure_level,
        )

    def _solution_outline(
        self,
        problem: KnowledgeProblem,
        solution: Any,
        citation: KnowledgeCitation,
    ) -> SearchProjection:
        coverage = solution.verification_coverage_json or {}
        verification_level = (
            "full"
            if solution.verification_status == "verified"
            and coverage.get("level") == "full"
            and not coverage.get("uncovered_step_ids")
            else "partial"
        )
        steps = []
        for raw in (solution.steps_json or [])[:10]:
            justifications = [
                str(item.get("statement", "")).strip()
                for item in raw.get("justifications", [])
                if str(item.get("statement", "")).strip()
            ]
            steps.append(RetrievedSolutionStep(
                step_key=str(raw.get("step_id", raw.get("step_key", "step"))),
                sequence=int(raw.get("sequence", len(steps) + 1)),
                action_summary=self._clip(str(raw.get("action", "求解")), 600),
                justification_summary=self._join_text(justifications, 600)
                or "依据已验证的题解步骤",
                result_summary=self._clip(str(raw.get("result", "")), 700) or None,
            ))
        breakthroughs = [
            self._join_text([item.get("title"), item.get("description")], 300)
            for item in (solution.key_breakthroughs_json or [])[:5]
        ]
        breakthroughs = [item for item in breakthroughs if item]
        teaching = RetrievedSolutionOutline(
            solution_id=solution.id,
            problem_id=problem.id,
            method_name=solution.method_name,
            strategy_summary=self._clip(solution.solution_text, 800),
            key_breakthroughs=breakthroughs,
            steps=steps,
            final_answer=(
                self._clip(solution.final_answer or "", 700) or None
                if verification_level == "full"
                else None
            ),
            verification_level=verification_level,
            score=0,
            citation=citation,
        )
        search_text = self._join_text([
            problem.statement,
            solution.method_name,
            solution.solution_text,
            *breakthroughs,
            *(self._join_text([step.action_summary, step.justification_summary,
                               step.result_summary]) for step in steps),
        ])
        return self._projection(
            entity_type="solution_outline",
            entity_id=solution.id,
            problem=problem,
            search_text=search_text,
            source_hash=solution.content_hash,
            teaching=teaching,
            citation=citation,
            disclosure_level=4,
            solution=solution,
        )

    def _error_pattern(
        self,
        problem: KnowledgeProblem,
        link: Any,
        citation: KnowledgeCitation,
    ) -> SearchProjection:
        pattern = link.error_pattern
        signals = self._flatten_values(link.trigger_evidence_json)[:8]
        if not signals:
            signals = [self._clip(pattern.description, 300)]
        teaching = RetrievedErrorPattern(
            pattern_code=pattern.code,
            title=pattern.title,
            observable_signals=signals,
            diagnostic_question=self._clip(link.diagnostic_prompt, 500),
            remediation_goal=self._clip(link.remediation_goal, 600),
            related_step_key=link.solution_step.step_key,
            disclosure_level=2,
            score=0,
            citation=citation,
        )
        canonical = {
            "link_id": link.id,
            "pattern_code": pattern.code,
            "trigger": link.trigger_evidence_json,
            "diagnostic_prompt": link.diagnostic_prompt,
            "remediation_goal": link.remediation_goal,
            "step_hash": link.solution_step.content_hash,
        }
        return self._projection(
            entity_type="error_pattern",
            entity_id=link.id,
            problem=problem,
            search_text=self._join_text([
                problem.statement,
                pattern.title,
                pattern.description,
                *signals,
                link.diagnostic_prompt,
                link.remediation_goal,
            ]),
            source_hash=self._hash(canonical),
            teaching=teaching,
            citation=citation,
            disclosure_level=2,
            solution=self._solution(problem, link.solution_id),
        )

    def _hint(
        self,
        problem: KnowledgeProblem,
        hint: Any,
        citation: KnowledgeCitation,
    ) -> SearchProjection:
        teaching = RetrievedHint(
            hint_blueprint_id=hint.id,
            solution_id=hint.solution_id,
            solution_step_key=(hint.solution_step.step_key if hint.solution_step else None),
            error_pattern_code=(
                hint.problem_error_pattern.error_pattern.code
                if hint.problem_error_pattern else None
            ),
            hint_level=hint.hint_level,
            hint_stage=hint.hint_stage,
            content=self._clip(hint.content, 1000),
            understanding_check=self._clip(hint.understanding_check, 500),
            review_status="approved",
            score=0,
            citation=citation,
        )
        return self._projection(
            entity_type="hint",
            entity_id=hint.id,
            problem=problem,
            search_text=self._join_text([
                problem.statement,
                hint.content,
                hint.understanding_check,
                *(hint.knowledge_point_codes_json or []),
            ]),
            source_hash=hint.content_hash,
            teaching=teaching,
            citation=citation,
            disclosure_level=hint.hint_level,
            hint_level=hint.hint_level,
            knowledge_points=hint.knowledge_point_codes_json or None,
            content_types=["hint"],
            solution=self._solution(problem, hint.solution_id),
        )

    def _source_fact(
        self,
        document: KnowledgeDocument,
        chunk: DocumentChunk,
    ) -> SearchProjection:
        citation = KnowledgeCitation(
            source_reference_id=document.source_reference_id,
            document_id=document.id,
            chunk_id=chunk.id,
            title=document.title,
            version=document.version_label,
            source_url=document.source_reference.canonical_url,
            locator=chunk.locator,
        )
        fact_types = {
            "definition": "definition",
            "curriculum": "curriculum_requirement",
            "curriculum_standard": "curriculum_requirement",
            "theorem": "theorem",
            "formula": "formula",
        }
        teaching = RetrievedSourceFact(
            fact_type=fact_types.get(chunk.content_type, "other"),
            summary=self._clip(chunk.content, 800),
            score=0,
            citation=citation,
        )
        difficulty_sources = self._difficulty_sources(chunk.difficulty_factors_json)
        payload = QdrantTeachingPayload(
            index_status="staging",
            content_status="approved",
            entity_type="source_fact",
            entity_id=chunk.id,
            subject=document.subject,
            grade_band=chunk.grade_band or document.grade_band,
            grade_codes=chunk.grade_codes_json or document.grade_codes_json,
            knowledge_point_codes=(
                chunk.knowledge_point_codes_json or document.knowledge_point_codes_json
            ),
            problem_types=chunk.problem_types_json or document.problem_types_json,
            content_types=[chunk.content_type],
            difficulty_sources=difficulty_sources,
            curriculum_version=(
                document.curriculum_version.version_code
                if document.curriculum_version else None
            ),
            curriculum_version_id=(
                chunk.curriculum_version_id or document.curriculum_version_id
            ),
            language=document.language,
            disclosure_level=1,
            search_text=self._join_text([
                document.title,
                *chunk.heading_path_json,
                chunk.content,
                *(chunk.knowledge_point_codes_json or []),
            ]),
            teaching_object=teaching.model_dump(
                mode="json", exclude={"score", "citation"}
            ),
            citation=citation,
            source_content_hash=chunk.content_hash,
            embedding_model=self.embedding_model,
            index_version=self.index_version,
        )
        return SearchProjection(
            point_id=self._point_id("source_fact", chunk.id),
            document_id=document.id,
            chunk_id=chunk.id,
            payload=payload,
        )

    def _projection(
        self,
        *,
        entity_type: str,
        entity_id: str,
        problem: KnowledgeProblem,
        search_text: str,
        source_hash: str,
        teaching: Any,
        citation: KnowledgeCitation,
        disclosure_level: int,
        hint_level: int | None = None,
        knowledge_points: list[str] | None = None,
        content_types: list[str] | None = None,
        solution: KnowledgeSolution | None = None,
    ) -> SearchProjection:
        difficulty_sources = self._difficulty_sources(problem.difficulty_factors_json)
        coverage = (
            dict(solution.verification_coverage_json or {}) if solution else None
        )
        verifier_versions = self._verifier_versions(problem, solution)
        payload = QdrantTeachingPayload(
            index_status="staging",
            content_status="approved",
            entity_type=entity_type,
            entity_id=entity_id,
            subject=problem.subject,
            grade_band=problem.grade_band,
            grade_codes=problem.grade_codes_json,
            knowledge_point_codes=(
                knowledge_points or problem.knowledge_point_codes_json
            ),
            problem_types=[problem.problem_type],
            content_types=content_types or [problem.content_type],
            difficulty=problem.difficulty,
            difficulty_sources=difficulty_sources,
            curriculum_version=(
                problem.curriculum_version.version_code
                if problem.curriculum_version else None
            ),
            curriculum_version_id=problem.curriculum_version_id,
            language=problem.language,
            disclosure_level=disclosure_level,
            hint_level=hint_level,
            generation_batch_id=problem.generation_batch_id,
            verification_level=(coverage.get("level") if coverage else None),
            verification_coverage=coverage,
            verifier_version_ids=[
                item.verifier_version_id for item in verifier_versions
            ],
            verifier_versions=verifier_versions,
            search_text=search_text,
            teaching_object=teaching.model_dump(
                mode="json", exclude={"score", "citation"}
            ),
            citation=citation,
            source_content_hash=source_hash,
            embedding_model=self.embedding_model,
            index_version=self.index_version,
        )
        return SearchProjection(
            point_id=self._point_id(entity_type, entity_id),
            problem_id=problem.id,
            document_id=problem.document_id,
            chunk_id=problem.source_chunk_id,
            payload=payload,
        )

    @staticmethod
    def _problem_citation(problem: KnowledgeProblem) -> KnowledgeCitation:
        document = problem.document
        source = problem.source_reference
        return KnowledgeCitation(
            source_reference_id=problem.source_reference_id,
            document_id=(document.id if document else f"problem:{problem.id}"),
            chunk_id=problem.source_chunk_id,
            title=(document.title if document else source.title),
            version=(document.version_label if document else None),
            source_url=source.canonical_url,
            locator=(problem.source_chunk.locator if problem.source_chunk else None),
        )

    @staticmethod
    def _point_id(entity_type: str, entity_id: str):
        return uuid5(NAMESPACE_URL, f"math-tutor:{entity_type}:{entity_id}")

    @staticmethod
    def _hash(value: Any) -> str:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _join_text(cls, values: Iterable[Any], limit: int = 4000) -> str:
        text = "\n".join(
            str(value).strip() for value in values if value is not None and str(value).strip()
        )
        return cls._clip(text, limit)

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        return value.strip()[:limit]

    @classmethod
    def _flatten_values(cls, value: Any) -> list[str]:
        if isinstance(value, dict):
            result = []
            for nested in value.values():
                result.extend(cls._flatten_values(nested))
            return result
        if isinstance(value, list):
            result = []
            for nested in value:
                result.extend(cls._flatten_values(nested))
            return result
        if value is None or isinstance(value, bool):
            return []
        text = cls._clip(str(value), 300)
        return [text] if text else []

    @classmethod
    def _difficulty_sources(cls, factors: list[dict[str, Any]] | None) -> list[str]:
        return [
            cls._clip(str(item.get("factor_type", "other")), 120)
            for item in (factors or [])
        ]

    @staticmethod
    def _solution(
        problem: KnowledgeProblem,
        solution_id: str,
    ) -> KnowledgeSolution:
        solution = next(
            (item for item in problem.solutions if item.id == solution_id),
            None,
        )
        if solution is None:
            raise ValueError(
                "indexed teaching content references an unknown solution"
            )
        return solution

    @staticmethod
    def _verifier_versions(
        problem: KnowledgeProblem,
        solution: KnowledgeSolution | None,
    ) -> list[VerifierVersionPayload]:
        versions: dict[str, VerifierVersionPayload] = {}
        for evidence in problem.admission_evidence:
            if evidence.verifier_version is None:
                continue
            if solution is not None and evidence.solution_id != solution.id:
                continue
            verifier = evidence.verifier_version
            versions[verifier.id] = VerifierVersionPayload(
                verifier_version_id=verifier.id,
                verifier_key=verifier.verifier_key,
                version=verifier.version,
                implementation_hash=verifier.implementation_hash,
                ruleset_hash=verifier.ruleset_hash,
            )
        return [versions[key] for key in sorted(versions)]
