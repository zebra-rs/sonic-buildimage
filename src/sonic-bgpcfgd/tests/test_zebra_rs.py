import bgpcfgd.zebra_rs
import pytest


def test_constructor():
    z = bgpcfgd.zebra_rs.ZebraRs(["abc", "cde"])
    assert z.daemons == ["abc", "cde"]


def test_constructor_without_daemons():
    # zebra-rs is one process, so the daemon list is interface parity
    # with the FRR backend rather than something callers must supply.
    z = bgpcfgd.zebra_rs.ZebraRs()
    assert z.daemons == []


def test_wait_for_daemons():
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (
        0,
        "zebra-rs version 26.8.2",
        "",
    )
    bgpcfgd.zebra_rs.ZebraRs().wait_for_daemons(5)


def test_wait_for_daemons_error():
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (1, "", "connection refused")
    with pytest.raises(Exception):
        bgpcfgd.zebra_rs.ZebraRs().wait_for_daemons(1)


def test_wait_for_daemons_empty_output():
    """A zero exit with no output is not readiness.

    vtyctl can succeed while the daemon is still coming up, and treating
    that as ready would let bgpcfgd push configuration into a half-started
    daemon.
    """
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (0, "  \n", "")
    with pytest.raises(Exception):
        bgpcfgd.zebra_rs.ZebraRs().wait_for_daemons(1)


def test_show_commands_include_the_leading_keyword():
    """`vtyctl show` takes the whole command string, `show` included.

    Dropping it is rejected with NoMatch, which is easy to write and
    fails only at runtime — so pin the exact argv here.
    """
    seen = []

    def fake(cmd, **kwargs):
        seen.append(cmd)
        return (0, "zebra-rs version 26.8.2", "")

    bgpcfgd.zebra_rs.run_command = fake
    bgpcfgd.zebra_rs.ZebraRs().wait_for_daemons(5)
    bgpcfgd.zebra_rs.ZebraRs.get_config()

    assert ["vtyctl", "show", "show version"] in seen
    assert ["vtyctl", "show", "show running-config formal"] in seen


def test_get_config():
    running = "router bgp global as 65100\nsystem fpm enabled true\n"
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (0, running, "")
    assert bgpcfgd.zebra_rs.ZebraRs.get_config() == running


def test_get_config_error():
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (1, "", "boom")
    assert bgpcfgd.zebra_rs.ZebraRs.get_config() == ""


def test_write():
    written = {}

    def fake(cmd, **kwargs):
        # cmd is ["vtyctl", "apply", "-f", <tmpfile>]
        with open(cmd[3]) as fp:
            written["text"] = fp.read()
        written["cmd"] = cmd
        return (0, "applied", "")

    bgpcfgd.zebra_rs.run_command = fake
    assert bgpcfgd.zebra_rs.ZebraRs.write("set router bgp global as 65100")
    assert written["cmd"][:3] == ["vtyctl", "apply", "-f"]
    assert "set router bgp global as 65100" in written["text"]


def test_write_failure_is_reported():
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (1, "", "rejected")
    assert not bgpcfgd.zebra_rs.ZebraRs.write("set nonsense")


def test_restart_peer_groups_reports_unsupported():
    """Peer-group soft-clear has no zebra-rs equivalent yet.

    It must fail visibly rather than silently doing nothing — and must
    not quietly widen into `clear bgp all`, which would soft-clear every
    session because one group's policy changed.
    """
    assert not bgpcfgd.zebra_rs.ZebraRs.restart_peer_groups(["PEER_V4"])
