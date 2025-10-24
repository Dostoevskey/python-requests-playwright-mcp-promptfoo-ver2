"""Convenience logger helpers used throughout the test suite."""
from __future__ import annotations

import logging
import os
from typing import Optional


def configure_logging(force: bool = False, level: Optional[int] = None) -> None:
    """Configure the root logger for pytest runs, respecting `LOG_LEVEL` env."""
    log_level = level or getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        force=force,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger."""
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]
