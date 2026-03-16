"""Centralized logging setup for module and master logs."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: str, log_level: str = "INFO") -> None:
    """Configure root logging with a master file handler.

    The master log aggregates every module logger entry.
    """
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers on repeated startup calls.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    master_handler = logging.FileHandler(path / "project_master.log", encoding="utf-8")
    master_handler.setFormatter(formatter)
    root_logger.addHandler(master_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_module_logger(module_name: str, log_dir: str, file_name: str) -> logging.Logger:
    """Get a logger that writes to module log and master log."""
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(module_name)
    logger.setLevel(logging.INFO)
    logger.propagate = True

    full_path = str(path / file_name)
    existing_files = {
        getattr(handler, "baseFilename", "")
        for handler in logger.handlers
        if isinstance(handler, logging.FileHandler)
    }

    if full_path not in existing_files:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        file_handler = logging.FileHandler(full_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
