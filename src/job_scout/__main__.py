"""python -m job_scout scrape|digest|health"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-scout")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scrape", help="Run enabled job pipelines")
    sub.add_parser("digest", help="Build and optionally send the morning digest")
    sub.add_parser("health", help="Supabase / schema health check")
    args, rest = parser.parse_known_args(argv)

    if args.command == "scrape":
        from job_scout.orchestration.run_scrapers import main as scrape_main

        return scrape_main(rest)
    if args.command == "digest":
        from job_scout.orchestration.send_digest import main as digest_main

        return digest_main(rest)
    from job_scout.orchestration.health_check import main as health_main

    return health_main(rest)


if __name__ == "__main__":
    sys.exit(main())
