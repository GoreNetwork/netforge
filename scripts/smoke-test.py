#!/usr/bin/env python3
"""End-to-end check against a running stack. Uses only the standard library.

Reserves real subnets in Nautobot, labelled smoke-<timestamp>, and leaves them there.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(
    line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line
)
NETFORGE = f"http://127.0.0.1:{ENV.get('NETFORGE_PORT', '8080')}"
NAUTOBOT = f"http://127.0.0.1:{ENV.get('NAUTOBOT_PORT', '8081')}"


def call(url, token_header, method="GET", body=None):
    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": token_header, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def netforge(path, method="GET", body=None):
    return call(f"{NETFORGE}{path}", f"Bearer {ENV['NETFORGE_API_TOKEN']}", method, body)


def nautobot(path):
    return call(f"{NAUTOBOT}{path}", f"Token {ENV['NAUTOBOT_API_TOKEN']}")[1]


def run_task(task_type, variables):
    code, task = netforge("/api/v1/tasks", "POST", {"task_type": task_type, "variables": variables})
    assert code == 201, task
    seen = []
    for _ in range(120):
        code, task = netforge(f"/api/v1/tasks/{task['id']}")
        if task["status"] not in seen:
            seen.append(task["status"])
        if task["status"] in ("succeeded", "failed"):
            return task, seen
        time.sleep(0.5)
    raise SystemExit(f"Timed out: {task}")


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name} {detail}")
    if not ok:
        sys.exit(1)


def main():
    name = f"smoke-{int(time.time())}"

    code, _ = call(f"{NETFORGE}/api/v1/tasks", "Bearer wrong")
    check("API rejects a bad token", code == 401)

    code, body = netforge("/api/v1/tasks", "POST", {"task_type": "build_new_device", "variables": {"device_name": "{{ 7*7 }}"}})
    check("API rejects bad variables", code == 422, json.dumps(body["detail"]))

    task, seen = run_task("build_new_device", {"device_name": name})
    if task["status"] != "succeeded":
        for entry in netforge(f"/api/v1/tasks/{task['id']}/logs")[1]:
            print(entry["line"])
    check("build_new_device succeeded", task["status"] == "succeeded", f"statuses={seen} error={task['error']}")
    prefix = task["result"]["prefix"]

    found = nautobot(f"/api/ipam/prefixes/?prefix={prefix}")["results"]
    check("Nautobot holds the prefix", len(found) == 1, prefix)
    check("Prefix is labelled", found[0]["description"] == name, found[0]["description"])
    status = nautobot(f"/api/extras/statuses/{found[0]['status']['id']}/")
    check("Prefix is Reserved", status["name"] == "Reserved", status["name"])
    check("Prefix is in the pool", prefix.startswith("10.0.") and prefix.endswith("/24"))

    task, _ = run_task("build_new_device", {"device_name": name})
    check(
        "Resubmitting reuses the reservation",
        task["result"]["prefix"] == prefix and task["result"]["already_reserved"] is True,
    )

    task, _ = run_task("build_new_device", {"device_name": name, "prefix_length": 28})
    check("A size mismatch fails", task["status"] == "failed", task["error"])

    other, _ = run_task("build_new_device", {"device_name": f"{name}-b", "prefix_length": 28})
    check("A second device gets a different subnet", other["result"]["prefix"] != prefix, other["result"]["prefix"])

    report, _ = run_task("ip_pool_report", {})
    labels = [item["label"] for item in report["result"]["prefixes"]]
    check("Python engine reports the reservation", name in labels, f"count={report['result']['count']}")

    print("All checks passed.")


if __name__ == "__main__":
    main()
