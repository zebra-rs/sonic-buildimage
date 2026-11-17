"""Traffic Shift Away / Back in the zebra-rs dialect."""
import os
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from bgpcfgd.directory import Directory
from bgpcfgd.template import TemplateFabric
from . import swsscommon_test  # noqa: F401
import bgpcfgd.managers_device_global
from swsscommon import swsscommon

TEMPLATE_PATH = os.path.abspath('../../dockers/docker-fpm-zebra-rs/zebra-rs')
CONSTANTS = {
    "bgp": {
        "traffic_shift_community": "12345:12345",
        "internal_community_match_tag": "201",
    }
}

# `show running-config formal` on a T1 with its two peer-groups configured.
RUNNING = [
    "set policy TO_BGP_PEER_V4 entry 100 action permit",
    "set policy TO_BGP_PEER_V6 entry 100 action permit",
    "set router bgp neighbor-group PEER_V4 policy in FROM_BGP_PEER_V4",
    "set router bgp neighbor-group PEER_V4 policy out TO_BGP_PEER_V4",
    "set router bgp neighbor-group PEER_V6 policy in FROM_BGP_PEER_V6",
    "set router bgp neighbor-group PEER_V6 policy out TO_BGP_PEER_V6",
    "set router bgp neighbor 10.0.0.1 neighbor-group PEER_V4",
]

ISOLATE_V4 = [
    "set community-set TSA_COMMUNITY members 12345:12345",
    "set policy TO_BGP_PEER_V4 entry 20 action permit",
    "set policy TO_BGP_PEER_V4 entry 20 match prefix-set PL_LoopbackV4",
    "set policy TO_BGP_PEER_V4 entry 20 set community name TSA_COMMUNITY",
    "set policy TO_BGP_PEER_V4 entry 30 action permit",
    "set policy TO_BGP_PEER_V4 entry 30 match tag 201",
    "set policy TO_BGP_PEER_V4 entry 30 set community name TSA_COMMUNITY",
    "set policy TO_BGP_PEER_V4 entry 40 action deny",
]
ISOLATE_V6 = [line.replace("V4", "V6") for line in ISOLATE_V4]


def lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


@pytest.fixture
def mgr(monkeypatch):
    monkeypatch.setenv("SONIC_ROUTING_STACK", "zebra-rs")
    cfg_mgr = MagicMock()
    cfg_mgr.pushed = []
    cfg_mgr.get_text = lambda: list(RUNNING)
    cfg_mgr.push = lambda text: cfg_mgr.pushed.append(text)
    common_objs = {
        'directory': Directory(),
        'cfg_mgr':   cfg_mgr,
        'tf':        TemplateFabric(TEMPLATE_PATH),
        'constants': deepcopy(CONSTANTS),
    }
    with patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status',
               return_value="false"):
        yield bgpcfgd.managers_device_global.DeviceGlobalCfgMgr(
            common_objs, "CONFIG_DB", swsscommon.CFG_BGP_DEVICE_GLOBAL_TABLE_NAME)


def pushed(mgr):
    return lines("\n".join(mgr.cfg_mgr.pushed))


def test_tsa_isolates_every_outbound_policy_in_use(mgr):
    assert mgr.set_handler("STATE", {"tsa_enabled": "true"})
    assert pushed(mgr) == ISOLATE_V4 + ISOLATE_V6
    assert mgr.directory.get("CONFIG_DB", swsscommon.CFG_BGP_DEVICE_GLOBAL_TABLE_NAME, "tsa_enabled") == "true"


def test_tsb_deletes_exactly_the_entries_tsa_added(mgr):
    mgr.set_handler("STATE", {"tsa_enabled": "true"})
    del mgr.cfg_mgr.pushed[:]
    assert mgr.set_handler("STATE", {"tsa_enabled": "false"})
    assert pushed(mgr) == [
        "delete policy TO_BGP_PEER_V4 entry 20",
        "delete policy TO_BGP_PEER_V4 entry 30",
        "delete policy TO_BGP_PEER_V4 entry 40",
        "delete policy TO_BGP_PEER_V6 entry 20",
        "delete policy TO_BGP_PEER_V6 entry 30",
        "delete policy TO_BGP_PEER_V6 entry 40",
    ]


def test_no_tsa_at_startup_pushes_nothing(mgr):
    assert mgr.set_handler("STATE", {"tsa_enabled": "false"})
    assert pushed(mgr) == []


def test_a_peer_group_created_while_isolated_comes_up_isolated(mgr):
    mgr.set_handler("STATE", {"tsa_enabled": "true"})
    pg = ("set router bgp neighbor-group PEER_V4\n"
          "set router bgp neighbor-group PEER_V4 policy in FROM_BGP_PEER_V4\n"
          "set router bgp neighbor-group PEER_V4 policy out TO_BGP_PEER_V4\n")
    assert lines(mgr.check_state_and_get_tsa_routemaps(pg)) == ISOLATE_V4


def test_a_peer_group_created_while_not_isolated_gets_nothing(mgr):
    pg = "set router bgp neighbor-group PEER_V4 policy out TO_BGP_PEER_V4\n"
    assert mgr.check_state_and_get_tsa_routemaps(pg) == ""


def test_a_neighbors_own_outbound_policy_is_isolated_too(mgr):
    text = mgr.get_ts_routemaps(
        ["set router bgp neighbor 10.0.0.9 policy out TO_BGP_PEER_V4"], mgr.tsa_template)
    assert lines(text) == ISOLATE_V4


def test_an_inbound_policy_is_not_touched(mgr):
    text = mgr.get_ts_routemaps(
        ["set router bgp neighbor-group PEER_V4 policy in FROM_BGP_PEER_V4"], mgr.tsa_template)
    assert lines(text) == []


def test_an_internal_policy_adds_no_export_instead_of_denying(mgr):
    text = mgr.get_ts_routemaps(
        ["set router bgp neighbor-group INTERNAL_PEER_V4 policy out TO_BGP_INTERNAL_PEER_V4"],
        mgr.tsa_template)
    assert lines(text) == [
        "set community-set TSA_NO_EXPORT members no-export",
        "set policy TO_BGP_INTERNAL_PEER_V4 entry 20 action permit",
        "set policy TO_BGP_INTERNAL_PEER_V4 entry 20 set community name TSA_NO_EXPORT",
        "set policy TO_BGP_INTERNAL_PEER_V4 entry 20 set community additive",
    ]
    text = mgr.get_ts_routemaps(
        ["set router bgp neighbor-group INTERNAL_PEER_V4 policy out TO_BGP_INTERNAL_PEER_V4"],
        mgr.tsb_template)
    assert lines(text) == ["delete policy TO_BGP_INTERNAL_PEER_V4 entry 20"]


@patch('bgpcfgd.managers_device_global.log_err')
def test_wcmp_is_refused_and_not_recorded(mocked_log_err, mgr):
    mgr.set_handler("STATE", {"wcmp_enabled": "true"})
    assert pushed(mgr) == []
    assert mgr.directory.get("CONFIG_DB", swsscommon.CFG_BGP_DEVICE_GLOBAL_TABLE_NAME, "wcmp_enabled") == "false"
    assert any("W-ECMP" in str(c) for c in mocked_log_err.call_args_list)


@patch('bgpcfgd.managers_device_global.log_err')
def test_idf_isolation_is_refused_and_not_recorded(mocked_log_err, mgr):
    mgr.set_handler("STATE", {"idf_isolation_state": "isolated_no_export"})
    assert pushed(mgr) == []
    assert mgr.directory.get(
        "CONFIG_DB", swsscommon.CFG_BGP_DEVICE_GLOBAL_TABLE_NAME, "idf_isolation_state") == "unisolated"
    assert any("IDF" in str(c) for c in mocked_log_err.call_args_list)
    assert mgr.check_state_and_get_idf_isolation_routemaps() == ""
