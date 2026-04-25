import logging
import os
from logging.handlers import RotatingFileHandler

from app.config import LOG_FILE, LOG_FORMAT


# Third-party libs that emit DEBUG noise we never want in our logs.
# `hpack`, `h2`, `h11` are the HTTP/2 protocol libs that were flooding the log
# with header-encoding/decoding traces.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "hpack",
    "h2",
    "h11",
    "urllib3",
    "requests",
    "anthropic",
    "supabase",
    "postgrest",
    "gotrue",
    "realtime",
    "storage3",
    "googlemaps",
)


def setup_logging() -> None:
    """Configure root logger once at application startup.

    Strategy:
    - Root logger at INFO (drops third-party DEBUG at the source).
    - Our own `app.*` loggers stay at DEBUG so internal traces survive.
    - Known-noisy libs are explicitly pinned to WARNING as belt-and-braces.
    - File handler rotates at 10MB, keeps 5 archives.
    """
    os.makedirs("logs", exist_ok=True)
    fmt = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,   # 10 MB per file
        backupCount=5,                # keep 5 archives → 60 MB cap total
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)

    # Root at INFO — third-party DEBUG never makes it to the handlers.
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

    # Our own modules keep DEBUG visibility.
    logging.getLogger("app").setLevel(logging.DEBUG)

    # Pin known-noisy libs to WARNING.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
