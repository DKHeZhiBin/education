from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, settings
from app.domain.knowledge import KnowledgeQuery
from app.domain.search_index import RankedTeachingCandidate


TOKEN_PATTERN = re.compile(
    r"[a-zA-Z_][a-zA-Z_0-9]*|\d+(?:\.\d+)?|[=<>≤≥+\-−×÷*/^()]|[\u3400-\u9fff]+"
)


@dataclass(frozen=True)
class CandidateStructure:
    conditions: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    solutions: tuple[str, ...] = ()


class StructuralCandidateReranker:
    """Deterministically compare problem conditions, target and solution shape."""

    def __init__(self, config: Settings = settings) -> None:
        self.weights = {
            "fusion": config.rag_rerank_fusion_weight,
            "condition": config.rag_rerank_condition_weight,
            "target": config.rag_rerank_target_weight,
            "solution": config.rag_rerank_solution_weight,
        }

    def rerank(
        self,
        query: KnowledgeQuery,
        candidates: list[RankedTeachingCandidate],
    ) -> list[RankedTeachingCandidate]:
        query_structure = query.problem_structure
        query_conditions = query_structure.condition_statements or [query.text]
        query_targets = (
            [query_structure.target_summary]
            if query_structure.target_summary else [query.text]
        )
        query_solutions = [
            *query_structure.solution_methods,
            *query_structure.solution_steps,
        ]

        reranked: list[RankedTeachingCandidate] = []
        for candidate in candidates:
            structure = self._candidate_structure(candidate)
            condition_score = self._similarity(
                query_conditions,
                list(structure.conditions),
            )
            target_score = self._similarity(
                query_targets,
                list(structure.targets),
            )
            solution_score = (
                self._similarity(query_solutions, list(structure.solutions))
                if query_solutions and structure.solutions else None
            )
            components = {
                "fusion": candidate.score,
                "condition": condition_score,
                "target": target_score,
                "solution": solution_score,
            }
            available = {
                key: value
                for key, value in components.items()
                if value is not None and self.weights[key] > 0
            }
            weight_sum = sum(self.weights[key] for key in available)
            final_score = (
                sum(
                    self.weights[key] * value
                    for key, value in available.items()
                ) / weight_sum
                if weight_sum else candidate.score
            )
            reranked.append(candidate.model_copy(update={
                "score": max(0.0, min(final_score, 1.0)),
                "fusion_score": candidate.score,
                "condition_score": condition_score,
                "target_score": target_score,
                "solution_structure_score": solution_score,
            }))

        return sorted(
            reranked,
            key=lambda item: (
                -item.score,
                -(item.fusion_score or 0),
                item.vector_rank or 10_000,
                item.keyword_rank or 10_000,
                item.entity_type,
                item.entity_id,
            ),
        )

    @staticmethod
    def _candidate_structure(
        candidate: RankedTeachingCandidate,
    ) -> CandidateStructure:
        payload = candidate.payload
        teaching = payload.teaching_object
        fallback = (payload.search_text,)
        if payload.entity_type == "problem_pattern":
            return CandidateStructure(
                conditions=tuple(
                    StructuralCandidateReranker._strings(
                        teaching.get("condition_schema")
                    )
                ) or fallback,
                targets=tuple(
                    StructuralCandidateReranker._strings(
                        teaching.get("target_schema")
                    )
                ) or fallback,
                solutions=tuple(
                    StructuralCandidateReranker._strings(
                        teaching.get("method_names")
                    )
                ),
            )
        if payload.entity_type == "solution_outline":
            step_texts = []
            for step in teaching.get("steps", []):
                if isinstance(step, dict):
                    step_texts.extend(StructuralCandidateReranker._strings([
                        step.get("action_summary"),
                        step.get("justification_summary"),
                        step.get("result_summary"),
                    ]))
            solutions = StructuralCandidateReranker._strings([
                teaching.get("method_name"),
                teaching.get("strategy_summary"),
                *StructuralCandidateReranker._strings(
                    teaching.get("key_breakthroughs")
                ),
                *step_texts,
            ])
            return CandidateStructure(
                conditions=fallback,
                targets=fallback,
                solutions=tuple(solutions),
            )
        return CandidateStructure(conditions=fallback, targets=fallback)

    @classmethod
    def _similarity(
        cls,
        left_values: list[str],
        right_values: list[str],
    ) -> float | None:
        left = cls._tokens(left_values)
        right = cls._tokens(right_values)
        if not left or not right:
            return None
        return (2 * len(left & right)) / (len(left) + len(right))

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, (list, tuple)):
            result: list[str] = []
            for item in value:
                result.extend(StructuralCandidateReranker._strings(item))
            return result
        return []

    @staticmethod
    def _tokens(values: list[str]) -> set[str]:
        tokens: set[str] = set()
        for value in values:
            normalized = unicodedata.normalize("NFKC", value).casefold()
            for token in TOKEN_PATTERN.findall(normalized):
                if re.fullmatch(r"[\u3400-\u9fff]+", token):
                    if len(token) == 1:
                        tokens.add(token)
                    else:
                        tokens.update(
                            token[index:index + 2]
                            for index in range(len(token) - 1)
                        )
                else:
                    tokens.add(token)
        return tokens
