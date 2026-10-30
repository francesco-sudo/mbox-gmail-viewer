import re

import bleach


ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union(
    {
        "html",
        "body",
        "head",
        "title",
        "meta",
        "style",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "caption",
        "colgroup",
        "col",
        "img",
        "font",
        "center",
        "div",
        "span",
        "p",
        "br",
        "hr",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "strike",
        "small",
        "big",
        "sub",
        "sup",
        "code",
        "kbd",
        "samp",
        "var",
        "mark",
        "ins",
        "del",
        "abbr",
        "acronym",
        "address",
        "article",
        "aside",
        "details",
        "summary",
        "figure",
        "figcaption",
        "map",
        "area",
        "q",
        "tt",
    }
)

ALLOWED_ATTRS = {
    "*": ["class", "style", "title", "id"],
    "a": ["href", "name", "target", "rel"],
    "img": [
        "src",
        "alt",
        "title",
        "width",
        "height",
        "border",
        "align",
        "style",
        "class",
    ],
    "table": [
        "border",
        "cellpadding",
        "cellspacing",
        "width",
        "height",
        "align",
        "bgcolor",
        "style",
        "class",
    ],
    "td": [
        "colspan",
        "rowspan",
        "width",
        "height",
        "align",
        "valign",
        "bgcolor",
        "style",
        "class",
    ],
    "th": [
        "colspan",
        "rowspan",
        "width",
        "height",
        "align",
        "valign",
        "bgcolor",
        "style",
        "class",
    ],
    "tr": ["align", "valign", "bgcolor", "style", "class"],
    "font": ["color", "face", "size"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto", "cid", "data"]


def _clean_style_attribute(match):
    style = match.group(1)
    style = re.sub(r"url\s*\([^)]*\)", "", style, flags=re.IGNORECASE)
    style = re.sub(r"expression\s*\([^)]*\)", "", style, flags=re.IGNORECASE)
    style = re.sub(r"javascript\s*:", "", style, flags=re.IGNORECASE)
    style = re.sub(r"@import[^;]*;?", "", style, flags=re.IGNORECASE)
    return f'style="{style}"'


def _process_img_tag(match, allow_remote_images):
    tag = match.group(0)
    src_match = re.search(r'src="([^"]*)"', tag, flags=re.IGNORECASE)
    if not src_match:
        return tag

    src = src_match.group(1)
    low = src.lower()

    if low.startswith("data:"):
        if low.startswith("data:image/"):
            return tag
        return re.sub(r'\ssrc="[^"]*"', "", tag, flags=re.IGNORECASE)

    if low.startswith("cid:"):
        return tag

    if low.startswith("http://") or low.startswith("https://"):
        if allow_remote_images:
            return tag
        return re.sub(r'\ssrc="[^"]*"', "", tag, flags=re.IGNORECASE)

    return re.sub(r'\ssrc="[^"]*"', "", tag, flags=re.IGNORECASE)


def sanitize_html(html: str, allow_remote_images: bool = False) -> str:
    if not html:
        return ""

    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )

    cleaned = re.sub(
        r'style="([^"]*)"', _clean_style_attribute, cleaned, flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"<img\b[^>]*>",
        lambda m: _process_img_tag(m, allow_remote_images),
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r'<a\b[^>]*href="\s*data:[^"]*"[^>]*>',
        "<a>",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r'<img\b[^>]*src="cid:[^"]*"[^>]*>',
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"<script\b[^>]*>.*?</script>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<iframe\b[^>]*>.*?</iframe>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<object\b[^>]*>.*?</object>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<embed\b[^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned
