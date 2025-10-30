from __future__ import annotations

from functools import lru_cache

import bleach
from bleach.linkifier import Linker
from markdown_it import MarkdownIt

MAX_MARKDOWN_CHARS = 20_000
MAX_HTML_CHARS = 100_000

ALLOWED_TAGS = [
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "code",
    "pre",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "hr",
    "img",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["align", "colspan", "rowspan"],
    "td": ["align", "colspan", "rowspan"],
}

ALLOWED_PROTOCOLS = ["http", "https"]


@lru_cache(maxsize=1)
def _markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"linkify": True, "typographer": False})
    md.enable("table")
    md.enable("strikethrough")
    return md


def _link_attrs(attrs: dict[tuple[str | None, str], str], _new: bool) -> dict[tuple[str | None, str], str]:
    href = attrs.get((None, "href"))
    if not href:
        return attrs
    attrs[(None, "target")] = "_blank"
    rel_values = set(filter(None, (attrs.get((None, "rel")) or "").split()))
    rel_values.update({"noopener", "noreferrer"})
    attrs[(None, "rel")] = " ".join(sorted(rel_values))
    return attrs


_linker = Linker(callbacks=[_link_attrs], skip_tags=["pre", "code"])


def render_markdown(raw_markdown: str | None) -> str:
    text = (raw_markdown or "").strip()
    if not text:
        return ""
    if len(text) > MAX_MARKDOWN_CHARS:
        raise ValueError("Markdown excede o limite de 20k caracteres.")
    rendered = _markdown().render(text)
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    linked = _linker.linkify(cleaned)
    if len(linked) > MAX_HTML_CHARS:
        raise ValueError("HTML sanitizado excede o limite de 100k caracteres.")
    return linked

