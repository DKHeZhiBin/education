from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.ingestion.schemas import FormulaRecord, ParsedBlock


FORMULA_PATTERN = re.compile(
    r"(?P<display>\$\$(.+?)\$\$|\\\[(.+?)\\\])|"
    r"(?P<inline>(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)|\\\((.+?)\\\))",
    re.DOTALL,
)
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class NormalizedDocument:
    """中文：定义“normalized·文档”类，封装该职责相关的数据与行为。
    English: Defines the normalized document class and encapsulates data and behavior for that responsibility.
    """
    blocks: list[ParsedBlock]
    formulae: list[FormulaRecord]


def normalize_formula(value: str) -> str:
    """中文：处理“规范化·formula”相关操作。
    English: Handles the normalize formula operation.
    """
    normalized = unicodedata.normalize("NFC", value).strip()
    normalized = normalized.replace("−", "-").replace("–", "-")
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"\\(?:left|right)\s*", "", normalized)
    normalized = normalized.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    normalized = re.sub(r"[ \t\r\n]+", " ", normalized)
    normalized = re.sub(r"\s*([=+\-*/^_,])\s*", r"\1", normalized)
    return normalized.strip()


def clean_text(value: str) -> str:
    """中文：处理“clean·text”相关操作。
    English: Handles the clean text operation.
    """
    cleaned = unicodedata.normalize("NFC", value)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\u200b", "").replace("\ufeff", "")
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = CONTROL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_blocks(blocks: list[ParsedBlock]) -> NormalizedDocument:
    """中文：处理“规范化·blocks”相关操作。
    English: Handles the normalize blocks operation.
    """
    normalized_blocks: list[ParsedBlock] = []
    formulae: list[FormulaRecord] = []
    for block in blocks:
        text = clean_text(block.text)
        if not text:
            continue
        block_ordinal = len(normalized_blocks)

        if block.content_type == "code":
            normalized_blocks.append(block.model_copy(update={"text": text}))
            continue

        def replace_formula(match: re.Match[str]) -> str:
            """中文：处理“replace·formula”相关操作。
            English: Handles the replace formula operation.
            """
            original = match.group(0)
            if match.group("display"):
                inner = match.group(2) or match.group(3)
            else:
                inner = match.group(5) or match.group(6)
            if inner is None:
                return original
            normalized = normalize_formula(inner)
            formulae.append(FormulaRecord(
                original=original,
                normalized=normalized,
                block_ordinal=block_ordinal,
            ))
            delimiter = "$$" if match.group("display") else "$"
            return f"{delimiter}{normalized}{delimiter}"

        text = FORMULA_PATTERN.sub(replace_formula, text)
        normalized_blocks.append(block.model_copy(update={"text": text}))
    return NormalizedDocument(blocks=normalized_blocks, formulae=formulae)
