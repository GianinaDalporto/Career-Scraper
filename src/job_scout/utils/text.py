"""Text normalisation helpers used by fingerprints, scoring and parsers."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def collapse_ws(value: str | None) -> str:
    if not value:
        return ""
    return _WS.sub(" ", value).strip()


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    import html as html_lib

    # Greenhouse and some ATS boards return fully entity-encoded HTML (&lt;div&gt;…).
    text = html_lib.unescape(html_lib.unescape(value))
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = (
        text.replace("\xa0", " ")
        .replace("&nbsp;", " ")
    )
    return collapse_ws(text)


def normalise_key(value: str | None) -> str:
    text = collapse_ws(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _PUNCT.sub(" ", text)
    return collapse_ws(text)


def company_key(value: str | None) -> str:
    text = normalise_key(value)
    for suffix in (
        " pty ltd",
        " pty. ltd.",
        " limited",
        " ltd",
        " llc",
        " inc",
        " incorporated",
        " plc",
        " gmbh",
        " bv",
        " nv",
        " sa",
        " ag",
        " co",
        " company",
        " group",
        " holdings",
    ):
        if text.endswith(suffix.strip()):
            text = text[: -len(suffix.strip())].strip()
    return collapse_ws(text)


def sha256_text(*parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def contains_phrase(haystack: str, phrase: str) -> bool:
    if not haystack or not phrase:
        return False
    return re.search(rf"\b{re.escape(phrase)}\b", haystack, flags=re.IGNORECASE) is not None
