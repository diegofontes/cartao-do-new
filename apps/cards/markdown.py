from __future__ import annotations

from functools import lru_cache

import bleach
from bleach.linkifier import Linker
from markdown_it import MarkdownIt

MAX_MARKDOWN_CHARS = 20_000
MAX_HTML_CHARS = 100_000

ALLOWED_TAGS = [
    "a",
    "p",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "img",
    "hr",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
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
    rel_values = set((attrs.get((None, "rel")) or "").split())
    rel_values.update({"noopener", "noreferrer", "nofollow"})
    attrs[(None, "rel")] = " ".join(sorted(rel_values))
    return attrs


_linker = Linker(callbacks=[_link_attrs], skip_tags=["pre", "code"])


def sanitize_about_markdown(raw_markdown: str) -> str:
    """
    Render Markdown into sanitized HTML suitable for dashboard preview and viewer.

    Raises:
        ValueError: when content exceeds the configured size limits.
    """
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


def has_about_content(raw_markdown: str | None) -> bool:
    return bool((raw_markdown or "").strip())

