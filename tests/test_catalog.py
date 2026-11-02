from pathlib import Path

import pytest

from netforge.catalog import ValidationFailed, load_catalog

AUTOMATIONS = Path(__file__).resolve().parent.parent / "automations"


@pytest.fixture
def build_device():
    return load_catalog(AUTOMATIONS)["build_new_device"]


def test_shipped_tasks_load():
    catalog = load_catalog(AUTOMATIONS)
    assert {"build_new_device", "ip_pool_report"} <= catalog.keys()


def test_default_is_applied(build_device):
    assert build_device.validate({"device_name": "sw1"}) == {"device_name": "sw1", "prefix_length": 24}


def test_form_strings_become_integers(build_device):
    assert build_device.validate({"device_name": "sw1", "prefix_length": "28"})["prefix_length"] == 28


@pytest.mark.parametrize(
    ("submitted", "field"),
    [
        ({}, "device_name"),
        ({"device_name": ""}, "device_name"),
        ({"device_name": "{{ lookup('pipe', 'id') }}"}, "device_name"),
        ({"device_name": "bad\nname"}, "device_name"),
        ({"device_name": 7}, "device_name"),
        ({"device_name": "sw1", "prefix_length": 16}, "prefix_length"),
        ({"device_name": "sw1", "prefix_length": 31}, "prefix_length"),
        ({"device_name": "sw1", "prefix_length": "abc"}, "prefix_length"),
        ({"device_name": "sw1", "prefix_length": True}, "prefix_length"),
        ({"device_name": "sw1", "surprise": "x"}, "surprise"),
    ],
)
def test_bad_input_is_rejected(build_device, submitted, field):
    with pytest.raises(ValidationFailed) as caught:
        build_device.validate(submitted)
    assert field in caught.value.errors
