"""Numbers in one Norwegian form (improvement pass 10 Nov 2026, D61): decimal comma, a space before the per cent
sign, a real minus, a narrow space between thousands. Like the dates (D58), it is one last pass over the finished
page, so every page reads alike without each of the sixteen formatting helpers being rewritten.

The pass changes what a person reads and nothing else. Tags, links, form fields, scripts, styles and code are left
exactly as they are; only text between tags and the hover text in ``title="…"`` is touched. Things that look like
numbers but are not – version numbers (5.2.1), addresses (127.0.0.1), dates (09.11.2026), file names – are left.
The pass can be run twice with the same result. That is why it does not regroup thousands: «9,410» is a rate with
three decimals after the pass and would read as nine thousand to a second one. Counts are grouped where they are
written, with ``heltall``.

``tall``, ``prosent`` and ``heltall`` format a single value for code that builds text directly.
"""

from __future__ import annotations

import re

NBSP = chr(0x00A0)          # before % and between a number and its unit: never breaks the line
THIN = chr(0x202F)          # between thousands: narrow, never breaks
MINUS = chr(0x2212)

_SKIP = {"script", "style", "textarea", "code", "pre", "title", "select"}
_TAG = re.compile(r"(<[^>]+>)")
_TITLE = re.compile(r'(\btitle=")([^"]*)(")')
# 45.50, 0.25, 9.410, 15.7x, 3.2m – but not 5.2.1, 127.0.0.1, 09.11.2026, v3.0 or a file name. A unit of up to three
# letters may be glued to the number. A number hyphenated to a word is part of a name: Apache-2.0.
_DECIMAL = re.compile(r"(?<![\w.,])(?<![A-Za-zæøå]-)(\d+)\.(\d+)(?!(?![a-zA-Z\u00e6\u00f8\u00e5]{1,3}\b)\w|[.,]\d)")
_PERCENT = re.compile(r"(?<=\d)\s?%")
# a hyphen used as a minus sign: before a digit, not inside a date, a range or a word
_HYPHEN_MINUS = re.compile(r"(?<![\w\d.," + MINUS + r"\-–])-(?=\d)")
_NEGATIVE_ZERO = re.compile(MINUS + r"(0(?:,0+)?)(?![\d,])")


def _text(s: str) -> str:
    if not s or not any(ch.isdigit() for ch in s):
        return s
    s = _DECIMAL.sub(r"\1,\2", s)
    s = _PERCENT.sub(NBSP + "%", s)
    s = _HYPHEN_MINUS.sub(MINUS, s)
    return _NEGATIVE_ZERO.sub(r"\1", s)                  # «−0,00» is zero


def norske_tall(page_html: str) -> str:
    """Every number a person reads on the page in the Norwegian form. See the module text for what is left alone."""
    out, skip = [], []
    for part in _TAG.split(page_html):
        if part.startswith("<") and part.endswith(">"):
            name = re.match(r"</?\s*([a-zA-Z0-9]+)", part)
            if name:
                tag = name.group(1).lower()
                if tag in _SKIP and not part.endswith("/>"):
                    if part.startswith("</"):
                        if skip and skip[-1] == tag:
                            skip.pop()
                    else:
                        skip.append(tag)
            if 'title="' in part and not skip:
                part = _TITLE.sub(lambda m: m.group(1) + _text(m.group(2)) + m.group(3), part)
            out.append(part)
        elif skip or not part:
            out.append(part)
        else:
            out.append(_text(part))
    return "".join(out)


def tall(x, d: int = 2, sign: bool = False) -> str:
    """One number: «1 234,50», «−0,25», «+3,1» with ``sign``; None and NaN give «–»."""
    if x is None or x != x:
        return "–"
    v = round(float(x), d)
    if v == 0:
        v = 0.0                                          # never «−0,00»
    s = f"{abs(v):,.{d}f}".replace(",", THIN).replace(".", ",")
    return (MINUS if v < 0 else "+" if sign and v > 0 else "") + s


def heltall(x) -> str:
    """A count: «305 610»."""
    return "–" if x is None or x != x else tall(x, 0)


def prosent(x, d: int = 1, sign: bool = True) -> str:
    """A share as per cent: 0.145 → «+14,5 %»."""
    return "–" if x is None or x != x else tall(float(x) * 100, d, sign) + NBSP + "%"
