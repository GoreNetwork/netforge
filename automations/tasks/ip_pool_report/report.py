"""Example of the python engine: read variables, log to stdout, write a result."""
import json
import os
from pathlib import Path

import httpx

variables = json.loads(Path(os.environ["NETFORGE_VARS_FILE"]).read_text())
pool = variables["pool"]

response = httpx.get(
    f"{os.environ['NAUTOBOT_URL']}/api/ipam/prefixes/",
    params={"within": pool, "limit": 1000},
    headers={"Authorization": f"Token {os.environ['NAUTOBOT_TOKEN']}"},
    timeout=30,
)
response.raise_for_status()

prefixes = [
    {"prefix": item["prefix"], "label": item["description"]}
    for item in response.json()["results"]
]
for item in prefixes:
    print(f"{item['prefix']:<20} {item['label']}")
print(f"{len(prefixes)} subnet(s) reserved from {pool}")

output = {"pool": pool, "count": len(prefixes), "prefixes": prefixes}
Path(os.environ["NETFORGE_OUTPUT_FILE"]).write_text(json.dumps(output))
