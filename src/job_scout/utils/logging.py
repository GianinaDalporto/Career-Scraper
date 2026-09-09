"""Process-wide logging. Import configure_logging() from every CLI entrypoint."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(numeric)
        for handler in root.handlers:
            handler.setLevel(numeric)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.setLevel(numeric)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
