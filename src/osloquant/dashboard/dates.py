"""Dates as the dashboard writes them (D58): Norwegian, one form everywhere – «9. nov. 2026», «9. nov. 10:32»,
«mandag 9. nov. 2026», «nov. 2026». Month abbreviations follow Språkrådet (mars, april, mai, juni and juli are written
out). Machine identifiers – log rows, run ids, file names – keep ISO dates; anything a person reads uses these."""

from __future__ import annotations

import html
import re
from datetime import date, datetime

import pandas as pd

MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember"]
SHORT_MONTHS = ["jan.", "feb.", "mars", "april", "mai", "juni", "juli", "aug.", "sep.", "okt.", "nov.", "des."]
DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
SHORT_DAYS = ["man.", "tir.", "ons.", "tor.", "fre.", "lør.", "søn."]


def _ts(d) -> pd.Timestamp | None:
    if d is None or (isinstance(d, float) and d != d):
        return None
    try:
        t = pd.Timestamp(d)
    except (ValueError, TypeError):
        return None
    return None if pd.isna(t) else t


def dato(d, year: bool = True, weekday: bool = False, short_weekday: bool = False) -> str:
    """«9. nov. 2026»; ``year=False`` gives «9. nov.»; ``weekday`` puts «mandag» in front (``short_weekday``: «man.»).
    Accepts a Timestamp, datetime, date or ISO string; anything unreadable comes back as written."""
    t = _ts(d)
    if t is None:
        return "" if d is None else html.escape(str(d))
    s = f"{t.day}. {SHORT_MONTHS[t.month - 1]}" + (f" {t.year}" if year else "")
    if weekday or short_weekday:
        s = f"{(SHORT_DAYS if short_weekday else DAYS)[t.weekday()]} {s}"
    return s


def dato_tid(d, year: bool = False) -> str:
    """«9. nov. 10:32» (Oslo time when the value carries a time zone); ``year=True`` gives «9. nov. 2026 10:32»."""
    t = _ts(d)
    if t is None:
        return "" if d is None else str(d)
    if t.tzinfo is not None:
        t = t.tz_convert("Europe/Oslo")
    return f"{dato(t, year)} {t:%H:%M}"


def stempel(s) -> str:
    """A fetch time stored as UTC ISO («2026-11-09T17:47:07Z») as Oslo time: «9. nov. 2026 18:47»."""
    t = _ts(s)
    if t is None:
        return "–" if not s else str(s)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return dato_tid(t, True)


def periode(label) -> str:
    """The light case's period labels in Norwegian: «LTM to 2026-09-30» → «LTM til 30. sep. 2026», «FY to 2025-12-31»
    → «år til 31. des. 2025», a bare ISO date → «30. sep. 2026». Anything else comes back escaped, as written."""
    if label is None:
        return "–"
    s = str(label)
    for eng, nor in (("LTM to ", "LTM til "), ("FY to ", "år til ")):
        if s.startswith(eng):
            return nor + dato(s[len(eng):])
    return dato(s)


def klokke(s) -> str:
    """The Oslo clock time of a UTC stamp: «2026-11-09T17:48:02Z» → «18:48»."""
    t = _ts(s)
    if t is None:
        return "–"
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return f"{t.tz_convert('Europe/Oslo'):%H:%M}"


def maaned(d) -> str:
    """«nov. 2026»."""
    t = _ts(d)
    return "" if t is None else f"{SHORT_MONTHS[t.month - 1]} {t.year}"


def today_words(d: date | datetime | None = None) -> str:
    return dato(d or datetime.now(), weekday=True)


#: Plotly.js locale with the same names, registered once per page; numbers have the page's own form (decimal comma,
#: narrow space between thousands, D61) so a chart and the table beside it read alike.
PLOTLY_LOCALE = ("<script>if(window.Plotly){Plotly.register({moduleType:'locale',name:'no',dictionary:{},format:{"
                 f"days:{DAYS[6:] + DAYS[:6]},shortDays:{SHORT_DAYS[6:] + SHORT_DAYS[:6]},months:{MONTHS},shortMonths:{SHORT_MONTHS},"
                 "date:'%d.%m.%Y',decimal:',',thousands:'\u202f',grouping:[3],currency:['NOK ','']}});"
                 "Plotly.setPlotConfig({locale:'no'});}</script>")

#: tick labels on a date axis, from days to years: «27. sep.», «sep. 2026», «2026»
DATE_TICKS = [dict(dtickrange=[None, 86400000 * 27], value="%-d. %b"), dict(dtickrange=[86400000 * 27, 86400000 * 360], value="%b %Y"),
              dict(dtickrange=[86400000 * 360, None], value="%Y")]
DATE_HOVER = "%-d. %b %Y"


# ------------------------------------------------------------------------------------------------ the last pass on a page
_SKIP = {"script", "style", "textarea", "code", "pre", "title"}
_TAG = re.compile(r"(<[^>]+>)")
_ISO = re.compile(r"(?<![\w/.\-])(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(\s?(?:Z|UTC)\b)?)?(?![\w\-])")


def _one(m: re.Match) -> str:
    rest = m.string[m.end():m.end() + 2]
    if len(rest) == 2 and rest[0] == "." and rest[1].isalpha():       # a file name: estimates_2026-11-02.json, report.pdf
        return m.group(0)
    try:
        t = pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return m.group(0)
    if m.group(4) is None:
        return dato(t)
    t = t + pd.Timedelta(hours=int(m.group(4)), minutes=int(m.group(5)))
    if m.group(6):                                                      # a UTC stamp: shown as Oslo time
        t = t.tz_localize("UTC")
    return dato_tid(t, True)


def norske_datoer(page_html: str) -> str:
    """Every ISO date in the text a person reads – «2026-11-09», «2026-11-09T17:47:07Z», «2026-11-09 17:47 UTC» – in
    the Norwegian form, UTC stamps as Oslo time. Tags and attributes (links, data for scripts), scripts, styles, form
    fields, code and file names are left exactly as they are: the pass changes what is read, never what is sent."""
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
            out.append(part)
        elif skip or not part:
            out.append(part)
        else:
            out.append(_ISO.sub(_one, part))
    return "".join(out)
