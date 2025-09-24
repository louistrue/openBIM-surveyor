import logging
import logging.handlers
import os
import sys
from pathlib import Path


LOG_FOLDER_NAME = "logs"


def get_base_dir() -> Path:
    """Return directory suitable for storing runtime artifacts."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def setup_logging(app_name: str) -> Path:
    """Configure RotatingFileHandler and return log file path."""
    base_dir = get_base_dir()
    logs_dir = base_dir / LOG_FOLDER_NAME
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    log_file = logs_dir / f"{app_name.lower().replace(' ', '_')}.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if not getattr(sys, "frozen", False):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logging.info("Logging initialised for %s", app_name)
    return log_file


def open_logs_folder() -> None:
    """Open the logs folder using the platform-specific file explorer."""
    logs_dir = get_base_dir() / LOG_FOLDER_NAME
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(logs_dir))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess

            subprocess.run(["open", str(logs_dir)], check=False)
        else:
            import subprocess

            subprocess.run(["xdg-open", str(logs_dir)], check=False)
    except Exception as exc:  # pragma: no cover - OS specific behaviour
        logging.exception("Failed to open logs folder: %s", exc)


