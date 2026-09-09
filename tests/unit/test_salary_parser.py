from decimal import Decimal

import pytest

from job_scout.services.salary import (
    extract_hours_per_week,
    format_salary_for_display,
    parse_salary_text,
    to_monthly,
)


@pytest.mark.parametrize(
    "text,currency,period,min_m,max_m",
    [
        ("R70,000 per month", "ZAR", "monthly", Decimal("70000"), Decimal("70000")),
        ("ZAR 70k pm", "ZAR", "monthly", Decimal("70000"), Decimal("70000")),
        ("$80,000–$120,000 per year", "USD", "annual", Decimal("80000") / 12, Decimal("120000") / 12),
        ("€5,000/month", "EUR", "monthly", Decimal("5000"), Decimal("5000")),
        ("AUD 150,000 p.a.", "AUD", "annual", Decimal("150000") / 12, Decimal("150000") / 12),
        ("£500/day", "GBP", "daily", to_monthly(Decimal("500"), "daily"), to_monthly(Decimal("500"), "daily")),
        ("from R80,000 per month", "ZAR", "monthly", Decimal("80000"), None),
        ("USD 90k per year", "USD", "annual", Decimal("90000") / 12, Decimal("90000") / 12),
    ],
)
def test_salary_formats(text, currency, period, min_m, max_m):
    snap = parse_salary_text(text)
    assert snap.published is True
    assert snap.currency == currency
    assert snap.period == period
    if min_m is not None:
        assert snap.min_monthly == min_m.quantize(Decimal("0.01")) if snap.period != "monthly" else snap.min_monthly == min_m or abs(snap.min_monthly - min_m) < Decimal("0.05")
    else:
        assert snap.min_monthly is None
    if max_m is None:
        assert snap.max_monthly is None or snap.min_monthly is not None


def test_hourly_without_hours_does_not_assume_40h_week():
    snap = parse_salary_text("$60/hour")
    assert snap.period == "hourly"
    assert snap.min_amount == Decimal("60")
    assert snap.min_monthly is None
    assert snap.hours_per_week is None
    assert "hourly_without_stated_hours_monthly_not_assumed" in snap.parse_notes


def test_hourly_with_stated_part_time_hours():
    snap = parse_salary_text(
        "USD 80–130 per hour",
        context="Clean Energy Mechanical Design Engineer. ±15 hours a week. Fully remote.",
    )
    assert snap.period == "hourly"
    assert snap.min_amount == Decimal("80")
    assert snap.max_amount == Decimal("130")
    assert snap.hours_per_week == Decimal("15")
    assert snap.min_monthly == (Decimal("80") * 15 * 52 / 12).quantize(Decimal("0.01"))
    assert snap.max_monthly == (Decimal("130") * 15 * 52 / 12).quantize(Decimal("0.01"))
    assert snap.monthly_from_hours is True


def test_extract_hours_variants():
    assert extract_hours_per_week("about 15 hours per week") == Decimal("15")
    assert extract_hours_per_week("±15 hours a week") == Decimal("15")
    assert extract_hours_per_week("~12.5 hrs/week") == Decimal("12.5")


def test_display_hourly_with_hours():
    snap = parse_salary_text(
        "$80-130 / hour",
        context="Part-time role, ±15 hours a week",
    )
    label = format_salary_for_display(snap)
    assert "per hour" in label
    assert "15 hours/week" in label
    assert "at stated hours" in label
    assert "40" not in label


def test_display_hourly_without_hours():
    snap = parse_salary_text("$80-130 per hour")
    label = format_salary_for_display(snap)
    assert "per hour" in label
    assert "weekly hours not published" in label
    assert "not calculated" in label


def test_display_fixed_monthly():
    snap = parse_salary_text("R80,000 per month")
    assert "fixed monthly" in format_salary_for_display(snap)


def test_up_to_has_no_lower_bound():
    snap = parse_salary_text("up to R90,000 per month")
    assert snap.published is True
    assert snap.min_monthly is None
    assert snap.max_monthly == Decimal("90000")
    assert "up_to_has_no_lower_bound" in snap.parse_notes


def test_glassdoor_estimate_rejected():
    snap = parse_salary_text("Glassdoor estimate $120,000 per year")
    assert snap.published is False
    assert snap.estimated is True


def test_range_lower_bound_used():
    snap = parse_salary_text("R60,000-R90,000 per month")
    assert snap.min_monthly == Decimal("60000")
    assert snap.max_monthly == Decimal("90000")


def test_daily_math_unchanged():
    daily = to_monthly(Decimal("400"), "daily")
    assert daily == (Decimal("400") * 5 * 52 / 12).quantize(Decimal("0.01"))


def test_hourly_to_monthly_requires_hours():
    assert to_monthly(Decimal("50"), "hourly") is None
    assert to_monthly(Decimal("50"), "hourly", hours_per_week=Decimal("15")) == (
        Decimal("50") * 15 * 52 / 12
    ).quantize(Decimal("0.01"))
