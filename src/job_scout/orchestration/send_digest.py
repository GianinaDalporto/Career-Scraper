"""08:00 digest. Never marks jobs notified if Resend send fails."""

from __future__ import annotations

import argparse
import logging

from job_scout.config.settings import get_settings
from job_scout.services.database import InMemoryJobRepository, build_repository
from job_scout.services.email_digest import build_and_maybe_send
from job_scout.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build / send the morning job digest")
    parser.add_argument("--send", action="store_true", help="Send via Resend (requires secrets)")
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--print-html", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.job_scout_log_level)
    if not args.memory and settings.job_scout_env == "github" and not settings.has_supabase():
        logger.error(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required in GitHub mode "
            "(refusing silent in-memory fallback)."
        )
        return 1
    repo = InMemoryJobRepository() if args.memory else build_repository(settings)
    send = bool(args.send or settings.job_scout_send_email)
    if send and not settings.has_resend():
        logger.error("Missing RESEND_API_KEY, RESEND_FROM or DIGEST_TO")
        return 1
    try:
        result = build_and_maybe_send(repo, settings=settings, send=send)
    except Exception:
        logger.exception("Digest send failed; jobs were not marked notified")
        return 1
    if args.print_html:
        print(result["html"])
    logger.info("Digest %s jobs, sent=%s subject=%s", result["summary"], result["sent"], result["subject"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
