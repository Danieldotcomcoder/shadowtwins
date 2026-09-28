"""Server settings, read once from the environment.

Credentials are only ever read here and handed to provider adapters; they are never serialized,
logged, returned by the API or written to the database.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


def _int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default


@dataclass(frozen=True)
class RetryPolicy:
    """Fixed policy for eligible transport/server/rate-limit failures (never for answers)."""

    max_attempts: int = 4
    base_delay_s: float = 2.0
    max_delay_s: float = 60.0
    # Rate limits (429) are usually per-minute windows, so they get a slower, longer schedule
    # (15 s, 30 s, 60 s, 120 s, 120 s) and pause the whole run's dispatch for the same time. A provider's
    # Retry-After is honoured up to a day, so a daily quota (e.g. Groq's free plan) makes the run wait
    # for the reset instead of failing its jobs.
    rate_limit_max_attempts: int = 6
    rate_limit_base_delay_s: float = 15.0
    rate_limit_max_delay_s: float = 120.0
    rate_limit_max_retry_after_s: float = 86400.0

    def delay(self, attempt_number: int, retry_after_s: float | None = None) -> float:
        d = min(self.max_delay_s, self.base_delay_s * (2 ** max(0, attempt_number - 1)))
        if retry_after_s is not None:
            d = max(d, min(retry_after_s, self.max_delay_s * 5))
        return d

    def rate_limit_delay(self, attempt_number: int, retry_after_s: float | None = None) -> float:
        d = min(self.rate_limit_max_delay_s, self.rate_limit_base_delay_s * (2 ** max(0, attempt_number - 1)))
        if retry_after_s is not None:
            d = max(d, min(retry_after_s, self.rate_limit_max_retry_after_s))
        return d


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    packs_dir: Path
    frontend_dist: Path
    openrouter_api_key: str | None = field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    groq_api_key: str | None = field(default=None, repr=False)
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_plan: str = "free"  # free | developer: whether Groq bills this account (see providers/groq.py)
    operator_token: str | None = field(default=None, repr=False)
    auth_mode: str = "local"  # token | local | open | readonly
    enable_mock_provider: bool = False
    catalog_ttl_s: float = 3600.0
    http_timeout_s: float = 3600.0  # a long thinking answer on a slow free endpoint can take ~40 min
    connect_timeout_s: float = 20.0
    lease_ttl_s: float = 90.0
    heartbeat_s: float = 5.0
    poll_s: float = 0.5
    worker_concurrency: int = 8
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    max_body_bytes: int = 64 * 1024
    app_title: str = "Shadow Twins"
    worker_stale_after_s: float = 30.0

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)


def load_settings(**overrides: object) -> Settings:
    data_dir = Path(os.environ.get("ST_DATA_DIR", str(ROOT / "data")))
    token = os.environ.get("ST_OPERATOR_TOKEN") or None
    mode = os.environ.get("ST_AUTH_MODE") or ("token" if token else "local")
    values: dict[str, object] = dict(
        data_dir=data_dir,
        db_path=Path(os.environ.get("ST_DB_PATH", str(data_dir / "shadowtwins.db"))),
        packs_dir=Path(os.environ.get("ST_PACKS_DIR", str(ROOT / "packs"))),
        frontend_dist=Path(os.environ.get("ST_FRONTEND_DIST", str(ROOT / "frontend" / "dist"))),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
        openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        groq_api_key=os.environ.get("GROQ_API_KEY") or None,
        groq_base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        groq_plan=(os.environ.get("GROQ_PLAN") or "free").strip().lower(),
        operator_token=token,
        auth_mode=mode,
        enable_mock_provider=_bool("ST_ENABLE_MOCK_PROVIDER", False),
        catalog_ttl_s=_float("ST_CATALOG_TTL_S", 3600.0),
        http_timeout_s=_float("ST_HTTP_TIMEOUT_S", 3600.0),
        lease_ttl_s=_float("ST_LEASE_TTL_S", 90.0),
        worker_concurrency=_int("ST_WORKER_CONCURRENCY", 8),
    )
    values.update(overrides)
    if values["auth_mode"] not in {"token", "local", "open", "readonly"}:
        raise ValueError("ST_AUTH_MODE must be token, local, open or readonly")
    if values["groq_plan"] not in {"free", "developer"}:
        raise ValueError("GROQ_PLAN must be free or developer")
    if values["auth_mode"] == "token" and not values.get("operator_token"):
        raise ValueError("ST_AUTH_MODE=token requires ST_OPERATOR_TOKEN")
    return Settings(**values)  # type: ignore[arg-type]
