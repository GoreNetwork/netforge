"""Runtime configuration. Everything comes from the environment so the same
image runs under Compose or Kubernetes."""
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ["DATABASE_URL"])
    redis_url: str = field(default_factory=lambda: os.environ["REDIS_URL"])
    automations_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("NETFORGE_AUTOMATIONS_DIR", "/app/automations"))
    )
    api_token: str = field(default_factory=lambda: os.environ.get("NETFORGE_API_TOKEN", ""))
    nautobot_public_url: str = field(default_factory=lambda: os.environ.get("NAUTOBOT_PUBLIC_URL", ""))
    worker_engines: list[str] = field(
        default_factory=lambda: _csv(os.environ.get("WORKER_ENGINES", "ansible,python"))
    )
    heartbeat_seconds: int = field(default_factory=lambda: int(os.environ.get("WORKER_HEARTBEAT_SECONDS", "10")))
    stale_seconds: int = field(default_factory=lambda: int(os.environ.get("WORKER_STALE_SECONDS", "60")))
    sweep_seconds: int = field(default_factory=lambda: int(os.environ.get("WORKER_SWEEP_SECONDS", "15")))


@lru_cache
def get_settings() -> Settings:
    return Settings()
