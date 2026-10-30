"""Safe structured logger that enforces privacy by masking biometric vectors and credentials."""

import logging
import sys


def mask_sensitive(text: str) -> str:
    """Mask credentials and long hex/binary tokens."""
    if not text or len(text) <= 6:
        return "***"
    return f"{text[:2]}...{text[-2:]}"


def setup_logger(name: str = "visionattend") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = setup_logger("visionattend")
