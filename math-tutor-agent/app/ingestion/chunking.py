from __future__ import annotations

import re
from hashlib import sha256

from app.ingestion.schemas import (
    ChunkFormula,
    ChunkingConfig,
    FormulaRecord,
    ParsedBlock,
    PreparedChunk,
)


TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|\\[A-Za-z]+|[^\s]")
FORMULA_PATTERN = re.compile(r"\$\$.+?\$\$|(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)", re.DOTALL)
SENTENCE_PATTERN = re.compile(r".+?(?:[。！？.!?；;]+|\n+|$)", re.DOTALL)
ATOMIC_TOKEN_PATTERN = re.compile(
    r"\$\$.+?\$\$|(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)|"
    r"[\u3400-\u9fff]|[A-Za-z0-9_]+|\\[A-Za-z]+|[^\s]",
    re.DOTALL,
)


def estimate_tokens(value: str) -> int:
    return max(1, len(TOKEN_PATTERN.findall(value)))


def _hard_split(text: str, max_tokens: int) -> list[str]:
    matches = list(ATOMIC_TOKEN_PATTERN.finditer(text))
    if not matches:
        return [text]
    parts: list[str] = []
    start = 0
    weight = 0
    for match in matches:
        atom = match.group(0)
        atom_weight = estimate_tokens(atom) if atom.startswith("$") else 1
        if weight and weight + atom_weight > max_tokens:
            part = text[start:match.start()].strip()
            if part:
                parts.append(part)
            start = match.start()
            weight = 0
        weight += atom_weight
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [text]


def _overlap_tail(text: str, token_limit: int) -> str:
    if token_limit <= 0:
        return ""
    matches = list(ATOMIC_TOKEN_PATTERN.finditer(text))
    if len(matches) <= token_limit:
        return text.strip()
    selected = matches[-token_limit:]
    return text[selected[0].start():].strip()


def _split_oversized(text: str, max_tokens: int) -> list[str]:
    formulae: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        key = f"\u0000FORMULA_{len(formulae)}\u0000"
        formulae[key] = match.group(0)
        return key

    protected = FORMULA_PATTERN.sub(protect, text)
    units = [match.group(0).strip() for match in SENTENCE_PATTERN.finditer(protected)]
    output: list[str] = []
    current: list[str] = []
    for unit in units:
        restored = unit
        for key, formula in formulae.items():
            restored = restored.replace(key, formula)
        if estimate_tokens(restored) > max_tokens:
            if current:
                output.append(" ".join(current))
                current = []
            output.extend(_hard_split(restored, max_tokens))
            continue
        if current and estimate_tokens(" ".join(current + [restored])) > max_tokens:
            output.append(" ".join(current))
            current = []
        current.append(restored)
    if current:
        output.append(" ".join(current))
    return output or [text]


def chunk_blocks(
    blocks: list[ParsedBlock],
    config: ChunkingConfig,
    knowledge_point_codes: list[str],
    formula_records: list[FormulaRecord],
) -> tuple[list[PreparedChunk], int]:
    originals_by_normalized: dict[str, list[str]] = {}
    for record in formula_records:
        originals = originals_by_normalized.setdefault(record.normalized, [])
        if record.original not in originals:
            originals.append(record.original)
    raw_chunks: list[tuple[str, list[str], str | None, str]] = []
    current_texts: list[str] = []
    current_heading: list[str] = []
    current_locator: str | None = None
    current_type = "text"

    def flush() -> None:
        nonlocal current_texts
        if current_texts:
            raw_chunks.append((
                "\n\n".join(current_texts),
                list(current_heading),
                current_locator,
                current_type,
            ))
            current_texts = []

    for block in blocks:
        for text in _split_oversized(block.text, config.max_tokens):
            incompatible_heading = bool(current_texts and block.heading_path != current_heading)
            too_large = bool(
                current_texts
                and estimate_tokens("\n\n".join(current_texts + [text])) > config.target_tokens
            )
            if incompatible_heading or too_large:
                flush()
            if not current_texts:
                current_heading = list(block.heading_path)
                current_locator = block.locator
                current_type = block.content_type
            current_texts.append(text)
    flush()

    chunks: list[PreparedChunk] = []
    seen_base_hashes: set[str] = set()
    duplicate_count = 0
    previous_tail = ""
    for text, heading_path, locator, content_type in raw_chunks:
        base_hash = sha256(text.encode("utf-8")).hexdigest()
        if base_hash in seen_base_hashes:
            duplicate_count += 1
            continue
        seen_base_hashes.add(base_hash)
        content = text
        if previous_tail and config.overlap_tokens:
            content = previous_tail + "\n\n" + content
        content_hash = sha256(content.encode("utf-8")).hexdigest()
        formulae: list[ChunkFormula] = []
        seen_formulae: set[str] = set()
        for match in FORMULA_PATTERN.finditer(content):
            rendered = match.group(0)
            normalized_formula = (
                rendered[2:-2] if rendered.startswith("$$") else rendered[1:-1]
            )
            if normalized_formula in seen_formulae:
                continue
            seen_formulae.add(normalized_formula)
            formulae.append(ChunkFormula(
                normalized=normalized_formula,
                originals=originals_by_normalized.get(normalized_formula, []),
            ))
        chunks.append(PreparedChunk(
            ordinal=len(chunks),
            content=content,
            content_hash=content_hash,
            token_count=estimate_tokens(content),
            heading_path=heading_path,
            locator=locator,
            content_type=content_type,
            knowledge_point_codes=knowledge_point_codes,
            formulae=formulae,
        ))
        previous_tail = _overlap_tail(text, config.overlap_tokens)
    return chunks, duplicate_count
