"""Markdown rendering of statements and descriptions, with the resulting HTML sanitized."""

import markdown
import nh3

# Tags and attributes allowed in statements on top of nh3's safe defaults
_EXTRA_ATTRIBUTES = {"code": {"class"}, "pre": {"class"}, "span": {"class"}, "div": {"class"}}


def markdown_to_html(text: str) -> str:
    """Renders Markdown (with fenced code blocks and tables) to sanitized HTML.

    Statements are written by teachers, but they are shown to every student, so
    any script or event handler is removed anyway.
    """
    html = markdown.markdown(text, extensions=["fenced_code", "tables"], output_format="html")
    attributes = {tag: set(attrs) for tag, attrs in nh3.ALLOWED_ATTRIBUTES.items()}
    for tag, attrs in _EXTRA_ATTRIBUTES.items():
        attributes.setdefault(tag, set()).update(attrs)
    return nh3.clean(html, attributes=attributes)
