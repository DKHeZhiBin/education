from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from app.domain.evaluation_leakage import (
    EvaluationCaseSignature,
    EvaluationDatasetSignature,
    EvaluationLeakageContext,
    EvaluationLeakageMatch,
    EvaluationLeakageReport,
    EvaluationLeakageStatus,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "evals/data/high_difficulty_v1.jsonl"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "evals/data/high_difficulty_v1.manifest.json"
MATH_SPAN_PATTERN = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\[(.+?)\\\]|\\\((.+?)\\\)", re.S)
MATH_TOKEN_PATTERN = re.compile(
    r"\\[A-Za-z]+|\d+(?:\.\d+)?|[A-Za-z]+|[+\-*/^=<>]|[(){}\[\]_,|]"
)


@dataclass(frozen=True)
class LeakageDetectionPolicy:
    near_text_threshold: float = 0.92
    structural_formula_threshold: float = 0.97
    structural_numeric_threshold: float = 0.90
    structural_minimum_formula_tokens: int = 8
    combined_threshold: float = 0.90
    combined_minimum_text_similarity: float = 0.80
    maximum_reported_matches: int = 20


@dataclass(frozen=True)
class LeakageFeatures:
    normalized_text_hash: str
    text_features: frozenset[str]
    formula_features: frozenset[str]
    numeric_features: frozenset[str]
    formula_token_count: int


class LeakageFeatureExtractor:
    @classmethod
    def extract(cls, text: str, extra_formulae: list[str] | None = None) -> LeakageFeatures:
        normalized_text = cls._normalize_text(text)
        text_features = cls._character_ngrams(normalized_text)
        formulae = [
            next(value for value in match.groups() if value is not None)
            for match in MATH_SPAN_PATTERN.finditer(text)
        ]
        formulae.extend(extra_formulae or [])
        formula_tokens: list[list[str]] = []
        numeric_values: list[str] = []
        for formula in formulae:
            tokens = cls._formula_tokens(formula)
            if tokens:
                formula_tokens.append(tokens)
                numeric_values.extend(token[2:] for token in tokens if token.startswith("n:"))
        formula_features: set[str] = set()
        token_count = 0
        for tokens in formula_tokens:
            token_count += len(tokens)
            formula_features.update(cls._token_ngrams(tokens, 2))
            formula_features.update(f"u:{token}" for token in tokens)
        numbers = Counter(numeric_values)
        return LeakageFeatures(
            normalized_text_hash=sha256(normalized_text.encode("utf-8")).hexdigest(),
            text_features=frozenset(text_features),
            formula_features=frozenset(formula_features),
            numeric_features=frozenset(
                f"{number}:{count}" for number, count in numbers.items()
            ),
            formula_token_count=token_count,
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).lower()
        normalized = (
            normalized.replace("−", "-").replace("–", "-")
            .replace("\\left", "").replace("\\right", "")
            .replace("\\,", "").replace("\\!", "")
        )
        return "".join(
            character for character in normalized
            if not character.isspace()
            and not unicodedata.category(character).startswith(("P", "Z"))
        )

    @staticmethod
    def _character_ngrams(value: str, size: int = 4) -> set[str]:
        if len(value) <= size:
            return {value} if value else set()
        return {value[index:index + size] for index in range(len(value) - size + 1)}

    @staticmethod
    def _formula_tokens(value: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", value)
        normalized = (
            normalized.replace("−", "-").replace("–", "-")
            .replace("×", "*").replace("÷", "/")
            .replace("\\left", "").replace("\\right", "")
            .replace("\\cdot", "*").replace("\\times", "*")
        )
        raw_tokens = MATH_TOKEN_PATTERN.findall(normalized)
        names: dict[str, str] = {}
        tokens: list[str] = []
        retained_commands = {
            "frac", "sqrt", "mid", "nmid", "leq", "geq", "in", "sum",
            "prod", "binom", "gcd", "lcm", "mod", "equiv",
        }
        for raw in raw_tokens:
            if raw.startswith("\\"):
                command = raw[1:].lower()
                if command in retained_commands:
                    tokens.append(f"c:{command}")
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?", raw):
                tokens.append(f"n:{raw.lstrip('0') or '0'}")
                continue
            if re.fullmatch(r"[A-Za-z]+", raw):
                lowered = raw.lower()
                names.setdefault(lowered, f"v:{len(names)}")
                tokens.append(names[lowered])
                continue
            tokens.append(f"o:{raw}")
        return tokens

    @staticmethod
    def _token_ngrams(tokens: list[str], size: int) -> set[str]:
        if len(tokens) <= size:
            return {" ".join(tokens)} if tokens else set()
        return {
            " ".join(tokens[index:index + size])
            for index in range(len(tokens) - size + 1)
        }


class EvaluationDatasetSignatureLoader:
    """Load only evaluation question features and fail closed on integrity errors."""

    def __init__(
        self,
        *,
        dataset_path: str | Path = DEFAULT_DATASET_PATH,
        manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    ) -> None:
        self.dataset_path = Path(dataset_path)
        self.manifest_path = Path(manifest_path)

    def load(self) -> EvaluationDatasetSignature:
        errors: list[str] = []
        manifest: dict = {}
        if not self.manifest_path.is_file():
            errors.append("evaluation manifest is missing")
        else:
            try:
                loaded_manifest = json.loads(
                    self.manifest_path.read_text(encoding="utf-8")
                )
                if isinstance(loaded_manifest, dict):
                    manifest = loaded_manifest
                else:
                    errors.append("evaluation manifest must be an object")
            except (OSError, json.JSONDecodeError):
                errors.append("evaluation manifest is unreadable")
        raw = b""
        if not self.dataset_path.is_file():
            errors.append("evaluation dataset is missing")
        else:
            try:
                raw = self.dataset_path.read_bytes()
            except OSError:
                errors.append("evaluation dataset is unreadable")

        actual_hash = sha256(raw).hexdigest() if raw else None
        expected_hash = manifest.get("dataset_sha256")
        manifest_name = manifest.get("name")
        manifest_schema_version = manifest.get("schema_version")
        manifest_source_commit = manifest.get("source_commit")
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_hash
        ):
            errors.append("evaluation manifest dataset_sha256 is invalid")
        elif actual_hash != expected_hash:
            errors.append("evaluation dataset checksum mismatch")
        if not isinstance(manifest_name, str) or not manifest_name.strip():
            errors.append("evaluation manifest name is missing")
        if (
            not isinstance(manifest_source_commit, str)
            or not manifest_source_commit.strip()
        ):
            errors.append("evaluation manifest source_commit is missing")
        if manifest and manifest.get("evaluation_only") is not True:
            errors.append("evaluation manifest must be evaluation_only")
        if manifest_schema_version != "1.0":
            errors.append("unsupported evaluation manifest schema version")

        cases: list[EvaluationCaseSignature] = []
        seen_ids: set[str] = set()
        if raw:
            try:
                decoded_lines = raw.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                errors.append("evaluation dataset is not valid UTF-8")
                decoded_lines = []
            for line_number, raw_line in enumerate(decoded_lines, start=1):
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    errors.append(f"invalid evaluation case at line {line_number}")
                    continue
                if not isinstance(record, dict):
                    errors.append(f"invalid evaluation case at line {line_number}")
                    continue
                record.pop("reference_answer", None)
                record.pop("reference_solution", None)
                case_id = record.get("id")
                problem = record.get("problem")
                source = record.get("source")
                taxonomy = record.get("taxonomy")
                if (
                    not isinstance(case_id, str)
                    or not isinstance(problem, str)
                    or not problem.strip()
                    or record.get("evaluation_only") is not True
                    or not isinstance(source, dict)
                    or source.get("usage") != "evaluation_only"
                    or not isinstance(taxonomy, dict)
                    or not isinstance(taxonomy.get("source_label"), str)
                ):
                    errors.append(f"invalid evaluation case contract at line {line_number}")
                    continue
                if case_id in seen_ids:
                    errors.append(f"duplicate evaluation case id: {case_id}")
                    continue
                seen_ids.add(case_id)
                source_commit = source.get("source_commit")
                if not isinstance(source_commit, str) or not source_commit.strip():
                    errors.append(f"source commit missing for case {case_id}")
                elif source_commit != manifest_source_commit:
                    errors.append(f"source commit mismatch for case {case_id}")
                features = LeakageFeatureExtractor.extract(problem)
                cases.append(EvaluationCaseSignature(
                    case_id=case_id,
                    source_commit=str(source_commit or ""),
                    source_label=taxonomy["source_label"],
                    normalized_text_hash=features.normalized_text_hash,
                    text_features=sorted(features.text_features),
                    formula_features=sorted(features.formula_features),
                    numeric_features=sorted(features.numeric_features),
                    formula_token_count=features.formula_token_count,
                ))

        expected_count = manifest.get("case_count")
        if not isinstance(expected_count, int) or expected_count < 1:
            errors.append("evaluation manifest case_count is invalid")
        elif len(cases) != expected_count:
            errors.append("evaluation case count mismatch")
        selected_ids = manifest.get("selected_upstream_ids")
        if not isinstance(selected_ids, list) or not selected_ids:
            errors.append("evaluation manifest selected case ids are missing")
        else:
            expected_upstream = set(str(item) for item in selected_ids)
            actual_upstream = {
                case.case_id.removeprefix("mathodyssey_problem_").replace("_", "")
                for case in cases
            }
            normalized_expected = {
                item.removeprefix("Problem_").replace("_", "") for item in expected_upstream
            }
            if actual_upstream != normalized_expected:
                errors.append("evaluation selected case ids mismatch")
        ids_payload = json.dumps(sorted(seen_ids), separators=(",", ":"))
        return EvaluationDatasetSignature(
            name=manifest_name if isinstance(manifest_name, str) else None,
            schema_version=(
                manifest_schema_version
                if isinstance(manifest_schema_version, str)
                else None
            ),
            evaluation_only=manifest.get("evaluation_only") is True,
            source_commit=(
                manifest_source_commit
                if isinstance(manifest_source_commit, str)
                else None
            ),
            expected_sha256=expected_hash if isinstance(expected_hash, str) else None,
            actual_sha256=actual_hash,
            expected_case_count=expected_count if isinstance(expected_count, int) else None,
            selected_case_ids_hash=sha256(ids_payload.encode("utf-8")).hexdigest(),
            integrity_valid=not errors,
            validation_errors=list(dict.fromkeys(errors)),
            cases=cases,
        )


class EvaluationLeakageDetector:
    name = "evaluation_leakage"
    schema_version = "1.0"

    def __init__(self, policy: LeakageDetectionPolicy | None = None) -> None:
        self.policy = policy or LeakageDetectionPolicy()

    def detect(self, context: EvaluationLeakageContext) -> EvaluationLeakageReport:
        dataset = context.dataset
        if not dataset.integrity_valid:
            return self._inconclusive(context, dataset.validation_errors)
        if not dataset.cases:
            return self._inconclusive(context, ["evaluation dataset contains no cases"])
        formulae = [
            str(item.get("normalized_expression") or item.get("statement") or "")
            for item in [
                *context.candidate.explicit_conditions,
                *context.candidate.implicit_conditions,
            ]
            if item.get("condition_type") in {"equation", "inequality"}
        ]
        candidate = LeakageFeatureExtractor.extract(
            context.candidate.statement,
            formulae,
        )
        matches: list[EvaluationLeakageMatch] = []
        for case in dataset.cases:
            text_similarity = self._jaccard(
                candidate.text_features, frozenset(case.text_features)
            )
            formula_similarity = self._jaccard(
                candidate.formula_features, frozenset(case.formula_features)
            )
            numeric_similarity = self._jaccard(
                candidate.numeric_features, frozenset(case.numeric_features)
            )
            composite = (
                text_similarity * 0.55
                + formula_similarity * 0.35
                + numeric_similarity * 0.10
            )
            reasons: list[str] = []
            classification: str | None = None
            if candidate.normalized_text_hash == case.normalized_text_hash:
                classification = "exact_text"
                reasons.append("规范题干哈希与冻结评估题完全相同")
            elif text_similarity >= self.policy.near_text_threshold:
                classification = "near_text"
                reasons.append("规范题干字符特征超过近似泄漏门槛")
            elif (
                formula_similarity >= self.policy.structural_formula_threshold
                and numeric_similarity >= self.policy.structural_numeric_threshold
                and min(candidate.formula_token_count, case.formula_token_count)
                >= self.policy.structural_minimum_formula_tokens
            ):
                classification = "structural"
                reasons.append("公式与数值结构高度一致，疑似翻译或改写泄漏")
            elif (
                composite >= self.policy.combined_threshold
                and text_similarity >= self.policy.combined_minimum_text_similarity
            ):
                classification = "combined"
                reasons.append("文本、公式和数值联合分数超过泄漏门槛")
            if classification:
                matches.append(EvaluationLeakageMatch(
                    case_id=case.case_id,
                    source_commit=case.source_commit,
                    source_label=case.source_label,
                    classification=classification,
                    text_similarity=round(text_similarity, 6),
                    formula_similarity=round(formula_similarity, 6),
                    numeric_similarity=round(numeric_similarity, 6),
                    composite_similarity=round(composite, 6),
                    reasons=reasons,
                ))
        matches.sort(key=lambda item: (-item.composite_similarity, item.case_id))
        if matches:
            status = EvaluationLeakageStatus.FAILED
            confidence = 0.99 if any(
                item.classification == "exact_text" for item in matches
            ) else 0.95
        else:
            status = EvaluationLeakageStatus.PASSED
            confidence = 0.96
        return EvaluationLeakageReport(
            problem_id=context.candidate.problem_id,
            context_fingerprint=context.fingerprint(),
            status=status,
            dataset_name=dataset.name,
            dataset_sha256=dataset.actual_sha256,
            source_commit=dataset.source_commit,
            checked_case_count=len(dataset.cases),
            matches=matches[:self.policy.maximum_reported_matches],
            thresholds=self._thresholds(),
            confidence=confidence,
        )

    def _inconclusive(
        self,
        context: EvaluationLeakageContext,
        limitations: list[str],
    ) -> EvaluationLeakageReport:
        return EvaluationLeakageReport(
            problem_id=context.candidate.problem_id,
            context_fingerprint=context.fingerprint(),
            status=EvaluationLeakageStatus.INCONCLUSIVE,
            dataset_name=context.dataset.name,
            dataset_sha256=context.dataset.actual_sha256,
            source_commit=context.dataset.source_commit,
            checked_case_count=len(context.dataset.cases),
            thresholds=self._thresholds(),
            limitations=limitations or ["evaluation dataset integrity is unknown"],
            confidence=0.1,
        )

    def _thresholds(self) -> dict[str, float]:
        return {
            "near_text": self.policy.near_text_threshold,
            "structural_formula": self.policy.structural_formula_threshold,
            "structural_numeric": self.policy.structural_numeric_threshold,
            "structural_minimum_formula_tokens": float(
                self.policy.structural_minimum_formula_tokens
            ),
            "combined": self.policy.combined_threshold,
            "combined_minimum_text": self.policy.combined_minimum_text_similarity,
        }

    @staticmethod
    def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
        union = left | right
        if not union:
            return 0.0
        return len(left & right) / len(union)
