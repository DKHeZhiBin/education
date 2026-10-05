from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import sympy as sp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp_tools.math_tools import compare_math_steps, solve_equation
from app.mcp_tools.safe_math import parse_equation
from app.models.generation import AdmissionEvidence, GenerationBatch, VerifierVersion
from app.models.knowledge import (
    CurriculumVersion,
    DocumentChunk,
    KnowledgeDocument,
    KnowledgeProblem,
    KnowledgeSolution,
    SourceReference,
)
from app.models.learning import KnowledgePoint
from app.repositories.teaching_content import TeachingContentRepository
from app.problem_bank.schemas import (
    TrustedMotherProblemDataset,
    TrustedMotherProblemSeed,
)


PROJECT_ROOT = Path(__file__).parents[2]
DEFAULT_SEED_PATH = Path(__file__).parent / "data" / "trusted_quadratic_mothers.v1.json"
DEFAULT_SOURCE_REGISTRY_PATH = PROJECT_ROOT / "rag" / "sources" / "source_registry_v1.json"
DEFAULT_LICENSE_EVIDENCE_DIR = PROJECT_ROOT / "rag" / "sources" / "evidence"
DEFAULT_EVALUATION_PATH = PROJECT_ROOT / "evals" / "data" / "high_difficulty_v1.jsonl"
SAFE_MATH_PATH = PROJECT_ROOT / "app" / "mcp_tools" / "safe_math.py"
MATH_TOOLS_PATH = PROJECT_ROOT / "app" / "mcp_tools" / "math_tools.py"

ALLOWED_RIGHTS_STATUSES = {"approved_with_obligations", "approved_with_file_audit"}


class TrustedSeedValidationError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedSeedProblem:
    seed: TrustedMotherProblemSeed
    solutions: list[str]
    standard_form: str
    discriminant: str


@dataclass(frozen=True)
class TrustedSeedValidationSummary:
    dataset_id: str
    version: str
    source_registry_id: str
    verified_problems: int
    evaluation_hashes_checked: int


@dataclass(frozen=True)
class TrustedSeedImportSummary:
    dataset_id: str
    version: str
    source_reference_id: str
    document_id: str
    generation_batch_id: str
    verifier_version_id: str
    problem_count: int
    solution_count: int
    evidence_count: int
    content_status: str = "candidate"


def load_trusted_seed(path: str | Path = DEFAULT_SEED_PATH) -> TrustedMotherProblemDataset:
    with Path(path).open(encoding="utf-8") as seed_file:
        return TrustedMotherProblemDataset.model_validate(json.load(seed_file))


def validate_trusted_seed(
    dataset: TrustedMotherProblemDataset,
    *,
    source_registry_path: str | Path = DEFAULT_SOURCE_REGISTRY_PATH,
    evaluation_path: str | Path = DEFAULT_EVALUATION_PATH,
) -> tuple[TrustedSeedValidationSummary, list[VerifiedSeedProblem]]:
    registry_entry = _source_registry_entry(dataset.source.registry_id, source_registry_path)
    if registry_entry.get("rights_status") not in ALLOWED_RIGHTS_STATUSES:
        raise TrustedSeedValidationError(
            f"source {dataset.source.registry_id} is not approved for content ingestion"
        )
    if registry_entry.get("license") != dataset.source.license_name:
        raise TrustedSeedValidationError("seed license does not match the source allowlist")
    if str(registry_entry.get("license_url")) != str(dataset.source.license_url):
        raise TrustedSeedValidationError(
            "seed license URL does not match the source allowlist"
        )
    if str(registry_entry.get("canonical_url")) != str(dataset.source.canonical_url):
        raise TrustedSeedValidationError("seed canonical URL does not match the source allowlist")
    if str(registry_entry.get("license_evidence_url")) != str(
        dataset.source.license_evidence_url
    ):
        raise TrustedSeedValidationError(
            "seed license evidence URL does not match the source allowlist"
        )
    if str(dataset.source.content_url) not in registry_entry.get("approved_content_urls", []):
        raise TrustedSeedValidationError(
            "seed content URL is not approved by the source allowlist"
        )
    if registry_entry.get("attribution_template") != dataset.source.attribution:
        raise TrustedSeedValidationError(
            "seed attribution does not match the source allowlist"
        )
    _license_evidence(dataset)

    evaluation_hashes = _evaluation_hashes(evaluation_path)
    verified: list[VerifiedSeedProblem] = []
    content_hashes: set[str] = set()
    for seed in dataset.problems:
        verified_problem = _verify_problem(seed)
        content_hash = _problem_content_hash(seed.equation, seed.variable)
        if content_hash in content_hashes:
            raise TrustedSeedValidationError(
                f"duplicate normalized equation in seed: {seed.external_id}"
            )
        content_hashes.add(content_hash)
        candidate_hashes = {
            _normalized_text_hash(seed.original_statement),
            _normalized_text_hash(seed.statement_zh),
            _normalized_text_hash(seed.equation),
        }
        if candidate_hashes & evaluation_hashes:
            raise TrustedSeedValidationError(
                f"evaluation leakage detected for {seed.external_id}"
            )
        verified.append(verified_problem)

    return (
        TrustedSeedValidationSummary(
            dataset_id=dataset.dataset_id,
            version=dataset.version,
            source_registry_id=dataset.source.registry_id,
            verified_problems=len(verified),
            evaluation_hashes_checked=len(evaluation_hashes),
        ),
        verified,
    )


def import_trusted_seed(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    *,
    source_registry_path: str | Path = DEFAULT_SOURCE_REGISTRY_PATH,
    evaluation_path: str | Path = DEFAULT_EVALUATION_PATH,
) -> TrustedSeedImportSummary:
    _, verified = validate_trusted_seed(
        dataset,
        source_registry_path=source_registry_path,
        evaluation_path=evaluation_path,
    )
    _require_knowledge_points(session, dataset)
    imported_at = _utc_naive_now()
    source = _upsert_source(session, dataset)
    curriculum_version = _upsert_curriculum_version(session, dataset, source)
    document = _upsert_document(session, dataset, source, curriculum_version)
    verifier = _upsert_verifier(session, dataset)
    batch = _upsert_batch(session, dataset, imported_at)
    chunks = _upsert_chunks(session, dataset, document)

    problem_count = 0
    solution_count = 0
    evidence_count = 0
    for ordinal, verified_problem in enumerate(verified):
        seed = verified_problem.seed
        problem = _upsert_problem(
            session,
            dataset,
            seed,
            source,
            document,
            chunks[ordinal],
            batch,
        )
        solution = _upsert_solution(session, seed, verified_problem, problem, source)
        evidence_count += _upsert_evidence(
            session,
            dataset,
            seed,
            verified_problem,
            problem,
            solution,
            batch,
            verifier,
        )
        problem_count += 1
        solution_count += 1

    batch.requested_count = len(dataset.problems)
    batch.generated_count = len(dataset.problems)
    if batch.finished_at is None:
        batch.approved_count = 0
        batch.quarantined_count = 0
        batch.failed_count = 0
        batch.status = "completed"
        batch.finished_at = imported_at
    session.flush()
    return TrustedSeedImportSummary(
        dataset_id=dataset.dataset_id,
        version=dataset.version,
        source_reference_id=source.id,
        document_id=document.id,
        generation_batch_id=batch.id,
        verifier_version_id=verifier.id,
        problem_count=problem_count,
        solution_count=solution_count,
        evidence_count=evidence_count,
    )


def _verify_problem(seed: TrustedMotherProblemSeed) -> VerifiedSeedProblem:
    solved = solve_equation(seed.equation, seed.variable)
    if not solved.ok:
        raise TrustedSeedValidationError(
            f"SymPy could not solve {seed.external_id}: {solved.error}"
        )
    if not all(solved.verification):
        raise TrustedSeedValidationError(
            f"root substitution failed for {seed.external_id}"
        )
    if not _equivalent_solution_sets(
        solved.solutions,
        seed.expected_real_solutions,
    ):
        raise TrustedSeedValidationError(
            f"solution mismatch for {seed.external_id}: "
            f"expected {seed.expected_real_solutions}, got {solved.solutions}"
        )
    equivalence = compare_math_steps(seed.equation, seed.standard_form, seed.variable)
    if not equivalence.ok or not equivalence.equivalent:
        raise TrustedSeedValidationError(
            f"standard form is not equivalent for {seed.external_id}"
        )

    parsed = parse_equation(seed.standard_form)
    symbol = sp.Symbol(seed.variable, real=True)
    try:
        polynomial = sp.Poly(parsed.residual, symbol)
    except sp.PolynomialError as error:
        raise TrustedSeedValidationError(
            f"standard form is not a polynomial for {seed.external_id}"
        ) from error
    if polynomial.degree() != 2 or polynomial.LC() == 0:
        raise TrustedSeedValidationError(
            f"seed is not a quadratic equation: {seed.external_id}"
        )
    a, b, c = polynomial.all_coeffs()
    discriminant = sp.simplify(b**2 - 4 * a * c)
    return VerifiedSeedProblem(
        seed=seed,
        solutions=solved.solutions,
        standard_form=seed.standard_form,
        discriminant=sp.sstr(discriminant),
    )


def _equivalent_solution_sets(actual: list[str], expected: list[str]) -> bool:
    """Compare roots by symbolic value instead of SymPy's display form."""
    if len(actual) != len(expected):
        return False
    unmatched = [sp.sympify(value) for value in expected]
    for actual_value in map(sp.sympify, actual):
        for index, expected_value in enumerate(unmatched):
            if sp.simplify(actual_value - expected_value) == 0:
                unmatched.pop(index)
                break
        else:
            return False
    return not unmatched


def _source_registry_entry(registry_id: str, path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as registry_file:
        registry = json.load(registry_file)
    for source in registry.get("sources", []):
        if source.get("id") == registry_id:
            return source
    raise TrustedSeedValidationError(f"source is not allowlisted: {registry_id}")


def _license_evidence(dataset: TrustedMotherProblemDataset) -> dict[str, Any]:
    evidence_path = DEFAULT_LICENSE_EVIDENCE_DIR / f"{dataset.source.registry_id}.json"
    if not evidence_path.exists():
        raise TrustedSeedValidationError(
            f"license evidence snapshot is missing: {evidence_path}"
        )
    with evidence_path.open(encoding="utf-8") as evidence_file:
        evidence = json.load(evidence_file)
    expected = {
        "source_registry_id": dataset.source.registry_id,
        "license": dataset.source.license_name,
        "evidence_url": str(dataset.source.license_evidence_url),
    }
    mismatched = [key for key, value in expected.items() if evidence.get(key) != value]
    if mismatched:
        raise TrustedSeedValidationError(
            "license evidence does not match seed metadata: " + ", ".join(mismatched)
        )
    if evidence.get("captured_at", "") > dataset.source.accessed_at:
        raise TrustedSeedValidationError(
            "license evidence capture date cannot be after the seed access date"
        )
    return evidence


def _evaluation_hashes(path: str | Path) -> set[str]:
    hashes: set[str] = set()
    evaluation_path = Path(path)
    if not evaluation_path.exists():
        raise TrustedSeedValidationError(f"evaluation set is missing: {evaluation_path}")
    with evaluation_path.open(encoding="utf-8") as evaluation_file:
        for line in evaluation_file:
            if not line.strip():
                continue
            item = json.loads(line)
            problem = item.get("problem")
            if problem:
                hashes.add(_normalized_text_hash(problem))
    return hashes


def _require_knowledge_points(
    session: Session, dataset: TrustedMotherProblemDataset
) -> None:
    required = {
        code for problem in dataset.problems for code in problem.knowledge_point_codes
    }
    existing = set(session.scalars(
        select(KnowledgePoint.code).where(KnowledgePoint.code.in_(sorted(required)))
    ))
    missing = sorted(required - existing)
    if missing:
        raise TrustedSeedValidationError(
            "curriculum catalog must be imported first; missing knowledge points: "
            + ", ".join(missing)
        )


def _upsert_source(
    session: Session,
    dataset: TrustedMotherProblemDataset,
) -> SourceReference:
    source_seed = dataset.source
    license_evidence_hash = _hash_json(_license_evidence(dataset))
    fingerprint = _hash_json({
        "registry_id": source_seed.registry_id,
        "edition": source_seed.edition,
        "content_url": str(source_seed.content_url),
        "license": source_seed.license_name,
    })
    source = session.scalar(
        select(SourceReference).where(SourceReference.fingerprint == fingerprint)
    )
    if source is None:
        source = SourceReference(fingerprint=fingerprint)
        session.add(source)
    source.source_type = "textbook"
    source.title = source_seed.title
    source.authors_json = ["Portland Community College Mathematics Faculty"]
    source.publisher = source_seed.publisher
    source.canonical_url = str(source_seed.canonical_url)
    source.external_id = f"{source_seed.registry_id}:edition-{source_seed.edition}"
    source.license_name = source_seed.license_name
    source.rights_note = (
        "Approved allowlist source under CC BY 4.0. Imported scope is limited to "
        "edition 2 public odd-numbered exercises; attribution and accessible math are "
        f"required. Evidence snapshot SHA-256: {license_evidence_hash}."
    )
    source.accessed_at = datetime.fromisoformat(source_seed.accessed_at)
    session.flush()
    return source


def _upsert_document(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    source: SourceReference,
    curriculum_version: CurriculumVersion,
) -> KnowledgeDocument:
    checksum = _hash_json([
        {
            "external_id": problem.external_id,
            "locator": problem.source_locator,
            "statement": problem.original_statement,
        }
        for problem in dataset.problems
    ])
    version_label = f"edition-{dataset.source.edition}-curated-{dataset.version}"
    document = session.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.source_reference_id == source.id,
        KnowledgeDocument.version_label == version_label,
        KnowledgeDocument.content_checksum == checksum,
    ))
    is_new = document is None
    if is_new:
        document = KnowledgeDocument(
            source_reference_id=source.id,
            document_key="orcca-ed2-section-7-2-trusted-seed",
            version_label=version_label,
            content_checksum=checksum,
        )
        session.add(document)
    document.document_key = "orcca-ed2-section-7-2-trusted-seed"
    document.curriculum_version_id = curriculum_version.id
    document.document_type = "problem_set"
    document.title = "ORCCA Edition 2 — Section 7.2 trusted quadratic mother problems"
    document.language = "en"
    document.subject = "math"
    document.grade_band = "middle"
    document.grade_codes_json = ["grade_9"]
    if is_new:
        document.review_status = "unreviewed"
        document.lifecycle_status = "draft"
        document.ingestion_status = "parsed"
    document.knowledge_point_codes_json = [dataset.topic_code]
    document.problem_types_json = ["quadratic_equation"]
    document.difficulty_factors_json = _dataset_difficulty_factors(dataset)
    document.content_types_json = ["problem_statement"]
    document.metadata_json = {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.version,
        "content_url": str(dataset.source.content_url),
        "license_url": str(dataset.source.license_url),
        "license_evidence_url": str(dataset.source.license_evidence_url),
        "license_evidence_snapshot_hash": _hash_json(_license_evidence(dataset)),
        "attribution": dataset.source.attribution,
        "accessed_at": dataset.source.accessed_at,
        "curation": "Selected odd-numbered public exercises with deterministic solutions.",
    }
    session.flush()
    return document


def _upsert_curriculum_version(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    source: SourceReference,
) -> CurriculumVersion:
    version_code = f"edition-{dataset.source.edition}"
    version = session.scalar(select(CurriculumVersion).where(
        CurriculumVersion.authority == dataset.source.publisher,
        CurriculumVersion.region_code == "US",
        CurriculumVersion.subject == "math",
        CurriculumVersion.grade_band == "middle",
        CurriculumVersion.version_code == version_code,
    ))
    if version is None:
        version = CurriculumVersion(
            source_reference_id=source.id,
            authority=dataset.source.publisher,
            region_code="US",
            subject="math",
            grade_band="middle",
            name=f"{dataset.source.title}, Edition {dataset.source.edition}",
            version_code=version_code,
            status="active",
        )
        session.add(version)
    session.flush()
    return version


def _upsert_verifier(
    session: Session, dataset: TrustedMotherProblemDataset
) -> VerifierVersion:
    verifier = session.scalar(select(VerifierVersion).where(
        VerifierVersion.verifier_key == dataset.verifier_key,
        VerifierVersion.version == dataset.verifier_version,
    ))
    implementation_hash = sha256(
        SAFE_MATH_PATH.read_bytes()
        + MATH_TOOLS_PATH.read_bytes()
        + Path(__file__).read_bytes()
    ).hexdigest()
    ruleset_hash = _hash_json({
        "schema_version": dataset.schema_version,
        "domain": "real_quadratic_equations",
        "checks": ["degree", "solution_set", "candidate_substitution", "standard_form"],
    })
    if verifier is None:
        verifier = VerifierVersion(
            verifier_key=dataset.verifier_key,
            version=dataset.verifier_version,
            implementation_hash=implementation_hash,
            ruleset_hash=ruleset_hash,
        )
        session.add(verifier)
    elif (
        verifier.implementation_hash != implementation_hash
        or verifier.ruleset_hash != ruleset_hash
    ):
        raise TrustedSeedValidationError(
            "verifier code changed without a verifier version bump"
        )
    verifier.supported_problem_types_json = ["quadratic_equation"]
    verifier.config_json = {"domain": "reals", "require_finite_set": True}
    verifier.active = True
    session.flush()
    return verifier


def _upsert_batch(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    imported_at: datetime,
) -> GenerationBatch:
    batch = session.scalar(
        select(GenerationBatch).where(GenerationBatch.batch_key == dataset.batch_key)
    )
    if batch is None:
        batch = GenerationBatch(
            batch_key=dataset.batch_key,
            purpose="trusted_source_import",
            requested_count=len(dataset.problems),
            started_at=imported_at,
        )
        session.add(batch)
    batch.subject = "math"
    batch.grade_band = "middle"
    batch.topic_code = dataset.topic_code
    batch.config_json = {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.version,
        "source_registry_id": dataset.source.registry_id,
        "automatic_approval": False,
    }
    session.flush()
    return batch


def _upsert_chunks(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    document: KnowledgeDocument,
) -> list[DocumentChunk]:
    existing = {
        chunk.ordinal: chunk
        for chunk in session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
    }
    chunks: list[DocumentChunk] = []
    for ordinal, seed in enumerate(dataset.problems):
        content_hash = sha256(seed.original_statement.encode("utf-8")).hexdigest()
        chunk = existing.get(ordinal)
        is_new = chunk is None
        if is_new:
            chunk = DocumentChunk(document_id=document.id, ordinal=ordinal)
            session.add(chunk)
        chunk.content = seed.original_statement
        chunk.content_hash = content_hash
        chunk.token_count = max(1, len(re.findall(r"[A-Za-z0-9]+", seed.original_statement)))
        chunk.heading_path_json = ["Section 7.2", "Exercises 7.2.3"]
        chunk.locator = seed.source_locator
        chunk.content_type = "problem_statement"
        chunk.curriculum_version_id = document.curriculum_version_id
        chunk.grade_band = document.grade_band
        chunk.grade_codes_json = list(document.grade_codes_json)
        chunk.knowledge_point_codes_json = seed.knowledge_point_codes
        chunk.problem_types_json = ["quadratic_equation"]
        chunk.difficulty_factors_json = [_difficulty_factor(seed)]
        chunk.metadata_json = {
            "external_id": seed.external_id,
            "content_url": str(dataset.source.content_url),
        }
        if is_new:
            chunk.enabled = True
        chunks.append(chunk)
    session.flush()
    return chunks


def _upsert_problem(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    seed: TrustedMotherProblemSeed,
    source: SourceReference,
    document: KnowledgeDocument,
    chunk: DocumentChunk,
    batch: GenerationBatch,
) -> KnowledgeProblem:
    content_hash = _problem_content_hash(seed.equation, seed.variable)
    duplicate = session.scalar(select(KnowledgeProblem).where(
        KnowledgeProblem.content_hash == content_hash,
        KnowledgeProblem.source_reference_id != source.id,
    ))
    if duplicate is not None:
        raise TrustedSeedValidationError(
            f"cross-source duplicate exists for {seed.external_id}: {duplicate.id}"
        )
    problem = session.scalar(select(KnowledgeProblem).where(
        KnowledgeProblem.source_reference_id == source.id,
        KnowledgeProblem.external_id == seed.external_id,
    ))
    if problem is None:
        problem = KnowledgeProblem(
            source_reference_id=source.id,
            external_id=seed.external_id,
            statement=seed.statement_zh,
            problem_type="quadratic_equation",
            difficulty=seed.difficulty,
            content_hash=content_hash,
        )
        session.add(problem)
    elif problem.content_status != "candidate":
        if problem.content_hash != content_hash:
            raise TrustedSeedValidationError(
                f"cannot replace admitted problem content: {seed.external_id}"
            )
        problem.document_id = document.id
        problem.source_chunk_id = chunk.id
        problem.curriculum_version_id = document.curriculum_version_id
        problem.grade_band = "middle"
        problem.grade_codes_json = list(document.grade_codes_json)
        problem.problem_type = "quadratic_equation"
        problem.content_type = "problem"
        problem.difficulty = seed.difficulty
        problem.knowledge_point_codes_json = seed.knowledge_point_codes
        problem.difficulty_factors_json = [_difficulty_factor(seed)]
        session.flush()
        return problem
    problem.document_id = document.id
    problem.curriculum_version_id = document.curriculum_version_id
    problem.source_chunk_id = chunk.id
    problem.generation_batch_id = batch.id
    problem.statement = seed.statement_zh
    problem.normalized_statement = seed.equation
    problem.subject = "math"
    problem.grade_band = "middle"
    problem.grade_codes_json = list(document.grade_codes_json)
    problem.problem_type = "quadratic_equation"
    problem.content_type = "problem"
    problem.difficulty = seed.difficulty
    problem.answer_type = "real_solution_set"
    problem.language = "zh-CN"
    problem.content_hash = content_hash
    problem.review_status = "unreviewed"
    problem.explicit_conditions_json = [{
        "statement": seed.equation,
        "condition_type": "equation",
        "normalized_expression": seed.equation,
        "related_symbols": [seed.variable],
    }]
    problem.implicit_conditions_json = [{
        "statement": f"{seed.variable} 为实数",
        "condition_type": "domain",
        "normalized_expression": f"{seed.variable} in Reals",
        "related_symbols": [seed.variable],
        "inference_basis": "题干明确要求在实数范围内求解",
        "confidence": 1.0,
    }]
    problem.target_json = {
        "action": "solve",
        "target_object": seed.equation,
        "expected_answer_type": "real_solution_set",
        "constraints": ["实数范围", "列出全部实数根"],
    }
    problem.difficulty_factors_json = [_difficulty_factor(seed)]
    problem.knowledge_point_codes_json = seed.knowledge_point_codes
    problem.metadata_json = {
        "trusted_mother": True,
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.version,
        "source_locator": seed.source_locator,
        "source_statement": seed.original_statement,
        "translation_note": "Chinese wording added; mathematical expression unchanged.",
        "license": dataset.source.license_name,
        "attribution": dataset.source.attribution,
    }
    if problem.content_status == "candidate":
        problem.status_reason = None
    session.flush()
    return problem


def _upsert_solution(
    session: Session,
    seed: TrustedMotherProblemSeed,
    verified: VerifiedSeedProblem,
    problem: KnowledgeProblem,
    source: SourceReference,
) -> KnowledgeSolution:
    final_answer = _solution_set_text(verified.solutions)
    solution_text = (
        f"将方程整理为 {verified.standard_form}。"
        f"判别式为 {verified.discriminant}。"
        f"在实数范围内得到{final_answer}，并将全部候选根代回原方程验证。"
    )
    content_hash = sha256(
        f"{problem.content_hash}|{seed.method}|{final_answer}".encode("utf-8")
    ).hexdigest()
    solution = session.scalar(select(KnowledgeSolution).where(
        KnowledgeSolution.problem_id == problem.id,
        KnowledgeSolution.content_hash == content_hash,
    ))
    if solution is None:
        solution = KnowledgeSolution(
            problem_id=problem.id,
            source_reference_id=source.id,
            method_name=_method_name(seed.method),
            solution_text=solution_text,
            content_hash=content_hash,
        )
        session.add(solution)
    elif problem.content_status != "candidate":
        TeachingContentRepository.sync_solution_steps(session, solution)
        return solution
    solution.method_name = _method_name(seed.method)
    solution.solution_text = solution_text
    solution.final_answer = final_answer
    solution.review_status = "unreviewed"
    solution.verification_status = "verified"
    solution.steps_json = _solution_steps(seed, verified, final_answer)
    solution.key_breakthroughs_json = [{
        "breakthrough_id": "breakthrough-1",
        "title": "选择可完整校验的代数解法",
        "description": f"先化为标准形式，再使用{_method_name(seed.method)}得到完整实数解集。",
        "why_it_matters": "该路径可以同时检查根的正确性和解集完整性。",
        "related_step_ids": ["step-1", "step-2", "step-3"],
        "knowledge_point_codes": seed.knowledge_point_codes,
        "hint_question": "这个方程整理为一般形式后，哪个方法能稳定得到全部实数根？",
    }]
    solution.verification_coverage_json = {
        "level": "full",
        "covered_step_ids": ["step-1", "step-2", "step-3"],
        "uncovered_step_ids": [],
        "checks": [
            {
                "check_type": "symbolic_equivalence",
                "status": "passed",
                "verifier": "trusted_seed_sympy",
                "covered_step_ids": ["step-1", "step-2"],
                "evidence": "原方程与标准形式的实数解集一致，且标准形式为二次多项式。",
            },
            {
                "check_type": "candidate_substitution",
                "status": "passed",
                "verifier": "trusted_seed_sympy",
                "covered_step_ids": ["step-3"],
                "evidence": "SymPy 在实数域求得有限解集，并对每个返回根完成精确代回。",
            },
            {
                "check_type": "answer_completeness",
                "status": "passed",
                "verifier": "trusted_seed_sympy",
                "covered_step_ids": ["step-3"],
                "evidence": "最终答案与实数域 solveset 的完整有限解集一致。",
            },
        ],
        "limitations": [],
        "confidence": 1.0,
    }
    solution.is_preferred = True
    solution.language = "zh-CN"
    solution.metadata_json = {
        "solution_origin": "project_deterministic_derivation",
        "source_problem_locator": seed.source_locator,
        "programmatically_verified": True,
    }
    session.flush()
    TeachingContentRepository.sync_solution_steps(session, solution)
    return solution


def _upsert_evidence(
    session: Session,
    dataset: TrustedMotherProblemDataset,
    seed: TrustedMotherProblemSeed,
    verified: VerifiedSeedProblem,
    problem: KnowledgeProblem,
    solution: KnowledgeSolution,
    batch: GenerationBatch,
    verifier: VerifierVersion,
) -> int:
    evidence_specs = [
        ("source_rights_clearance", "system", "passed", True,
         "来源位于允许清单，固定为 ORCCA 第 2 版公开练习，许可证为 CC BY 4.0。",
         {"license": dataset.source.license_name, "license_url": str(dataset.source.license_url),
          "evidence_url": str(dataset.source.license_evidence_url), "locator": seed.source_locator}),
        ("condition_completeness", "system", "passed", True,
         "题目包含完整方程、实数定义域和求全部实数根的明确目标。",
         {"equation": seed.equation, "domain": "reals", "target": "complete_solution_set"}),
        ("solution_independence", "verifier", "passed", True,
         "答案由 SymPy 仅根据题目方程独立求得，未读取来源答案文本。",
         {"computed_solutions": verified.solutions}),
        ("symbolic_verification", "verifier", "passed", True,
         "原方程、标准形式和实数域解集已完成符号校验。",
         {"standard_form": verified.standard_form, "discriminant": verified.discriminant}),
        ("numeric_verification", "verifier", "passed", True,
         "全部候选根已完成精确代回，残差均为零。",
         {"solutions": verified.solutions, "verification": [True] * len(verified.solutions)}),
        ("constraint_verification", "verifier", "passed", True,
         "求解域固定为实数，返回结果与实数域有限解集一致。",
         {"domain": "reals", "solution_count": len(verified.solutions)}),
        ("duplicate_detection", "system", "passed", True,
         "数据包内规范方程唯一，写入前未发现其他来源的同哈希题目。",
         {"content_hash": problem.content_hash}),
        ("evaluation_leakage_detection", "system", "not_run", True,
         "尚未执行隔离评估集泄漏检测，不能用导入阶段的哈希检查代替正式检测。",
         {"required_next_step": "versioned_evaluation_leakage_detection"}),
        ("pedagogical_review", "system", "not_run", True,
         "尚未执行独立 AI 教学复核，因此题目保持 candidate，不能自动批准。",
         {"required_next_step": "independent_ai_pedagogical_review"}),
    ]
    created = 0
    for evidence_type, producer_type, status, is_blocking, summary, payload in evidence_specs:
        evidence_hash = _hash_json({
            "evidence_type": evidence_type,
            "status": status,
            "payload": payload,
            "verifier_version": dataset.verifier_version if producer_type == "verifier" else None,
        })
        existing = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == batch.id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == evidence_type,
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if existing is not None:
            continue
        session.add(AdmissionEvidence(
            generation_batch_id=batch.id,
            problem_id=problem.id,
            solution_id=solution.id if producer_type == "verifier" else None,
            evidence_type=evidence_type,
            producer_type=producer_type,
            status=status,
            verifier_version_id=verifier.id if producer_type == "verifier" else None,
            is_blocking=is_blocking,
            summary=summary,
            payload_json=payload,
            evidence_hash=evidence_hash,
        ))
        created += 1
    session.flush()
    return created


def _solution_steps(
    seed: TrustedMotherProblemSeed,
    verified: VerifiedSeedProblem,
    final_answer: str,
) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "step-1",
            "sequence": 1,
            "action": "把原方程整理为一元二次方程的一般形式",
            "result": verified.standard_form,
            "justifications": [{
                "basis_type": "algebraic_property",
                "statement": "对方程两边进行同解变形，并合并同类项。",
                "source_reference_id": None,
                "locator": None,
            }],
            "depends_on_step_ids": [],
            "condition_refs": ["explicit-condition-1"],
            "knowledge_point_codes": seed.knowledge_point_codes,
        },
        {
            "step_id": "step-2",
            "sequence": 2,
            "action": f"使用{_method_name(seed.method)}求出实数域候选解",
            "result": f"判别式 Δ={verified.discriminant}；{final_answer}",
            "justifications": [{
                "basis_type": "formula" if seed.method == "quadratic_formula" else "theorem",
                "statement": "所选方法在当前二次方程上给出完整候选解集。",
                "source_reference_id": None,
                "locator": seed.source_locator,
            }],
            "depends_on_step_ids": ["step-1"],
            "condition_refs": ["explicit-condition-1"],
            "knowledge_point_codes": seed.knowledge_point_codes,
        },
        {
            "step_id": "step-3",
            "sequence": 3,
            "action": "将候选根逐个代回原方程并核对解集完整性",
            "result": f"全部候选根代回成立；最终{final_answer}",
            "justifications": [{
                "basis_type": "calculation",
                "statement": "SymPy 实数域求解与精确代回结果一致。",
                "source_reference_id": None,
                "locator": None,
            }],
            "depends_on_step_ids": ["step-2"],
            "condition_refs": ["explicit-condition-1"],
            "knowledge_point_codes": seed.knowledge_point_codes,
        },
    ]


def _difficulty_factor(seed: TrustedMotherProblemSeed) -> dict[str, Any]:
    factor_type = "method_selection" if seed.method != "quadratic_formula" else "computational_complexity"
    return {
        "factor_type": factor_type,
        "level": seed.difficulty,
        "rationale": (
            "需要先识别方程结构并选择合适解法；含根式时还要保证化简与全部根完整。"
        ),
        "related_knowledge_codes": seed.knowledge_point_codes,
    }


def _dataset_difficulty_factors(
    dataset: TrustedMotherProblemDataset,
) -> list[dict[str, Any]]:
    by_type: dict[str, dict[str, Any]] = {}
    for seed in dataset.problems:
        factor = _difficulty_factor(seed)
        current = by_type.get(factor["factor_type"])
        if current is None or factor["level"] > current["level"]:
            by_type[factor["factor_type"]] = factor
    return [by_type[key] for key in sorted(by_type)]


def _method_name(method: str) -> str:
    return {
        "quadratic_formula": "求根公式",
        "direct_square_root": "直接开平方法",
        "factoring": "因式分解法",
    }[method]


def _solution_set_text(solutions: list[str]) -> str:
    return "实数解集为空" if not solutions else "解集为 {" + ", ".join(solutions) + "}"


def _problem_content_hash(equation: str, variable: str) -> str:
    parsed = parse_equation(equation)
    symbol = sp.Symbol(variable, real=True)
    try:
        polynomial = sp.Poly(sp.expand(parsed.residual), symbol)
    except sp.PolynomialError as error:
        raise TrustedSeedValidationError(
            f"equation cannot be normalized as a polynomial: {equation}"
        ) from error
    if polynomial.degree() != 2 or polynomial.LC() == 0:
        raise TrustedSeedValidationError(f"equation is not quadratic: {equation}")
    monic_expression = sp.expand(polynomial.as_expr() / polynomial.LC())
    canonical = sp.sstr(monic_expression)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _normalized_text_hash(value: str) -> str:
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    return sha256(normalized.encode("utf-8")).hexdigest()


def _hash_json(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
