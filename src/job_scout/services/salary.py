"""Parse employer-published salary text. Never invent a lower bound or hours."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from job_scout.models.job import SalarySnapshot

_PERIOD_ALIASES = {
    "hour": "hourly",
    "hourly": "hourly",
    "hr": "hourly",
    "ph": "hourly",
    "/h": "hourly",
    "/hr": "hourly",
    "per hour": "hourly",
    "an hour": "hourly",
    "day": "daily",
    "daily": "daily",
    "pd": "daily",
    "p/d": "daily",
    "/d": "daily",
    "week": "weekly",
    "weekly": "weekly",
    "pw": "weekly",
    "p/w": "weekly",
    "month": "monthly",
    "monthly": "monthly",
    "pm": "monthly",
    "p/m": "monthly",
    "pcm": "monthly",
    "per month": "monthly",
    "year": "annual",
    "yearly": "annual",
    "annual": "annual",
    "annum": "annual",
    "pa": "annual",
    "p.a": "annual",
    "p.a.": "annual",
    "fy": "annual",
    "per year": "annual",
    "per annum": "annual",
    "biweekly": "biweekly",
    "bi-weekly": "biweekly",
    "fortnightly": "biweekly",
    "every two weeks": "biweekly",
    "twice monthly": "semimonthly",
    "semi-monthly": "semimonthly",
    "semimonthly": "semimonthly",
}

_CURRENCY_WORDS = {
    "zar": "ZAR",
    "rand": "ZAR",
    "rands": "ZAR",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "aud": "AUD",
    "cad": "CAD",
    "nzd": "NZD",
    "chf": "CHF",
    "jpy": "JPY",
    "nok": "NOK",
    "sek": "SEK",
    "dkk": "DKK",
    "pln": "PLN",
}

_NUMBER = r"(?:(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,]\d+)?|\d+(?:\.\d+)?)\s*[kKmM]?"
_RANGE_SEP = r"(?:\s*(?:-|–|—|to|and)\s*)"
_HOURS_PATTERNS = (
    r"(?:±|~|approx(?:imately)?|about|around|circa)?\s*(\d{1,2}(?:[.,]\d+)?)\s*"
    r"(?:hours?|hrs?|h)\s*(?:a|per|/)\s*week",
    r"(\d{1,2}(?:[.,]\d+)?)\s*h(?:ours?|rs?)?\s*/\s*w(?:eek)?",
    r"(\d{1,2}(?:[.,]\d+)?)\s*hrs?\s*p/?w\b",
    r"(\d{1,2}(?:[.,]\d+)?)\s*hours?\s*weekly",
)


def _to_decimal(raw: str) -> Decimal | None:
    text = raw.strip().lower().replace(" ", "").replace(",", "")
    multiplier = Decimal("1")
    if text.endswith("k"):
        multiplier = Decimal("1000")
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = Decimal("1000000")
        text = text[:-1]
    if text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return Decimal(text) * multiplier
    except (InvalidOperation, ValueError):
        return None


def detect_currency(text: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit.upper()
    lowered = text.lower()
    for word, code in _CURRENCY_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return code
    if re.search(r"\baud\b|australian\s+dollar|a\$", lowered):
        return "AUD"
    if "zar" in lowered or re.search(r"\brand\b", lowered) or re.search(r"\bR[\s]?[\d]", text):
        return "ZAR"
    if "€" in text or "eur" in lowered:
        return "EUR"
    if "£" in text or "gbp" in lowered:
        return "GBP"
    if "$" in text or "us$" in lowered:
        if re.search(r"\b(australia|aud)\b", lowered):
            return "AUD"
        if re.search(r"\b(canada|cad)\b", lowered):
            return "CAD"
        return "USD"
    if re.search(r"\bR[\d]", text) or re.search(r"\bR\s+\d", text):
        return "ZAR"
    return None


def detect_period(text: str, explicit: str | None = None) -> str:
    if explicit:
        key = explicit.lower().strip().replace(".", "")
        return _PERIOD_ALIASES.get(key, key)
    lowered = text.lower()
    # Prefer explicit hourly / daily cues before generic "week" noise.
    for alias in ("per hour", "an hour", "/hr", "/h", "hourly", "ph"):
        if alias in lowered:
            return "hourly"
    for alias, period in sorted(_PERIOD_ALIASES.items(), key=lambda item: -len(item[0])):
        if alias in lowered:
            return period
    if detect_currency(text) == "ZAR" and re.search(r"\bR?\s?\d", text) and "year" not in lowered:
        return "monthly"
    return "annual"


def extract_hours_per_week(*texts: str | None) -> Decimal | None:
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    lowered = blob.lower().replace("±", "~")
    for pattern in _HOURS_PATTERNS:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if not match:
            continue
        value = _to_decimal(match.group(1).replace(",", "."))
        if value is None:
            continue
        if Decimal("1") <= value <= Decimal("80"):
            return value
    return None


def employment_basis_for(period: str | None) -> str:
    mapping = {
        "hourly": "hourly",
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly_fixed",
        "annual": "annual",
    }
    return mapping.get(period or "", "unknown")


def to_monthly(
    amount: Decimal,
    period: str,
    *,
    hours_per_week: Decimal | None = None,
    policy: dict[str, Any] | None = None,
) -> Decimal | None:
    """Convert to monthly only when the conversion does not invent missing hours."""
    policy = policy or {}
    norm = policy.get("normalisation") or {}
    days = Decimal(str(norm.get("daily_days_per_week", 5)))
    weeks = Decimal(str(norm.get("weeks_per_year", 52)))
    if period == "monthly":
        return amount
    if period == "annual":
        return (amount / Decimal("12")).quantize(Decimal("0.01"))
    if period == "weekly":
        return ((amount * weeks) / Decimal("12")).quantize(Decimal("0.01"))
    if period == "daily":
        return ((amount * days * weeks) / Decimal("12")).quantize(Decimal("0.01"))
    if period == "hourly":
        if hours_per_week is None:
            return None
        return ((amount * hours_per_week * weeks) / Decimal("12")).quantize(Decimal("0.01"))
    if period == "biweekly":
        return ((amount * Decimal("26")) / Decimal("12")).quantize(Decimal("0.01"))
    if period == "semimonthly":
        return (amount * Decimal("2")).quantize(Decimal("0.01"))
    # Unknown period — do not invent a monthly figure.
    return None


def _salary_numbers(raw: str, *, hours_per_week: Decimal | None) -> list[Decimal]:
    numbers: list[Decimal] = []
    for match in re.finditer(_NUMBER, raw):
        value = _to_decimal(match.group(0))
        if value is None or value <= 0:
            continue
        # Don't treat "15 hours/week" as a pay figure.
        if hours_per_week is not None and value == hours_per_week:
            trailing = raw[match.end() : match.end() + 24].lower()
            if re.match(r"\s*(?:hours?|hrs?|h)\b", trailing) or "week" in trailing[:20]:
                continue
        numbers.append(value)
    return numbers


_PAY_SNIPPET = re.compile(
    r"(?:US\s+Pay\s+Range|Pay\s+Range|Salary\s*(?:Range)?|Compensation|Wage\s+Range)"
    r".{0,40}?"
    r"(?:\$|USD|EUR|GBP|ZAR|R\s?|€|£)\s?\d[\d,]*(?:\.\d+)?"
    r"(?:.{0,24}?(?:\$|USD|EUR|GBP|ZAR|R\s?|€|£)?\s?\d[\d,]*(?:\.\d+)?)?"
    r"(?:.{0,20}?(?:USD|EUR|GBP|ZAR|/year|/yr|per\s+year|per\s+annum|/hour|/hr|per\s+hour))?",
    re.IGNORECASE,
)


def extract_pay_snippet(*texts: str | None) -> str | None:
    """Pull a short employer pay phrase from a long description when salary_text is empty."""
    for text in texts:
        if not text:
            continue
        match = _PAY_SNIPPET.search(text)
        if match:
            return match.group(0)
        # Fallback: bare $range near "pay"/"salary"
        loose = re.search(
            r"(?:salary|pay|wage).{0,30}\$\s?\d[\d,]*(?:\s*[-–—to]+\s*\$?\s?\d[\d,]*)?",
            text,
            re.IGNORECASE,
        )
        if loose:
            return loose.group(0)
    return None


def parse_salary_text(
    text: str | None,
    *,
    currency: str | None = None,
    period: str | None = None,
    context: str | None = None,
    policy: dict[str, Any] | None = None,
) -> SalarySnapshot:
    raw_in = (text or "").strip()
    if not raw_in:
        snippet = extract_pay_snippet(context)
        if snippet:
            raw_in = snippet
        else:
            hours_only = extract_hours_per_week(context)
            if hours_only is None:
                return SalarySnapshot(published=False)
            return SalarySnapshot(
                published=False,
                hours_per_week=hours_only,
                parse_notes=["hours_found_without_salary"],
            )

    raw = str(raw_in).strip()
    notes: list[str] = []
    lowered = raw.lower()
    if any(token in lowered for token in ("glassdoor", "estimated", "estimate", "typically pays", "average salary")):
        notes.append("ignored_third_party_estimate")
        return SalarySnapshot(published=False, raw_text=raw, estimated=True, parse_notes=notes)

    hours = extract_hours_per_week(raw, context)
    currency_code = detect_currency(raw, currency)
    period_code = detect_period(raw, period)
    up_to = bool(re.search(r"\b(up to|upto|maximum of|max(?:imum)?)\b", lowered))
    from_only = bool(re.search(r"\b(from|starting at|minimum of|min(?:imum)?)\b", lowered) and not up_to)
    if "total compensation" in lowered or "ote" in lowered or "on-target" in lowered:
        notes.append("may_include_variable_pay")

    numbers = _salary_numbers(raw, hours_per_week=hours)
    if not numbers and context and text:
        # Structured salary_text had no numbers — try a body pay snippet.
        snippet = extract_pay_snippet(context)
        if snippet and snippet != raw:
            return parse_salary_text(snippet, currency=currency, period=period, context=context, policy=policy)
    if not numbers:
        return SalarySnapshot(
            published=False,
            raw_text=raw,
            hours_per_week=hours,
            parse_notes=["no_numeric_salary"],
        )

    min_amount: Decimal | None
    max_amount: Decimal | None
    if len(numbers) == 1:
        if up_to:
            min_amount, max_amount = None, numbers[0]
            notes.append("up_to_has_no_lower_bound")
        elif from_only:
            min_amount, max_amount = numbers[0], None
        else:
            min_amount = max_amount = numbers[0]
    else:
        # Prefer the first contiguous pay range; ignore later hours-like leftovers.
        min_amount, max_amount = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
        if up_to and not re.search(_RANGE_SEP, raw):
            min_amount, max_amount = None, numbers[0]
            notes.append("up_to_has_no_lower_bound")

    basis = employment_basis_for(period_code)
    snapshot = SalarySnapshot(
        published=True,
        raw_text=raw,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=currency_code,
        period=period_code,
        hours_per_week=hours,
        employment_basis=basis,
        parse_notes=notes,
    )

    if period_code == "hourly" and hours is None:
        notes.append("hourly_without_stated_hours_monthly_not_assumed")
        snapshot.parse_notes = notes
        return snapshot

    if min_amount is not None:
        monthly = to_monthly(min_amount, period_code, hours_per_week=hours, policy=policy)
        snapshot.min_monthly = monthly
    if max_amount is not None:
        monthly = to_monthly(max_amount, period_code, hours_per_week=hours, policy=policy)
        snapshot.max_monthly = monthly
    if period_code == "hourly" and hours is not None and (
        snapshot.min_monthly is not None or snapshot.max_monthly is not None
    ):
        snapshot.monthly_from_hours = True
        notes.append(f"monthly_from_stated_hours:{hours}")
        snapshot.parse_notes = notes
    return snapshot


def merge_structured_salary(
    *,
    text: str | None,
    min_amount: Decimal | None,
    max_amount: Decimal | None,
    currency: str | None,
    period: str | None,
    context: str | None = None,
    policy: dict[str, Any] | None = None,
) -> SalarySnapshot:
    if min_amount is None and max_amount is None:
        return parse_salary_text(text, currency=currency, period=period, context=context, policy=policy)

    combined = " ".join(p for p in [text or "", context or ""] if p)
    hours = extract_hours_per_week(combined)
    period_code = detect_period(text or period or "annual", period)
    currency_code = detect_currency(combined, currency)
    snapshot = SalarySnapshot(
        published=True,
        raw_text=text,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=currency_code,
        period=period_code,
        hours_per_week=hours,
        employment_basis=employment_basis_for(period_code),
    )
    if period_code == "hourly" and hours is None:
        snapshot.parse_notes.append("hourly_without_stated_hours_monthly_not_assumed")
        return snapshot
    if min_amount is not None:
        snapshot.min_monthly = to_monthly(min_amount, period_code, hours_per_week=hours, policy=policy)
    if max_amount is not None:
        snapshot.max_monthly = to_monthly(max_amount, period_code, hours_per_week=hours, policy=policy)
    if min_amount is None and max_amount is not None:
        snapshot.parse_notes.append("up_to_has_no_lower_bound")
    if period_code == "hourly" and hours is not None:
        snapshot.monthly_from_hours = True
    return snapshot


def lower_bound_monthly(snapshot: SalarySnapshot) -> Decimal | None:
    if snapshot.min_monthly is not None:
        return snapshot.min_monthly
    return None


def format_salary_for_display(snapshot: SalarySnapshot) -> str:
    """Human label for digests — never imply a 40h month from an hourly rate."""
    if not snapshot.published:
        return "Salary: Not published"
    currency = snapshot.currency or ""
    period = snapshot.period or "unknown"

    def _fmt(value: Decimal | None) -> str:
        if value is None:
            return "?"
        if value == value.to_integral_value():
            return f"{value.quantize(Decimal('1')):,}"
        return f"{value.quantize(Decimal('0.01')):,}"

    def _money(value: Decimal | None) -> str:
        return f"{currency} {_fmt(value)}".strip()

    def _range(lo: Decimal | None, hi: Decimal | None) -> str:
        if hi is not None and lo is not None and hi != lo:
            return f"{currency} {_fmt(lo)}–{_fmt(hi)}".strip()
        return _money(lo if lo is not None else hi)

    if period == "hourly":
        rate = _range(snapshot.min_amount, snapshot.max_amount)
        if snapshot.hours_per_week is not None:
            hours = snapshot.hours_per_week
            hours_s = str(hours.quantize(Decimal("1")) if hours == hours.to_integral_value() else hours)
            monthly_bit = ""
            if snapshot.min_monthly is not None:
                monthly_bit = (
                    f" · ≈ {_range(snapshot.min_monthly, snapshot.max_monthly)}/month at stated hours"
                )
            return f"Salary: {rate} per hour · {hours_s} hours/week{monthly_bit}"
        return (
            f"Salary: {rate} per hour · weekly hours not published — "
            "monthly equivalent not calculated"
        )

    if period == "monthly":
        return f"Salary: {_range(snapshot.min_amount, snapshot.max_amount)} per month (fixed monthly)"

    if period == "annual":
        amount = _range(snapshot.min_amount, snapshot.max_amount)
        monthly = ""
        if snapshot.min_monthly is not None:
            monthly = f" · ≈ {_range(snapshot.min_monthly, snapshot.max_monthly)}/month"
        return f"Salary: {amount} per year{monthly}"

    if period == "daily":
        return f"Salary: {_range(snapshot.min_amount, snapshot.max_amount)} per day"

    if snapshot.raw_text:
        return f"Salary: {snapshot.raw_text}"
    return "Salary: Published (see listing)"
