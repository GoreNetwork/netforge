"""Step 1: turn the latest config backup into data. Never contacts Nautobot."""
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

BACKUP_ROOT = Path("/backups")
ADDRESS = re.compile(r"ip address (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+)(?: secondary)?$")
INTERFACE_TYPES = {
    "FastEthernet": "100base-tx",
    "GigabitEthernet": "1000base-t",
    "Loopback": "virtual",
    "Tunnel": "virtual",
    "Vlan": "virtual",
}


def interface_type(name: str) -> str:
    return INTERFACE_TYPES.get(re.match(r"[A-Za-z-]*", name).group(), "other")


def parse_config(device: str, text: str) -> list[dict]:
    """Return every interface in an IOS config."""
    interfaces: list[dict] = []
    current = None
    for line in text.splitlines():
        if line.startswith("interface "):
            name = line.split()[1]
            current = {
                "device": device,
                "name": name,
                "type": interface_type(name),
                "enabled": True,
                "description": "",
                "addresses": [],
            }
            interfaces.append(current)
        elif current is None:
            continue
        elif not line.startswith(" "):
            current = None
        elif line == " shutdown":
            current["enabled"] = False
        elif line.startswith(" description "):
            current["description"] = line.removeprefix(" description ")
        elif match := ADDRESS.fullmatch(line.strip()):
            address = ipaddress.ip_interface("/".join(match.groups()))
            current["addresses"].append(
                {"address": address.with_prefixlen, "prefix": str(address.network)}
            )
    return interfaces


def latest_backup(root: Path) -> Path | None:
    folders = [path for path in root.iterdir() if path.is_dir()]
    return max(folders, key=lambda path: path.name, default=None)


def main() -> None:
    folder = latest_backup(BACKUP_ROOT)
    if folder is None:
        sys.exit("No backups found. Run the backup task first.")

    interfaces: list[dict] = []
    for path in sorted(folder.glob("*.cfg")):
        parsed = parse_config(path.stem, path.read_text(encoding="utf-8"))
        addressed = sum(1 for interface in parsed if interface["addresses"])
        print(f"{path.stem}: {len(parsed)} interfaces, {addressed} with an IP address")
        interfaces.extend(parsed)

    print(f"Read backup {folder.name}")
    output = {"backup": folder.name, "interfaces": interfaces}
    Path(os.environ["NETFORGE_OUTPUT_FILE"]).write_text(json.dumps(output), encoding="utf-8")


if __name__ == "__main__":
    main()
