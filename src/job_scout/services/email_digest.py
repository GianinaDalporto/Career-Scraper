"""Morning HTML digest via Resend (HTTPS API)."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import httpx

from job_scout.config.settings import Settings, get_settings, load_scoring
from job_scout.models.enums import FitCategory, WorkMode
from job_scout.models.job import CanonicalJobRecord
from job_scout.services.database import JobRepository
from job_scout.services.salary import format_salary_for_display
from job_scout.utils.dates import utcnow
from job_scout.utils.text import strip_html

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

MATERIAL_SCORE_DELTA = 8

CardStatus = Literal["new", "updated", "returning"]


@dataclass
class DigestSelection:
    jobs: list[CanonicalJobRecord]
    updated_ids: set[str] = field(default_factory=set)
    new_ids: set[str] = field(default_factory=set)
    returning: list[CanonicalJobRecord] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def salary_label(job: CanonicalJobRecord) -> str:
    if job.work_mode == WorkMode.REMOTE and not job.salary.published:
        return "Salary: Not published — allowed because role is fully remote"
    if not job.salary.published:
        return "Salary: Not published"
    return format_salary_for_display(job.salary)


def job_changed_materially(previous: CanonicalJobRecord | None, current: CanonicalJobRecord) -> bool:
    if previous is None:
        return False
    if (previous.salary.raw_text or "") != (current.salary.raw_text or ""):
        return True
    if previous.closing_date != current.closing_date and current.closing_date:
        return True
    if (previous.direct_employer_url or "") != (current.direct_employer_url or "") and current.direct_employer_url:
        return True
    if (previous.apply_url or "") != (current.apply_url or "") and current.apply_url:
        return True
    if previous.fit_score is not None and current.fit_score is not None:
        if current.fit_score - previous.fit_score >= MATERIAL_SCORE_DELTA:
            return True
    return False


def select_digest_jobs(
    jobs: list[CanonicalJobRecord],
    *,
    previous_by_fp: dict[str, CanonicalJobRecord] | None = None,
    min_category: FitCategory = FitCategory.POSSIBLE,
) -> DigestSelection:
    previous_by_fp = previous_by_fp or {}
    rank = {
        FitCategory.EXCEPTIONAL: 4,
        FitCategory.STRONG: 3,
        FitCategory.GOOD: 2,
        FitCategory.POSSIBLE: 1,
        FitCategory.LOW: 0,
    }
    min_rank = rank[min_category]
    selected: list[CanonicalJobRecord] = []
    updated: set[str] = set()
    new_ids: set[str] = set()
    returning: list[CanonicalJobRecord] = []
    for job in jobs:
        if not job.active or job.rejected:
            continue
        if job.fit_category is None or rank.get(job.fit_category, 0) < min_rank:
            continue
        prev = previous_by_fp.get(job.canonical_fingerprint)
        is_new = job.last_notified_at is None
        changed = bool(job.digest_pending_update)
        if not changed and not is_new:
            changed = job_changed_materially(prev, job)
        if is_new:
            new_ids.add(job.canonical_fingerprint)
            selected.append(job)
            continue
        if changed:
            updated.add(job.canonical_fingerprint)
            selected.append(job)
            continue
        returning.append(job)

    selected.sort(key=lambda item: (-(item.fit_score or 0), item.title))
    returning.sort(key=lambda item: (-(item.fit_score or 0), item.title))
    summary = {
        "included": len(selected),
        "new": len(new_ids),
        "updated": len(updated),
        "returning": len(returning),
        "remote": sum(1 for j in selected if j.work_mode == WorkMode.REMOTE),
        "hybrid": sum(1 for j in selected if j.work_mode == WorkMode.HYBRID),
        "onsite": sum(1 for j in selected if j.work_mode == WorkMode.ONSITE),
        "exceptional": sum(1 for j in selected if j.fit_category == FitCategory.EXCEPTIONAL),
        "strong": sum(1 for j in selected if j.fit_category == FitCategory.STRONG),
        "good": sum(1 for j in selected if j.fit_category == FitCategory.GOOD),
        "possible": sum(1 for j in selected if j.fit_category == FitCategory.POSSIBLE),
    }
    return DigestSelection(
        jobs=selected,
        updated_ids=updated,
        new_ids=new_ids,
        returning=returning,
        summary=summary,
    )


def resolve_apply_url(job: CanonicalJobRecord) -> str:
    for candidate in (job.direct_employer_url, job.apply_url, *(job.source_urls or ())):
        if candidate and str(candidate).strip().startswith("https://"):
            return str(candidate).strip()
        if candidate and str(candidate).strip().startswith("http://"):
            return str(candidate).strip()
    return ""


def apply_url_host(url: str) -> str:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        return ""
    parts = host.lower().split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def job_excerpt(job: CanonicalJobRecord, *, max_chars: int = 220) -> str:
    """One short plain-text blurb for the email card — enough context, not a full advert."""
    text = strip_html(job.description or "")
    text = " ".join(text.split())
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def _status_for(job: CanonicalJobRecord, selection: DigestSelection) -> CardStatus:
    if job.canonical_fingerprint in selection.new_ids:
        return "new"
    if job.canonical_fingerprint in selection.updated_ids:
        return "updated"
    return "returning"


def _status_badge(status: CardStatus) -> str:
    styles = {
        "new": ("NEW", "#0b5fff", "#e8f0ff"),
        "updated": ("UPDATED", "#b45309", "#fff7ed"),
        "returning": ("SEEN BEFORE", "#4b5563", "#f3f4f6"),
    }
    label, fg, bg = styles[status]
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f"font-size:11px;font-weight:bold;letter-spacing:.04em;"
        f'padding:3px 8px;border-radius:4px;margin-right:8px">{label}</span>'
    )


def _card(job: CanonicalJobRecord, status: CardStatus) -> str:
    apply_url = resolve_apply_url(job)
    safe_url = html.escape(apply_url, quote=True) if apply_url else ""
    secondary = ""
    if (
        job.direct_employer_url
        and job.apply_url
        and job.apply_url != job.direct_employer_url
        and job.apply_url.startswith("https://")
    ):
        sec = html.escape(job.apply_url, quote=True)
        sec_host = html.escape(apply_url_host(job.apply_url) or "external")
        secondary = (
            f'<p style="margin:8px 0 0;font-size:13px">'
            f'<a href="{sec}" style="color:#0f6b4c;text-decoration:underline">'
            f"Secondary source ({sec_host})</a></p>"
        )
    reasons = "".join(f"<li>{html.escape(item)}</li>" for item in job.fit_reasons[:3])
    concerns = "".join(f"<li>{html.escape(item)}</li>" for item in job.concerns[:2])
    remote = ""
    if job.work_mode == WorkMode.REMOTE:
        remote = (
            f'<p style="margin:0 0 8px"><strong>Remote eligibility:</strong> '
            f"{html.escape(job.remote_scope.value)}</p>"
        )
    visa = "Unknown" if job.mobility.visa_sponsorship is None else ("Yes" if job.mobility.visa_sponsorship else "No")
    reloc = (
        "Unknown"
        if job.mobility.relocation_assistance is None
        else ("Yes" if job.mobility.relocation_assistance else "No")
    )
    work_auth = html.escape(job.mobility.work_authorisation_notes or "Unknown — not inferred")
    first_seen = job.first_seen_at.date().isoformat() if job.first_seen_at else "Unknown"
    posted = job.date_posted.date().isoformat() if job.date_posted else "Unknown"
    closing = job.closing_date.isoformat() if job.closing_date else "Unknown"
    title_html = html.escape(job.title)
    if safe_url:
        title_html = (
            f'<a href="{safe_url}" style="color:#0f6b4c;text-decoration:none">{title_html}</a>'
        )
    host_label = html.escape(apply_url_host(apply_url) or "external link")
    cta = (
        f'<a href="{safe_url}" style="display:inline-block;background:#0f6b4c;color:#ffffff;'
        f"font-family:Arial,sans-serif;font-size:14px;font-weight:bold;text-decoration:none;"
        f'padding:12px 18px;border-radius:6px">View / apply →</a>'
        f'<div style="margin-top:6px;font-size:12px;color:#666">{host_label} — verify before applying</div>'
        if safe_url
        else '<span style="color:#888">No application URL available</span>'
    )
    excerpt = job_excerpt(job)
    excerpt_html = (
        f'<p style="margin:0 0 10px;font-size:14px;line-height:1.45;color:#333">{html.escape(excerpt)}</p>'
        if excerpt
        else ""
    )
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 16px;border:1px solid #d8d8d8;border-radius:8px;background:#ffffff">
      <tr><td style="padding:16px;font-family:Arial,sans-serif;color:#222">
        <p style="margin:0 0 8px;font-size:12px;color:#555">
          {_status_badge(status)}
          <span style="letter-spacing:.04em">{job.fit_category or ''} · {job.fit_score if job.fit_score is not None else '—'}/100</span>
        </p>
        <h3 style="margin:0 0 8px;font-size:18px;line-height:1.3">{title_html}</h3>
        <p style="margin:0 0 8px"><strong>{html.escape(job.company or 'Unknown company')}</strong><br>
        {html.escape(job.location_text or 'Location unknown')} · {html.escape(job.work_mode.value)}</p>
        {excerpt_html}
        {remote}
        <p style="margin:0 0 8px">{html.escape(salary_label(job))}</p>
        <p style="margin:0 0 8px">Posted: {posted} · Closing: {closing} · First seen: {first_seen}</p>
        <p style="margin:0 0 8px">Visa sponsorship: {visa} · Relocation: {reloc}<br>Work-authorisation: {work_auth}</p>
        <p style="margin:0 0 4px"><strong>Why this fits</strong></p>
        <ul style="margin:0 0 8px;padding-left:18px">{reasons}</ul>
        <p style="margin:0 0 4px"><strong>Gaps / concerns</strong></p>
        <ul style="margin:0 0 14px;padding-left:18px">{concerns or '<li>None recorded</li>'}</ul>
        <p style="margin:0">{cta}</p>
        {secondary}
      </td></tr>
    </table>
    """


def _stat_cell(label: str, value: object, *, fg: str, bg: str, border: str) -> str:
    return f"""
    <td width="25%" valign="top" style="padding:6px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {border};border-radius:8px;background:{bg}">
        <tr><td style="padding:10px 12px;font-family:Arial,sans-serif">
          <div style="font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:{fg};font-weight:bold">{html.escape(label)}</div>
          <div style="font-size:22px;line-height:1.2;color:{fg};font-weight:bold;margin-top:4px">{html.escape(str(value))}</div>
        </td></tr>
      </table>
    </td>
    """


def _stats_table(summary: dict[str, int], health: dict[str, Any]) -> str:
    found = health.get("jobs_found", summary.get("found", 0))
    discarded = health.get("jobs_discarded", summary.get("discarded", 0))
    cells = [
        _stat_cell("Found (recent scrapes)", found, fg="#1d4ed8", bg="#eff6ff", border="#bfdbfe"),
        _stat_cell("Discarded (recent)", discarded, fg="#4b5563", bg="#f3f4f6", border="#d1d5db"),
        _stat_cell("New", summary.get("new", 0), fg="#0f766e", bg="#f0fdfa", border="#99f6e4"),
        _stat_cell("Updated", summary.get("updated", 0), fg="#b45309", bg="#fff7ed", border="#fdba74"),
        _stat_cell("Remote", summary.get("remote", 0), fg="#0f6b4c", bg="#f3faf6", border="#c5ddd2"),
        _stat_cell("Hybrid", summary.get("hybrid", 0), fg="#92400e", bg="#fffbeb", border="#fcd34d"),
        _stat_cell("On-site", summary.get("onsite", 0), fg="#9f1239", bg="#fff1f2", border="#fda4af"),
        _stat_cell("Perfect match", summary.get("exceptional", 0), fg="#6d28d9", bg="#f5f3ff", border="#c4b5fd"),
    ]
    row1 = "".join(cells[:4])
    row2 = "".join(cells[4:])
    returning = summary.get("returning", 0)
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 8px">
      <tr>{row1}</tr>
      <tr>{row2}</tr>
    </table>
    <p style="margin:4px 0 0;font-size:12px;color:#555;font-family:Arial,sans-serif">
      Still open from earlier digests (not re-listed above): {returning}
    </p>
    """


def _returning_section(jobs: list[CanonicalJobRecord], *, limit: int = 12) -> str:
    if not jobs:
        return ""
    rows = []
    for job in jobs[:limit]:
        url = resolve_apply_url(job)
        title = html.escape(job.title)
        company = html.escape(job.company or "Unknown")
        score = job.fit_score if job.fit_score is not None else "—"
        if url:
            safe = html.escape(url, quote=True)
            title = f'<a href="{safe}" style="color:#0f6b4c;text-decoration:none">{title}</a>'
        rows.append(
            f'<li style="margin:0 0 8px">{_status_badge("returning")} '
            f"<strong>{title}</strong> — {company} · {job.fit_category or ''} {score}/100</li>"
        )
    more = ""
    if len(jobs) > limit:
        more = f'<p style="margin:8px 0 0;color:#555;font-size:13px">+{len(jobs) - limit} more still open.</p>'
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px">
      <tr><td style="background:#4b5563;color:#fff;padding:10px 14px;font-family:Arial,sans-serif;font-size:16px;font-weight:bold">STILL OPEN (seen before)</td></tr>
      <tr><td style="padding:12px 14px;font-family:Arial,sans-serif;background:#ffffff;border:1px solid #d8d8d8;border-top:0">
        <p style="margin:0 0 10px;font-size:13px;color:#555">Previously emailed matches that remain active. Not counted in New/Updated above.</p>
        <ul style="margin:0;padding-left:18px">{''.join(rows)}</ul>
        {more}
      </td></tr>
    </table>
    """


def render_digest_html(
    selection: DigestSelection,
    *,
    health: dict[str, Any],
    digest_date: date | None = None,
) -> str:
    digest_date = digest_date or utcnow().date()
    sections = []
    for mode, title, colour in (
        (WorkMode.REMOTE, "REMOTE", "#0f6b4c"),
        (WorkMode.HYBRID, "HYBRID", "#8a5a00"),
        (WorkMode.ONSITE, "ON-SITE", "#6b1f3b"),
    ):
        cards = [
            _card(job, _status_for(job, selection))
            for job in selection.jobs
            if job.work_mode == mode
        ]
        body = "".join(cards) or (
            '<p style="font-family:Arial,sans-serif;color:#555">No new or updated matches in this section.</p>'
        )
        sections.append(
            f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px">
              <tr><td style="background:{colour};color:#fff;padding:10px 14px;font-family:Arial,sans-serif;font-size:16px;font-weight:bold">{title}</td></tr>
              <tr><td style="padding:12px 0 0">{body}</td></tr>
            </table>
            """
        )
    sections.append(_returning_section(selection.returning))
    failed = [str(item) for item in (health.get("failed_sources") or []) if item]
    stale = [str(item) for item in (health.get("stale_sources") or []) if item]
    last_scrape = health.get("last_successful_scrape") or "unknown"
    summary = selection.summary
    sources_ok = health.get("sources_ok", 0)
    sources_failed = health.get("sources_failed", 0)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Job Scout</title></head>
<body style="margin:0;padding:0;background:#f3f3f3">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f3f3">
    <tr><td align="center" style="padding:16px">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">
        <tr><td style="font-family:Arial,sans-serif;padding:8px 0 12px">
          <h1 style="margin:0 0 12px;font-size:22px;color:#1a1a1a">Daily Job Scout — {digest_date.strftime('%d %b %Y')}</h1>
          {_stats_table(summary, health)}
          <p style="margin:8px 0 0;font-size:13px;color:#333;font-family:Arial,sans-serif">
            In this email: {summary.get('included', 0)}
            · New {summary.get('new', 0)}
            · Updated {summary.get('updated', 0)}
            · Exceptional {summary.get('exceptional', 0)}
            · Strong {summary.get('strong', 0)}
            · Good {summary.get('good', 0)}
            · Possible {summary.get('possible', 0)}
            · Sources {sources_ok} ok / {sources_failed} failed
          </p>
        </td></tr>
        <tr><td>{''.join(sections)}</td></tr>
        <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:#555;padding:12px 0 24px">
          <p><strong>System health</strong><br>
          Last successful scrape: {html.escape(str(last_scrape))}<br>
          Failed sources: {html.escape(', '.join(failed) or 'none')}<br>
          Stale sources: {html.escape(', '.join(stale) or 'none')}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>
"""


def subject_line(selection: DigestSelection, digest_date: date | None = None) -> str:
    digest_date = digest_date or utcnow().date()
    strong = selection.summary.get("exceptional", 0) + selection.summary.get("strong", 0)
    included = selection.summary.get("included", 0)
    date_s = digest_date.strftime("%d %b %Y")
    if strong > 0:
        return f"Daily Job Scout — {strong} Strong Matches | {date_s}"
    return f"Daily Job Scout — {included} Matches | {date_s}"


def send_resend(subject: str, html_body: str, settings: Settings) -> dict[str, Any]:
    if not settings.has_resend():
        raise RuntimeError(
            "Resend settings are incomplete. Set RESEND_API_KEY, RESEND_FROM and DIGEST_TO."
        )
    payload = {
        "from": settings.resend_from,
        "to": [settings.digest_to],
        "subject": subject,
        "html": html_body,
        "text": "This digest is HTML. Open it in an HTML-capable client.",
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(RESEND_API_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"Resend API error {response.status_code}: {response.text}")
        data = response.json()
    logger.info("Resend accepted digest email id=%s", data.get("id"))
    return data if isinstance(data, dict) else {"raw": data}


def build_and_maybe_send(
    repo: JobRepository,
    *,
    settings: Settings | None = None,
    send: bool = False,
    extra_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    scoring = load_scoring(settings)
    min_score = int(scoring.get("low_score_cutoff", 60))
    min_name = str(scoring.get("digest_minimum_category") or "Possible")
    try:
        min_category = FitCategory(min_name)
    except ValueError:
        min_category = FitCategory.POSSIBLE
    jobs = repo.list_digest_candidates(repo.last_digest_at(), min_score)
    previous = {job.canonical_fingerprint: job for job in jobs if job.last_notified_at}
    selection = select_digest_jobs(jobs, previous_by_fp=previous, min_category=min_category)
    health = {
        "sources_ok": 0,
        "sources_failed": 0,
        "failed_sources": [],
        "stale_sources": [],
        "last_successful_scrape": repo.last_successful_scrape(),
        "new_jobs": selection.summary.get("new", 0),
        "jobs_found": 0,
        "jobs_discarded": 0,
    }
    try:
        totals = repo.recent_scrape_totals()
        health["jobs_found"] = totals.get("jobs_found", 0)
        health["jobs_discarded"] = totals.get("jobs_discarded", 0)
        if totals.get("jobs_new") is not None:
            health["pipeline_new"] = totals["jobs_new"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load scrape totals for digest header: %s", exc)
    for row in repo.list_source_health():
        if row.get("consecutive_failures", 0) > 0 or row.get("status") == "failure":
            health["sources_failed"] += 1
            health["failed_sources"].append(row.get("source"))
        else:
            health["sources_ok"] += 1
        if row.get("consecutive_failures", 0) >= 2:
            health["stale_sources"].append(row.get("source"))
    if extra_health:
        health.update(extra_health)
    html_body = render_digest_html(selection, health=health)
    subject = subject_line(selection)
    result = {
        "subject": subject,
        "html": html_body,
        "jobs": [job.canonical_fingerprint for job in selection.jobs],
        "returning_jobs": [job.canonical_fingerprint for job in selection.returning],
        "summary": selection.summary,
        "sent": False,
    }
    if send:
        send_resend(subject, html_body, settings)
        when = utcnow()
        # Mark both featured and still-open listings that appeared in this email.
        repo.mark_notified([*result["jobs"], *result["returning_jobs"]], when)
        repo.record_digest_run(
            {
                "digest_date": when.date(),
                "generated_at": when,
                "jobs_included": len(result["jobs"]),
                "delivery_status": "sent",
                "recipient": settings.digest_to,
            }
        )
        result["sent"] = True
    else:
        repo.record_digest_run(
            {
                "digest_date": utcnow().date(),
                "generated_at": utcnow(),
                "jobs_included": len(result["jobs"]),
                "delivery_status": "dry_run",
                "recipient": settings.digest_to or "unset",
            }
        )
    return result
