from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generation import ModelVersion, PromptVersion, VerifierVersion
from app.prompts.independent_review import INDEPENDENT_REVIEW_PROMPT
from app.prompts.independent_solving import INDEPENDENT_SOLVING_PROMPT
from app.prompts.problem_condition_check import PROBLEM_CONDITION_CHECK_PROMPT
from app.prompts.question_variation import QUESTION_VARIATION_SAFETY_PROMPT


@dataclass(frozen=True)
class CandidateValidationVersions:
    """中文：定义“候选内容·验证·versions”类，封装该职责相关的数据与行为。
    English: Defines the candidate validation versions class and encapsulates data and behavior for that responsibility.
    """
    model_version_id: str
    condition_prompt_version_id: str
    solver_prompt_version_id: str
    review_prompt_version_id: str
    sympy_verifier_version_id: str
    numeric_verifier_version_id: str
    duplicate_verifier_version_id: str
    leakage_verifier_version_id: str


class ValidationVersionRegistry:
    """中文：定义“验证·version·registry”类，封装该职责相关的数据与行为。
    English: Defines the validation version registry class and encapsulates data and behavior for that responsibility.
    """
    PROFILE = "quadratic-v1"
    PROMPTS = (
        ("question-variation", "question_generation", QUESTION_VARIATION_SAFETY_PROMPT),
        ("problem-condition-check", "problem_condition_check", PROBLEM_CONDITION_CHECK_PROMPT),
        ("independent-problem-solving", "independent_problem_solving", INDEPENDENT_SOLVING_PROMPT),
        ("independent-pedagogical-review", "independent_pedagogical_review", INDEPENDENT_REVIEW_PROMPT),
    )
    VERIFIERS = (
        ("quadratic_sympy", "app/verifiers/quadratic_sympy.py"),
        ("quadratic_numeric", "app/verifiers/quadratic_numeric.py"),
        ("four_layer_duplicate", "app/verifiers/four_layer_duplicate.py"),
        ("evaluation_leakage", "app/evaluation/leakage.py"),
    )

    def ensure(
        self,
        session: Session,
        *,
        model_version_id: str,
        profile: str,
    ) -> CandidateValidationVersions:
        """中文：处理“ensure”相关操作。
        English: Handles the ensure operation.
        """
        if profile != self.PROFILE:
            raise ValueError(f"unsupported verifier profile: {profile}")
        model = session.get(ModelVersion, model_version_id)
        if model is None or not model.active:
            raise ValueError("active validation model version is required")
        prompts = {
            purpose: self._ensure_prompt(session, key, purpose, text)
            for key, purpose, text in self.PROMPTS
        }
        verifiers = {
            key: self._ensure_verifier(session, key, relative_path)
            for key, relative_path in self.VERIFIERS
        }
        return CandidateValidationVersions(
            model_version_id=model.id,
            condition_prompt_version_id=prompts["problem_condition_check"].id,
            solver_prompt_version_id=prompts["independent_problem_solving"].id,
            review_prompt_version_id=prompts["independent_pedagogical_review"].id,
            sympy_verifier_version_id=verifiers["quadratic_sympy"].id,
            numeric_verifier_version_id=verifiers["quadratic_numeric"].id,
            duplicate_verifier_version_id=verifiers["four_layer_duplicate"].id,
            leakage_verifier_version_id=verifiers["evaluation_leakage"].id,
        )

    def generation_prompt(self, session: Session) -> PromptVersion:
        """中文：处理“生成·提示词”相关操作。
        English: Handles the generation prompt operation.
        """
        key, purpose, text = self.PROMPTS[0]
        return self._ensure_prompt(session, key, purpose, text)

    @staticmethod
    def _ensure_prompt(
        session: Session, key: str, purpose: str, template: str
    ) -> PromptVersion:
        """中文：处理“ensure·提示词”相关操作。
        English: Handles the ensure prompt operation.
        """
        template_hash = sha256(template.encode("utf-8")).hexdigest()
        entity = session.scalar(select(PromptVersion).where(
            PromptVersion.prompt_key == key,
            PromptVersion.version == "1.0.0",
        ))
        if entity is None:
            entity = PromptVersion(
                prompt_key=key,
                version="1.0.0",
                purpose=purpose,
                template_text=template,
                template_hash=template_hash,
                output_schema_version="1.0",
                active=True,
            )
            session.add(entity)
            session.flush()
        elif entity.template_hash != template_hash or entity.purpose != purpose:
            raise RuntimeError(f"prompt {key} changed without a version bump")
        entity.active = True
        return entity

    @staticmethod
    def _ensure_verifier(
        session: Session, key: str, relative_path: str
    ) -> VerifierVersion:
        """中文：处理“ensure·verifier”相关操作。
        English: Handles the ensure verifier operation.
        """
        project_root = Path(__file__).resolve().parents[2]
        implementation_hash = sha256((project_root / relative_path).read_bytes()).hexdigest()
        rules = {
            "profile": ValidationVersionRegistry.PROFILE,
            "problem_type": "quadratic_equation",
            "fail_closed": True,
        }
        ruleset_hash = sha256(json.dumps(
            rules, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        entity = session.scalar(select(VerifierVersion).where(
            VerifierVersion.verifier_key == key,
            VerifierVersion.version == "1.0.0",
        ))
        if entity is None:
            entity = VerifierVersion(
                verifier_key=key,
                version="1.0.0",
                implementation_hash=implementation_hash,
                ruleset_hash=ruleset_hash,
                supported_problem_types_json=["quadratic_equation"],
                config_json=rules,
                active=True,
            )
            session.add(entity)
            session.flush()
        elif (
            entity.implementation_hash != implementation_hash
            or entity.ruleset_hash != ruleset_hash
        ):
            raise RuntimeError(f"verifier {key} changed without a version bump")
        entity.active = True
        return entity


validation_version_registry = ValidationVersionRegistry()
