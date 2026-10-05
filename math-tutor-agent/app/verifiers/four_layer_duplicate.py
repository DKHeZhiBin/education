from __future__ import annotations

import ast
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from app.domain.duplicate_detection import (
    DuplicateDetectionContext,
    DuplicateDetectionReport,
    DuplicateDetectionStatus,
    DuplicateLayerResult,
    DuplicateMatch,
    DuplicateProblemSnapshot,
)


MAX_EXPRESSION_LENGTH = 1000


@dataclass(frozen=True)
class DuplicateDetectionPolicy:
    near_composite_threshold: float = 0.94
    near_text_threshold: float = 0.92
    near_formula_threshold: float = 0.90
    near_condition_threshold: float = 0.90
    maximum_reported_matches: int = 20


@dataclass(frozen=True)
class LayerSignature:
    canonical: str | None
    fingerprint: str | None
    features: frozenset[str]

    @property
    def available(self) -> bool:
        return self.canonical is not None


class FourLayerDuplicateDetector:
    """Compare text, formula AST, condition structure, and solution structure."""

    name = "four_layer_duplicate"
    schema_version = "1.0"

    def __init__(self, policy: DuplicateDetectionPolicy | None = None) -> None:
        self.policy = policy or DuplicateDetectionPolicy()

    def detect(self, context: DuplicateDetectionContext) -> DuplicateDetectionReport:
        candidate_signatures = self._signatures(context.candidate)
        matches = [
            self._compare(context.candidate, reference, candidate_signatures)
            for reference in context.references
        ]
        matches.sort(key=lambda item: (
            0 if item.classification == "exact_duplicate" else
            1 if item.classification == "near_duplicate" else 2,
            -item.composite_similarity,
            item.reference_problem_id,
        ))
        exact_count = sum(item.classification == "exact_duplicate" for item in matches)
        near_count = sum(item.classification == "near_duplicate" for item in matches)
        limitations: list[str] = []
        if not context.comparison_scope_complete:
            limitations.append(
                "同题型比较池超过单次扫描上限，当前结果不能证明不存在重复题"
            )
        if not candidate_signatures["formula_ast"].available:
            limitations.append("候选题缺少可安全解析的规范公式 AST")
        if not candidate_signatures["condition"].available:
            limitations.append("候选题缺少可比较的结构化条件或目标")
        if not candidate_signatures["solution_structure"].available:
            limitations.append("候选题缺少可比较的结构化独立题解")

        if exact_count or near_count:
            status = DuplicateDetectionStatus.FAILED
            confidence = 0.99 if exact_count else 0.94
        elif limitations:
            status = DuplicateDetectionStatus.INCONCLUSIVE
            confidence = 0.45
        else:
            status = DuplicateDetectionStatus.PASSED
            confidence = 0.96
        reported = [
            item for item in matches
            if item.classification != "distinct"
        ][:self.policy.maximum_reported_matches]
        if not reported:
            reported = matches[:min(5, self.policy.maximum_reported_matches)]
        return DuplicateDetectionReport(
            problem_id=context.candidate.problem_id,
            solution_id=context.candidate.solution_id or "",
            context_fingerprint=context.fingerprint(),
            status=status,
            compared_count=len(context.references),
            comparison_scope_total=context.comparison_scope_total,
            comparison_scope_complete=context.comparison_scope_complete,
            exact_duplicate_count=exact_count,
            near_duplicate_count=near_count,
            matches=reported,
            thresholds={
                "near_composite": self.policy.near_composite_threshold,
                "near_text": self.policy.near_text_threshold,
                "near_formula": self.policy.near_formula_threshold,
                "near_condition": self.policy.near_condition_threshold,
            },
            limitations=limitations,
            confidence=confidence,
        )

    def _compare(
        self,
        candidate: DuplicateProblemSnapshot,
        reference: DuplicateProblemSnapshot,
        candidate_signatures: dict[str, LayerSignature],
    ) -> DuplicateMatch:
        reference_signatures = self._signatures(reference)
        layers: list[DuplicateLayerResult] = []
        similarities: dict[str, float] = {}
        exact: dict[str, bool] = {}
        for layer in ("text", "formula_ast", "condition", "solution_structure"):
            left = candidate_signatures[layer]
            right = reference_signatures[layer]
            available = left.available and right.available
            similarity = self._similarity(left, right) if available else 0.0
            is_exact = bool(available and left.fingerprint == right.fingerprint)
            similarities[layer] = similarity
            exact[layer] = is_exact
            layers.append(DuplicateLayerResult(
                layer=layer,
                available=available,
                exact=is_exact,
                similarity=similarity,
                candidate_fingerprint=left.fingerprint,
                reference_fingerprint=right.fingerprint,
                details={
                    "candidate_feature_count": len(left.features),
                    "reference_feature_count": len(right.features),
                },
            ))

        weights = {
            "text": 0.30,
            "formula_ast": 0.30,
            "condition": 0.25,
            "solution_structure": 0.15,
        }
        available_weight = sum(
            weights[layer] for layer in weights
            if candidate_signatures[layer].available and reference_signatures[layer].available
        )
        composite = (
            sum(similarities[layer] * weights[layer] for layer in weights) / available_weight
            if available_weight else 0.0
        )
        reasons: list[str] = []
        if candidate.content_hash == reference.content_hash:
            classification = "exact_duplicate"
            reasons.append("题目内容哈希完全相同")
        elif exact["text"] and exact["formula_ast"]:
            classification = "exact_duplicate"
            reasons.append("规范化题干与公式 AST 同时完全相同")
        elif exact["formula_ast"] and exact["condition"]:
            classification = "exact_duplicate"
            reasons.append("公式 AST 与条件目标结构同时相同")
        elif (
            composite >= self.policy.near_composite_threshold
            and similarities["text"] >= self.policy.near_text_threshold
            and similarities["formula_ast"] >= self.policy.near_formula_threshold
            and similarities["condition"] >= self.policy.near_condition_threshold
        ):
            classification = "near_duplicate"
            reasons.append("文本、公式和条件的联合相似度超过近重复门槛")
        else:
            classification = "distinct"
        if exact["solution_structure"]:
            reasons.append("解法步骤结构完全相同")
        relationship = (
            "mother" if reference.problem_id == candidate.mother_problem_id
            else "same_batch_peer"
            if candidate.generation_batch_id is not None
            and reference.generation_batch_id == candidate.generation_batch_id
            else "existing_problem"
        )
        return DuplicateMatch(
            reference_problem_id=reference.problem_id,
            reference_solution_id=reference.solution_id,
            relationship=relationship,
            classification=classification,
            composite_similarity=round(composite, 6),
            layers=layers,
            reasons=reasons,
        )

    def _signatures(
        self,
        snapshot: DuplicateProblemSnapshot,
    ) -> dict[str, LayerSignature]:
        return {
            "text": self._text_signature(snapshot),
            "formula_ast": self._formula_signature(snapshot),
            "condition": self._condition_signature(snapshot),
            "solution_structure": self._solution_signature(snapshot),
        }

    def _text_signature(self, snapshot: DuplicateProblemSnapshot) -> LayerSignature:
        text = self._normalize_text(snapshot.normalized_statement or snapshot.statement)
        if not text:
            return LayerSignature(None, None, frozenset())
        return self._signature(text, self._character_ngrams(text))

    def _formula_signature(self, snapshot: DuplicateProblemSnapshot) -> LayerSignature:
        expressions = [
            str(item.get("normalized_expression") or item.get("statement") or "").strip()
            for item in [*snapshot.explicit_conditions, *snapshot.implicit_conditions]
            if item.get("condition_type") in {"equation", "inequality"}
            and (item.get("normalized_expression") or item.get("statement"))
        ]
        canonical = [self._canonical_relation(item) for item in expressions]
        canonical = sorted(item for item in canonical if item)
        if not canonical:
            return LayerSignature(None, None, frozenset())
        joined = "||".join(canonical)
        features = set()
        for item in canonical:
            features.update(self._ast_features(item))
        return self._signature(joined, features)

    def _condition_signature(self, snapshot: DuplicateProblemSnapshot) -> LayerSignature:
        if not snapshot.target or not (
            snapshot.explicit_conditions or snapshot.implicit_conditions
        ):
            return LayerSignature(None, None, frozenset())
        symbols = self._condition_symbols(snapshot)
        conditions = []
        features: set[str] = set()
        for implicit, values in (
            (False, snapshot.explicit_conditions),
            (True, snapshot.implicit_conditions),
        ):
            for item in values:
                condition_type = str(item.get("condition_type") or "other")
                expression = str(
                    item.get("normalized_expression")
                    or (
                        item.get("statement")
                        if condition_type in {"equation", "inequality"}
                        else ""
                    )
                    or ""
                ).strip()
                normalized_expression = self._canonical_relation(expression) if expression else ""
                record = {
                    "implicit": implicit,
                    "type": condition_type,
                    "expression": normalized_expression,
                    "statement": (
                        "" if normalized_expression
                        else self._normalize_with_symbols(
                            str(item.get("statement") or ""), symbols
                        )
                    ),
                    "inference_basis": (
                        self._normalize_with_symbols(
                            str(item.get("inference_basis") or ""), symbols
                        )
                        if implicit else ""
                    ),
                    "symbols": sorted(self._canonical_symbols(item.get("related_symbols"))),
                }
                conditions.append(record)
                features.add(f"condition:{'implicit' if implicit else 'explicit'}:{condition_type}")
                if normalized_expression:
                    features.add(f"expression:{normalized_expression}")
        target = {
            "action": snapshot.target.get("action"),
            "expected_answer_type": snapshot.target.get("expected_answer_type"),
            "target_object": self._normalize_with_symbols(
                str(snapshot.target.get("target_object") or ""), symbols
            ),
            "constraints": sorted(
                self._normalize_with_symbols(str(item), symbols)
                for item in snapshot.target.get("constraints", [])
            ),
        }
        features.add(f"target_action:{target['action']}")
        features.add(f"answer_type:{target['expected_answer_type']}")
        features.add(f"target_object:{target['target_object']}")
        features.update(f"constraint:{item}" for item in target["constraints"])
        canonical = json.dumps(
            {"conditions": sorted(conditions, key=self._json_sort_key), "target": target},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._signature(canonical, features)

    def _solution_signature(self, snapshot: DuplicateProblemSnapshot) -> LayerSignature:
        if not snapshot.solution_id or not snapshot.solution_steps:
            return LayerSignature(None, None, frozenset())
        step_ids = {
            str(step.get("step_id")): position
            for position, step in enumerate(snapshot.solution_steps, start=1)
        }
        steps = []
        features: set[str] = set()
        for position, step in enumerate(snapshot.solution_steps, start=1):
            action = self._normalize_text(str(step.get("action") or ""))
            result = str(step.get("result") or "").strip()
            canonical_result = self._canonical_relation(result) or self._normalize_text(result)
            basis_types = sorted(
                str(item.get("basis_type") or "other")
                for item in step.get("justifications", [])
                if isinstance(item, dict)
            )
            dependencies = sorted(
                step_ids.get(str(item), 0)
                for item in step.get("depends_on_step_ids", [])
            )
            knowledge_codes = sorted(str(item) for item in step.get("knowledge_point_codes", []))
            record = {
                "position": position,
                "action": action,
                "result": canonical_result,
                "basis_types": basis_types,
                "dependencies": dependencies,
                "knowledge_codes": knowledge_codes,
            }
            steps.append(record)
            features.add(f"step:{position}:action:{action}")
            features.update(f"step:{position}:basis:{item}" for item in basis_types)
            features.update(f"step:{position}:dep:{item}" for item in dependencies)
            features.update(f"step:{position}:knowledge:{item}" for item in knowledge_codes)
            if canonical_result:
                features.add(f"step:{position}:result:{canonical_result}")
        canonical = json.dumps(
            {
                "method": self._normalize_text(snapshot.solution_method_name or ""),
                "steps": steps,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._signature(canonical, features)

    @classmethod
    def _canonical_relation(cls, value: str) -> str | None:
        try:
            value = cls._normalize_formula(value)
        except ValueError:
            return None
        operators = ["<=", ">=", "!=", "=", "<", ">"]
        operator = next((item for item in operators if value.count(item) == 1), None)
        if operator is None:
            try:
                return cls._canonical_ast(ast.parse(value, mode="eval").body, {})
            except (SyntaxError, ValueError):
                return None
        left, right = value.split(operator, maxsplit=1)
        try:
            names: dict[str, str] = {}
            sides = [
                cls._canonical_ast(ast.parse(item, mode="eval").body, names)
                for item in (left, right)
            ]
        except (SyntaxError, ValueError):
            return None
        if operator in {"=", "!="}:
            sides.sort()
        return f"{operator}({sides[0]},{sides[1]})"

    @classmethod
    def _canonical_ast(cls, node: ast.AST, names: dict[str, str]) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            try:
                number = Decimal(str(node.value)).normalize()
            except InvalidOperation as error:
                raise ValueError("invalid number") from error
            return f"n:{number}"
        if isinstance(node, ast.Name):
            if node.id == "sqrt":
                return "fn:sqrt"
            if node.id not in names:
                names[node.id] = f"v{len(names)}"
            return names[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operator = "+" if isinstance(node.op, ast.UAdd) else "-"
            return f"u{operator}({cls._canonical_ast(node.operand, names)})"
        if isinstance(node, ast.BinOp):
            operator = {
                ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^"
            }.get(type(node.op))
            if operator is None:
                raise ValueError("unsupported operator")
            if operator in {"+", "-"}:
                children = cls._flatten_additive(node, names)
                return f"+({','.join(sorted(children))})"
            if operator == "*":
                children = cls._flatten_commutative(node, type(node.op), names)
                return f"{operator}({','.join(sorted(children))})"
            return (
                f"{operator}({cls._canonical_ast(node.left, names)},"
                f"{cls._canonical_ast(node.right, names)})"
            )
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id != "sqrt"
                or len(node.args) != 1
                or node.keywords
            ):
                raise ValueError("unsupported function")
            return f"sqrt({cls._canonical_ast(node.args[0], names)})"
        raise ValueError("unsupported AST node")

    @classmethod
    def _flatten_commutative(
        cls,
        node: ast.AST,
        operator_type: type[ast.operator],
        names: dict[str, str],
    ) -> list[str]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, operator_type):
            return [
                *cls._flatten_commutative(node.left, operator_type, names),
                *cls._flatten_commutative(node.right, operator_type, names),
            ]
        return [cls._canonical_ast(node, names)]

    @classmethod
    def _flatten_additive(
        cls,
        node: ast.AST,
        names: dict[str, str],
        sign: int = 1,
    ) -> list[str]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return [
                *cls._flatten_additive(node.left, names, sign),
                *cls._flatten_additive(node.right, names, sign),
            ]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            return [
                *cls._flatten_additive(node.left, names, sign),
                *cls._flatten_additive(node.right, names, -sign),
            ]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return cls._flatten_additive(node.operand, names, -sign)
        prefix = "+" if sign > 0 else "-"
        return [f"{prefix}{cls._canonical_ast(node, names)}"]

    @staticmethod
    def _normalize_formula(value: str) -> str:
        if not value or len(value) > MAX_EXPRESSION_LENGTH:
            raise ValueError("formula empty or too long")
        normalized = unicodedata.normalize("NFKC", value).strip()
        normalized = (
            normalized.replace("−", "-").replace("–", "-")
            .replace("×", "*").replace("÷", "/").replace("^", "**")
            .replace("≥", ">=").replace("≤", "<=").replace("≠", "!=")
            .replace("√", "sqrt")
        )
        normalized = re.sub(r"sqrt([A-Za-z0-9.]+)", r"sqrt(\1)", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"(?<=\d)(?=[A-DF-Za-df-z(])", "*", normalized)
        normalized = re.sub(r"(?<=\))(?=[A-Za-z0-9(])", "*", normalized)
        normalized = re.sub(r"(?<!sqrt)(?<=[A-Za-z])(?=\()", "*", normalized)
        return normalized

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).lower()
        normalized = normalized.replace("−", "-").replace("–", "-")
        return "".join(
            character for character in normalized
            if not character.isspace()
            and not unicodedata.category(character).startswith(("P", "Z"))
        )

    @staticmethod
    def _canonical_symbols(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        mapping: dict[str, str] = {}
        result = []
        for raw in value:
            symbol = str(raw)
            mapping.setdefault(symbol, f"v{len(mapping)}")
            result.append(mapping[symbol])
        return result

    @classmethod
    def _condition_symbols(cls, snapshot: DuplicateProblemSnapshot) -> list[str]:
        symbols: set[str] = set()
        for item in [*snapshot.explicit_conditions, *snapshot.implicit_conditions]:
            symbols.update(str(value) for value in item.get("related_symbols", []))
            expression = str(
                item.get("normalized_expression")
                or (
                    item.get("statement")
                    if item.get("condition_type") in {"equation", "inequality"}
                    else ""
                )
                or ""
            )
            symbols.update(
                value for value in re.findall(r"[A-Za-z][A-Za-z0-9_]*", expression)
                if value != "sqrt"
            )
        return sorted(symbols)

    @classmethod
    def _normalize_with_symbols(cls, value: str, symbols: list[str]) -> str:
        normalized = cls._normalize_text(value)
        for index, symbol in enumerate(symbols):
            normalized_symbol = cls._normalize_text(symbol)
            if not normalized_symbol:
                continue
            normalized = re.sub(
                rf"(?<![A-Za-z0-9_]){re.escape(normalized_symbol)}(?![A-Za-z0-9_])",
                f"v{index}",
                normalized,
            )
        return normalized

    @staticmethod
    def _character_ngrams(value: str, size: int = 3) -> set[str]:
        if len(value) <= size:
            return {value} if value else set()
        return {value[index:index + size] for index in range(len(value) - size + 1)}

    @staticmethod
    def _ast_features(canonical: str) -> set[str]:
        tokens = re.findall(r"(?:sqrt|fn|v\d+|n:[^,()]+|[+*/^!=-])", canonical)
        counts = Counter(tokens)
        return {f"{token}:{count}" for token, count in counts.items()}

    @staticmethod
    def _signature(canonical: str, features: set[str]) -> LayerSignature:
        fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
        return LayerSignature(canonical, fingerprint, frozenset(features))

    @staticmethod
    def _similarity(left: LayerSignature, right: LayerSignature) -> float:
        if left.fingerprint == right.fingerprint:
            return 1.0
        union = left.features | right.features
        if not union:
            return 0.0
        return len(left.features & right.features) / len(union)

    @staticmethod
    def _json_sort_key(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
