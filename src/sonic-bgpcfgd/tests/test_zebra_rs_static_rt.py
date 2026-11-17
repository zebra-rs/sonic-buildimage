"""
STATIC_ROUTE under zebra-rs: the manager writes `router static` lines and
refuses the routes zebra-rs cannot express.
"""
from unittest.mock import MagicMock

import pytest
from swsscommon import swsscommon

from bgpcfgd.directory import Directory
from bgpcfgd.template import TemplateFabric
from bgpcfgd.managers_static_rt import StaticRouteMgr

REDIST = [
    "router bgp afi-safi ipv4 redistribute static",
    "router bgp afi-safi ipv6 redistribute static",
]
ENABLE = ["set " + line for line in REDIST]
DISABLE = ["delete " + line for line in REDIST]


@pytest.fixture
def mgr(monkeypatch):
    monkeypatch.setenv("SONIC_ROUTING_STACK", "zebra-rs")
    common_objs = {
        'directory': Directory(),
        'cfg_mgr':   MagicMock(),
        'tf':        TemplateFabric(),
        'constants': {},
    }
    m = StaticRouteMgr(common_objs, "CONFIG_DB", "STATIC_ROUTE")
    m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME, "localhost", {"bgp_asn": "65100"})
    m.pushed = []
    m.cfg_mgr.push_list = lambda cmds: m.pushed.append(list(cmds))
    return m


def pushed(m):
    """ What the last handler call pushed, as one list; nothing if it pushed nothing """
    out = [line for batch in m.pushed for line in batch]
    m.pushed = []
    return out


def test_first_route_is_written_and_turns_redistribution_on(mgr):
    assert mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    assert pushed(mgr) == ["set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57"] + ENABLE


def test_second_route_leaves_redistribution_alone(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    pushed(mgr)
    mgr.set_handler("default|10.2.0.0/24", {"nexthop": "10.0.0.59"})
    assert pushed(mgr) == ["set router static ipv4 route 10.2.0.0/24 nexthop 10.0.0.59"]


def test_ecmp_route_gets_one_line_per_next_hop(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57,10.0.0.59"})
    assert pushed(mgr)[:2] == [
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57",
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.59",
    ]


def test_ifname_beside_an_address_is_not_written(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57", "ifname": "Ethernet4"})
    assert pushed(mgr)[0] == "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57"


def test_route_as_config_route_add_writes_it(mgr):
    mgr.set_handler("default|10.1.0.0/24", {
        "blackhole": "false,false", "distance": "0,0", "ifname": ",",
        "nexthop": "10.0.0.57,10.0.0.59", "nexthop-vrf": "default,default",
    })
    assert pushed(mgr)[:2] == [
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57",
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.59",
    ]


def test_ipv6_route(mgr):
    mgr.set_handler("fc00:10::/64", {"nexthop": "fc00::72"})
    assert pushed(mgr)[0] == "set router static ipv6 route fc00:10::/64 nexthop fc00::72"


def test_blackhole_is_a_next_hop_keyword(mgr):
    mgr.set_handler("10.1.0.0/24", {"blackhole": "true"})
    assert pushed(mgr)[0] == "set router static ipv4 route 10.1.0.0/24 nexthop blackhole"


def test_distance_is_set_on_the_route(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57,10.0.0.59", "distance": "10,10"})
    assert pushed(mgr)[:3] == [
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57",
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.59",
        "set router static ipv4 route 10.1.0.0/24 distance 10",
    ]


def test_changed_next_hop_adds_before_it_removes(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    pushed(mgr)
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.59"})
    assert pushed(mgr) == [
        "set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.59",
        "delete router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57",
    ]


def test_distance_removed(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57", "distance": "10"})
    pushed(mgr)
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    assert pushed(mgr) == ["delete router static ipv4 route 10.1.0.0/24 distance"]


def test_same_route_again_pushes_nothing(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    pushed(mgr)
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    assert pushed(mgr) == []


def test_delete_of_the_last_route_turns_redistribution_off(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57,10.0.0.59"})
    pushed(mgr)
    mgr.del_handler("10.1.0.0/24")
    assert pushed(mgr) == ["delete router static ipv4 route 10.1.0.0/24"] + DISABLE
    assert mgr.static_routes == {"default": {}}


def test_delete_of_one_of_two_routes_keeps_redistribution(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    mgr.set_handler("10.2.0.0/24", {"nexthop": "10.0.0.57"})
    pushed(mgr)
    mgr.del_handler("10.1.0.0/24")
    assert pushed(mgr) == ["delete router static ipv4 route 10.1.0.0/24"]


def test_redistribution_waits_for_the_asn(monkeypatch):
    monkeypatch.setenv("SONIC_ROUTING_STACK", "zebra-rs")
    m = StaticRouteMgr({'directory': Directory(), 'cfg_mgr': MagicMock(), 'tf': TemplateFabric(), 'constants': {}},
                       "CONFIG_DB", "STATIC_ROUTE")
    m.pushed = []
    m.cfg_mgr.push_list = lambda cmds: m.pushed.append(list(cmds))
    m.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    assert pushed(m) == ["set router static ipv4 route 10.1.0.0/24 nexthop 10.0.0.57"]
    m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME, "localhost", {"bgp_asn": "65100"})
    assert pushed(m) == ENABLE


@pytest.mark.parametrize("key,data", [
    ("10.1.0.0/24", {"nexthop": "10.0.0.57", "advertise": "false"}),
    ("Vrf1|10.1.0.0/24", {"nexthop": "10.0.0.57"}),
    ("10.1.0.0/24", {"ifname": "Ethernet4"}),
    ("10.1.0.0/24", {"nexthop": "PortChannel0001"}),
    ("10.1.0.0/24", {"nexthop": "10.0.0.57", "nexthop-vrf": "Vrf1"}),
    ("10.1.0.0/24", {"nexthop": "10.0.0.57,10.0.0.59", "distance": "10,20"}),
    ("10.1.0.0/24", {"nexthop": "10.0.0.57,", "blackhole": "false,true"}),
    ("fc00:10::/64", {"nexthop": "fe80::1", "ifname": "Ethernet4"}),
])
def test_route_zebra_rs_cannot_express_is_refused_whole(mgr, key, data):
    assert mgr.set_handler(key, data)
    assert pushed(mgr) == []
    assert not any(mgr.static_routes.values())


def test_route_changed_to_a_refused_form_is_removed(mgr):
    mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57"})
    pushed(mgr)
    assert mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57", "advertise": "false"})
    assert pushed(mgr) == ["delete router static ipv4 route 10.1.0.0/24"] + DISABLE
    assert mgr.static_routes == {"default": {}}


def test_bfd_route_is_left_alone(mgr):
    assert mgr.set_handler("10.1.0.0/24", {"nexthop": "10.0.0.57", "bfd": "true"})
    assert pushed(mgr) == []
