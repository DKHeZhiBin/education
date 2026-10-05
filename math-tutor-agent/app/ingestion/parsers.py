from __future__ import annotations

import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser

from app.ingestion.schemas import ParsedBlock, SupportedMediaType


class DocumentParseError(ValueError):
    pass


class DocumentParser(ABC):
    name: str

    @abstractmethod
    def parse(self, content: str) -> list[ParsedBlock]: ...


def _content_type(text: str) -> str:
    lowered = text.casefold().strip()
    labels = {
        "definition": ("definition", "定义"),
        "theorem": ("theorem", "定理"),
        "proof": ("proof", "证明"),
        "example": ("example", "例题", "示例"),
        "exercise": ("exercise", "练习", "习题"),
    }
    for content_type, prefixes in labels.items():
        if lowered.startswith(prefixes):
            return content_type
    return "text"


class PlainTextParser(DocumentParser):
    name = "plain_text_v1"

    def parse(self, content: str) -> list[ParsedBlock]:
        paragraphs = re.split(r"\n\s*\n", content)
        blocks = []
        for index, paragraph in enumerate(paragraphs, start=1):
            text = paragraph.strip()
            if text:
                blocks.append(ParsedBlock(
                    text=text,
                    locator=f"paragraph:{index}",
                    content_type=_content_type(text),
                ))
        return blocks


class MarkdownParser(DocumentParser):
    name = "markdown_v1"
    _heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def parse(self, content: str) -> list[ParsedBlock]:
        heading_path: list[str] = []
        pending: list[str] = []
        blocks: list[ParsedBlock] = []
        paragraph_start = 1
        in_fence = False

        def flush(end_line: int) -> None:
            nonlocal pending, paragraph_start
            text = "\n".join(pending).strip()
            if text:
                blocks.append(ParsedBlock(
                    text=text,
                    heading_path=list(heading_path),
                    locator=f"lines:{paragraph_start}-{end_line}",
                    content_type="code" if text.startswith("```") else _content_type(text),
                ))
            pending = []

        for line_number, line in enumerate(content.splitlines(), start=1):
            if line.strip().startswith("```"):
                if not pending:
                    paragraph_start = line_number
                in_fence = not in_fence
                pending.append(line)
                if not in_fence:
                    flush(line_number)
                    paragraph_start = line_number + 1
                continue
            heading = None if in_fence else self._heading.match(line)
            if heading:
                flush(line_number - 1)
                level = len(heading.group(1))
                title = heading.group(2).strip()
                heading_path = heading_path[: level - 1] + [title]
                continue
            if not in_fence and not line.strip():
                flush(line_number - 1)
                paragraph_start = line_number + 1
                continue
            if not pending:
                paragraph_start = line_number
            pending.append(line)
        flush(len(content.splitlines()))
        return blocks


class _StructuredHTMLParser(HTMLParser):
    ignored_tags = {"script", "style", "nav", "footer", "noscript"}
    block_tags = {"p", "li", "pre", "blockquote", "td", "th", "div"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_path: list[str] = []
        self.blocks: list[ParsedBlock] = []
        self._buffer: list[str] = []
        self._current_tag: str | None = None
        self._ignored_depth = 0
        self._block_number = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self.ignored_tags:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in self.block_tags or re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._current_tag = tag
        elif tag == "br":
            self._buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self.ignored_tags:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if not self._ignored_depth and (
            tag in self.block_tags or re.fullmatch(r"h[1-6]", tag)
        ):
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = "".join(self._buffer).strip()
        tag = self._current_tag
        self._buffer = []
        self._current_tag = None
        if not text:
            return
        if tag and re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            self.heading_path = self.heading_path[: level - 1] + [text]
            return
        self._block_number += 1
        self.blocks.append(ParsedBlock(
            text=text,
            heading_path=list(self.heading_path),
            locator=f"html-block:{self._block_number}",
            content_type=_content_type(text),
        ))


class HTMLDocumentParser(DocumentParser):
    name = "html_v1"

    def parse(self, content: str) -> list[ParsedBlock]:
        parser = _StructuredHTMLParser()
        try:
            parser.feed(content)
            parser.close()
        except Exception as error:
            raise DocumentParseError("invalid HTML document") from error
        return parser.blocks


PARSERS: dict[str, DocumentParser] = {
    "text/plain": PlainTextParser(),
    "text/markdown": MarkdownParser(),
    "text/html": HTMLDocumentParser(),
}


def parser_for(media_type: SupportedMediaType) -> DocumentParser:
    try:
        return PARSERS[media_type]
    except KeyError as error:
        raise DocumentParseError(f"unsupported media type: {media_type}") from error
