import html

from job_scout.services.salary import format_salary_for_display, parse_salary_text
from job_scout.utils.text import strip_html


def test_strip_html_unescapes_greenhouse_entities():
    raw = (
        "&lt;div class=&quot;content-intro&quot;&gt;&lt;p&gt;"
        "US Pay Range $70,000 &amp;mdash; $100,000 USD"
        "&lt;/p&gt;&lt;/div&gt;"
    )
    text = strip_html(raw)
    assert "<div" not in text
    assert "font-family" not in text
    assert "$70,000" in text
    assert "$100,000" in text


def test_salary_from_description_pay_range():
    description = (
        "Please note that the salary information shown below is a general guideline. "
        "US Pay Range $70,000 — $100,000 USD Full-time employees receive benefits."
    )
    snap = parse_salary_text(None, context=description)
    assert snap.published is True
    assert snap.min_amount == 70000
    assert snap.max_amount == 100000
    assert snap.currency == "USD"
    assert snap.period == "annual"
    label = format_salary_for_display(snap)
    assert "70,000" in label
    assert "100,000" in label


def test_double_escaped_greenhouse_roundtrip():
    raw = html.escape("<p>US Pay Range $80,000 — $95,000 USD</p>")
    text = strip_html(raw)
    snap = parse_salary_text(None, context=text)
    assert snap.published is True
    assert snap.min_amount == 80000
