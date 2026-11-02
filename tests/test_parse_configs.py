import importlib.util
from pathlib import Path

import pytest

from netforge.catalog import CatalogError, load_catalog

AUTOMATIONS = Path(__file__).resolve().parent.parent / "automations"
SCRIPT = AUTOMATIONS / "tasks" / "sync_nautobot_from_backups" / "parse_configs.py"

spec = importlib.util.spec_from_file_location("parse_configs", SCRIPT)
parse_configs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parse_configs)

CONFIG = """Building configuration...

hostname R1
!
username dhimes privilege 15 password 0 not-an-interface
!
interface FastEthernet0/0
 description To the lab LAN
 ip address 192.168.1.138 255.255.255.0
 ip address 192.168.9.1 255.255.255.128 secondary
 duplex auto
!
interface FastEthernet0/1
 no ip address
 shutdown
!
interface Serial3/0
 ip address dhcp
!
interface Loopback0
 ip address 1.1.1.1 255.255.255.255
!
router ospf 1
 network 0.0.0.0 255.255.255.255 area 0
!
line vty 0 4
 login local
!
end
"""


def by_name():
    return {item["name"]: item for item in parse_configs.parse_config("R1", CONFIG)}


def test_finds_every_interface_and_nothing_else():
    assert list(by_name()) == ["FastEthernet0/0", "FastEthernet0/1", "Serial3/0", "Loopback0"]


def test_reads_addresses_including_secondaries():
    assert by_name()["FastEthernet0/0"]["addresses"] == [
        {"address": "192.168.1.138/24", "prefix": "192.168.1.0/24"},
        {"address": "192.168.9.1/25", "prefix": "192.168.9.0/25"},
    ]


def test_reads_state_and_description():
    interfaces = by_name()
    assert interfaces["FastEthernet0/0"]["description"] == "To the lab LAN"
    assert interfaces["FastEthernet0/0"]["enabled"] is True
    assert interfaces["FastEthernet0/1"]["enabled"] is False


def test_interface_without_a_static_address_has_none():
    assert by_name()["FastEthernet0/1"]["addresses"] == []
    assert by_name()["Serial3/0"]["addresses"] == []


def test_router_network_statement_is_not_read_as_an_interface_address():
    assert by_name()["Loopback0"]["addresses"] == [
        {"address": "1.1.1.1/32", "prefix": "1.1.1.1/32"}
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("FastEthernet0/0", "100base-tx"),
        ("GigabitEthernet0/1", "1000base-t"),
        ("Vlan1", "virtual"),
        ("Serial3/0", "other"),
    ],
)
def test_interface_types(name, expected):
    assert parse_configs.interface_type(name) == expected


def test_latest_backup_is_the_newest_folder(tmp_path):
    assert parse_configs.latest_backup(tmp_path) is None
    (tmp_path / "2026-11-02_162816").mkdir()
    (tmp_path / "2026-11-03_010203").mkdir()
    (tmp_path / "notes.txt").write_text("")
    assert parse_configs.latest_backup(tmp_path).name == "2026-11-03_010203"


def write_task(tmp_path, body):
    folder = tmp_path / "tasks" / "t"
    folder.mkdir(parents=True)
    (folder / "task.yml").write_text(body)


def test_pipeline_needs_steps(tmp_path):
    write_task(tmp_path, "title: t\nengine: pipeline\n")
    with pytest.raises(CatalogError, match="needs steps"):
        load_catalog(tmp_path)


def test_pipeline_cannot_nest(tmp_path):
    body = "title: t\nengine: pipeline\nsteps:\n  - {engine: pipeline, entrypoint: a.yml}\n"
    write_task(tmp_path, body)
    with pytest.raises(CatalogError, match="can't contain"):
        load_catalog(tmp_path)


def test_other_engines_still_need_an_entrypoint(tmp_path):
    write_task(tmp_path, "title: t\nengine: python\n")
    with pytest.raises(CatalogError, match="entrypoint is required"):
        load_catalog(tmp_path)
