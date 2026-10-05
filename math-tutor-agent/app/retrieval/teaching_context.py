from __future__ import annotations

from time import perf_counter
from typing import Any

from pydantic import ValidationError

from app.domain.knowledge import (
    KnowledgeQuery,
    RetrievalDiagnostics,
    RetrievedConcept,
    RetrievedErrorPattern,
    RetrievedHint,
    RetrievedPrinciple,
    RetrievedProblemPattern,
    RetrievedSolutionOutline,
    RetrievedSourceFact,
    RetrievedTeachingContext,
)
from app.domain.search_index import RankedTeachingCandidate


ENTITY_MODELS = {
    "concept": ("concepts", RetrievedConcept),
    "principle": ("principles", RetrievedPrinciple),
    "problem_pattern": ("problem_patterns", RetrievedProblemPattern),
    "solution_outline": ("solution_outlines", RetrievedSolutionOutline),
    "error_pattern": ("error_patterns", RetrievedErrorPattern),
    "hint": ("hints", RetrievedHint),
    "source_fact": ("source_facts", RetrievedSourceFact),
}

CATEGORY_LIMITS = {
    "concepts": 8,
    "principles": 8,
    "problem_patterns": 5,
    "solution_outlines": 3,
    "error_patterns": 6,
    "hints": 4,
    "source_facts": 8,
}

PURPOSE_ENTITIES = {
    "problem_understanding": ["concept", "principle", "problem_pattern"],
    "solution_analysis": [
        "concept",
        "principle",
        "problem_pattern",
        "solution_outline",
        "error_pattern",
    ],
    "hint_teaching": [
        "concept",
        "principle",
        "problem_pattern",
        "error_pattern",
        "hint",
    ],
    "source_lookup": ["source_fact"],
}


def allowed_entity_types(query: KnowledgeQuery) -> list[str]:
    entity_types = list(PURPOSE_ENTITIES[query.purpose])
    if query.purpose == "hint_teaching" and query.hint_level == 4:
        entity_types.append("solution_outline")
    return entity_types


def candidate_allowed(candidate: RankedTeachingCandidate, query: KnowledgeQuery) -> bool:
    payload = candidate.payload
    filters = query.filters
    if payload.index_status != "active" or payload.content_status not in {
        "approved",
        "indexed",
    }:
        return False
    if payload.evaluation_only or payload.entity_type not in allowed_entity_types(query):
        return False
    if payload.subject != filters.subject or payload.language != filters.language:
        return False
    if filters.grade_band and payload.grade_band != filters.grade_band:
        return False
    if filters.curriculum_version and (
        payload.curriculum_version != filters.curriculum_version
    ):
        return False
    if filters.curriculum_version_id and (
        payload.curriculum_version_id != filters.curriculum_version_id
    ):
        return False
    if filters.grade and filters.grade not in payload.grade_codes:
        return False
    if filters.grade_codes and not (
        set(filters.grade_codes) & set(payload.grade_codes)
    ):
        return False
    if not set(filters.knowledge_points).issubset(payload.knowledge_point_codes):
        return False
    for requested, actual in (
        (filters.problem_types, payload.problem_types),
        (filters.content_types, payload.content_types),
        (filters.difficulty_sources, payload.difficulty_sources),
    ):
        if requested and not set(requested) & set(actual):
            return False
    if filters.difficulty and str(filters.difficulty).isdigit():
        if payload.difficulty != int(filters.difficulty):
            return False
    if query.purpose == "hint_teaching":
        if payload.disclosure_level > (query.hint_level or 1):
            return False
        if payload.entity_type == "hint" and payload.hint_level != query.hint_level:
            return False
    return True


def build_teaching_context(
    *,
    provider: str,
    query: KnowledgeQuery,
    candidates: list[RankedTeachingCandidate],
    started: float,
    max_context_chars: int,
    candidate_count: int | None = None,
    limitations: list[str] | None = None,
) -> RetrievedTeachingContext:
    groups: dict[str, list[Any]] = {name: [] for name in CATEGORY_LIMITS}
    notes = list(limitations or [])
    invalid = 0
    truncated = False
    used_chars = 500
    seen: set[tuple[str, str]] = set()
    versions: set[str] = set()

    for candidate in candidates:
        identity = (candidate.entity_type, candidate.entity_id)
        if identity in seen:
            continue
        seen.add(identity)
        if not candidate_allowed(candidate, query):
            invalid += 1
            continue
        mapping = ENTITY_MODELS.get(candidate.entity_type)
        if mapping is None:
            invalid += 1
            continue
        group_name, domain_model = mapping
        try:
            item = domain_model.model_validate({
                **candidate.payload.teaching_object,
                "score": candidate.score,
                "citation": candidate.payload.citation.model_dump(mode="json"),
            })
        except (ValidationError, TypeError, ValueError):
            invalid += 1
            continue
        item_chars = len(item.model_dump_json())
        if (
            len(groups[group_name]) >= CATEGORY_LIMITS[group_name]
            or used_chars + item_chars > max_context_chars
        ):
            truncated = True
            continue
        groups[group_name].append(item)
        versions.add(candidate.payload.index_version)
        used_chars += item_chars
        if sum(len(group) for group in groups.values()) >= query.top_k:
            truncated = truncated or len(candidates) > query.top_k
            break

    if invalid:
        notes.append(f"discarded {invalid} malformed or disallowed retrieval candidates")
    if truncated:
        notes.append("results were trimmed to the teaching context budget")
    notes = list(dict.fromkeys(notes))[:8]
    selected_count = sum(len(group) for group in groups.values())
    status = "success" if selected_count else "no_results"
    if notes:
        status = "degraded"
    return RetrievedTeachingContext(
        status=status,
        provider=provider,
        query=query,
        **groups,
        limitations=notes,
        diagnostics=RetrievalDiagnostics(
            latency_ms=round((perf_counter() - started) * 1000),
            index_version=next(iter(versions)) if len(versions) == 1 else None,
            candidate_count=(
                len(candidates) if candidate_count is None else candidate_count
            ),
            selected_count=selected_count,
            truncated=truncated,
        ),
        max_context_chars=max_context_chars,
    )
