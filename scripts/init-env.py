#!/usr/bin/env python3
"""Create .env with random secrets. Never overwrites an existing file."""
import secrets
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

SECRETS = [
    "TASKS_DB_PASSWORD",
    "QUEUE_REDIS_PASSWORD",
    "NAUTOBOT_DB_PASSWORD",
    "NAUTOBOT_REDIS_PASSWORD",
    "NAUTOBOT_SUPERUSER_PASSWORD",
    "NETFORGE_API_TOKEN",
]


def main() -> None:
    if ENV_FILE.exists():
        print(f"{ENV_FILE} already exists; leaving it alone.")
        return
    lines = [f"{name}={secrets.token_hex(24)}" for name in SECRETS]
    lines.append(f"NAUTOBOT_SECRET_KEY={secrets.token_hex(32)}")
    # Nautobot API tokens are exactly 40 characters.
    lines.append(f"NAUTOBOT_API_TOKEN={secrets.token_hex(20)}")
    lines += ["NETFORGE_PORT=8080", "NAUTOBOT_PORT=8081"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {ENV_FILE}")


if __name__ == "__main__":
    main()
