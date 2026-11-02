"""Create the Nautobot data the shipped tasks rely on. Safe to run repeatedly."""
import os
import sys

import httpx

PARENT_PREFIX = "10.0.0.0/16"


def main() -> None:
    client = httpx.Client(
        base_url=f"{os.environ['NAUTOBOT_URL']}/api",
        headers={"Authorization": f"Token {os.environ['NAUTOBOT_TOKEN']}"},
        timeout=30,
    )

    def lookup(path: str, **params: str) -> dict | None:
        response = client.get(path, params=params)
        response.raise_for_status()
        results = response.json()["results"]
        return results[0] if results else None

    if lookup("/ipam/prefixes/", prefix=PARENT_PREFIX):
        print(f"{PARENT_PREFIX} already exists")
        return

    status = lookup("/extras/statuses/", name="Active")
    namespace = lookup("/ipam/namespaces/", name="Global")
    if not status or not namespace:
        sys.exit("Nautobot is missing the default Active status or Global namespace")

    response = client.post(
        "/ipam/prefixes/",
        json={
            "prefix": PARENT_PREFIX,
            "type": "container",
            "status": status["id"],
            "namespace": namespace["id"],
            "description": "Netforge allocation pool",
        },
    )
    response.raise_for_status()
    print(f"Created {PARENT_PREFIX}")


if __name__ == "__main__":
    main()
