"""Process startup: logging, migrations, pack sync and the shared context."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import db, packsync
from .config import Settings, load_settings
from .context import AppContext
from .providers.base import Provider

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _RedactSecrets(logging.Filter):
    """Belt and braces: scrub configured secrets from any log record."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if self.secrets:
            msg = record.getMessage()
            for s in self.secrets:
                msg = msg.replace(s, "***")
            record.msg, record.args = msg, ()
        return True


def configure_logging(settings: Settings, component: str) -> None:
    root = logging.getLogger()
    if getattr(root, "_st_configured", False):
        return
    root.setLevel(logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    log_dir = settings.data_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / f"{component}.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    redact = _RedactSecrets([settings.openrouter_api_key or "", settings.operator_token or ""])
    for h in handlers:
        h.setFormatter(logging.Formatter(_LOG_FORMAT))
        h.addFilter(redact)
        root.addHandler(h)
    # httpx logs full URLs at INFO; keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root._st_configured = True  # type: ignore[attr-defined]


def prepare_database(settings: Settings) -> dict[str, object]:
    conn = db.connect(settings.db_path)
    try:
        applied = db.migrate(conn)
        report = packsync.sync_packs(conn, settings.packs_dir)
    finally:
        conn.close()
    return {"migrations_applied": applied, "packs": report}


def startup(settings: Settings | None = None, run_migrations: bool = True, component: str = "api",
            providers: dict[str, Provider] | None = None) -> AppContext:
    settings = settings or load_settings()
    configure_logging(settings, component)
    if run_migrations:
        prepare_database(settings)
    else:
        conn = db.connect(settings.db_path)
        try:
            if db.schema_version(conn) < db.latest_migration():
                raise RuntimeError("database schema is behind; run `benchserver migrate` first")
        finally:
            conn.close()
    return AppContext(settings, providers)
