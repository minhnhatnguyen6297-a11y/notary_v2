import logging
import os
from logging.handlers import RotatingFileHandler


_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _parse_log_level(raw: str) -> int:
    name = (raw or "INFO").strip().upper()
    return getattr(logging, name, logging.INFO)


def _ensure_handler(
    logger: logging.Logger,
    handler_type: type,
    *,
    target_path: str | None = None,
    level: int,
) -> None:
    for h in logger.handlers:
        if not isinstance(h, handler_type):
            continue
        if target_path is None:
            return
        if getattr(h, "baseFilename", None) == target_path:
            return

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    if target_path is None:
        handler = logging.StreamHandler()
    else:
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        handler = RotatingFileHandler(
            target_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def configure_process_logging(service_name: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    level = _parse_log_level(os.getenv("LOG_LEVEL", "INFO"))
    file_path = os.path.join(logs_dir, f"{service_name}.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    _ensure_handler(root_logger, logging.StreamHandler, level=level)
    _ensure_handler(root_logger, RotatingFileHandler, target_path=file_path, level=level)

    return file_path
