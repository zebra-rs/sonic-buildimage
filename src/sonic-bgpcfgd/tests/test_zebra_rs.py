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
        # write() first reads the running config to drop lines the daemon
        # already has, then applies: ["vtyctl", "apply", "-f", <tmpfile>]
        if cmd[1] == "show":
            return (0, "", "")
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


def test_write_detects_rejection_despite_zero_exit():
    """`vtyctl apply` exits 0 even when the daemon rejects a line.

    It reports `error reply: <line>` and still returns success, so an
    exit-code-only check would let a bad template silently no-op — the
    config would look applied and would not be. Observed against a live
    daemon.
    """
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (
        0,
        "line:set bogus leaf 1\nerror reply: set bogus leaf 1\n",
        "",
    )
    assert not bgpcfgd.zebra_rs.ZebraRs.write("set bogus leaf 1")


def test_write_accepts_a_clean_apply():
    bgpcfgd.zebra_rs.run_command = lambda cmd, **kwargs: (
        0,
        "line:set router bgp global as 65100\napplied\n",
        "",
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write("set router bgp global as 65100")


def test_restart_peer_groups_reports_unsupported():
    """Peer-group soft-clear has no zebra-rs equivalent yet.

    It must fail visibly rather than silently doing nothing — and must
    not quietly widen into `clear bgp all`, which would soft-clear every
    session because one group's policy changed.
    """
    assert not bgpcfgd.zebra_rs.ZebraRs.restart_peer_groups(["PEER_V4"])


def _fake_daemon(running, applied):
    """ run_command stand-in: answers `show running-config formal` with
    `running` and records the text of each `apply -f <file>` """
    def fake(cmd, **kwargs):
        if cmd[1] == "show":
            return 0, running, ""
        with open(cmd[3]) as fp:
            applied.append(fp.read())
        return 0, "", ""
    return fake


def test_write_skips_what_the_daemon_already_has():
    # A leaf-list `set` appends in zebra-rs, so re-pushing a peer-group's
    # policy for every peer that uses it would store each community once
    # per peer. Only the genuinely new line may reach the daemon.
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon(
        "set community-set C members 5060:12345\nset router bgp neighbor-group PEER_V4\n",
        applied,
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write(
        "set community-set C members 5060:12345\n"
        "set router bgp neighbor-group PEER_V4\n"
        "set router bgp neighbor 10.0.0.1 remote-as 65200\n"
    )
    assert applied == ["set router bgp neighbor 10.0.0.1 remote-as 65200\n"]


def test_write_drops_repeats_within_a_batch():
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon("", applied)
    assert bgpcfgd.zebra_rs.ZebraRs.write(
        "set community-set C members no-export\n" * 3
        + "set router bgp neighbor 10.0.0.1 remote-as 65200\n"
    )
    assert applied == [
        "set community-set C members no-export\n"
        "set router bgp neighbor 10.0.0.1 remote-as 65200\n"
    ]


def test_write_with_nothing_new_does_not_call_apply():
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon("set router bgp neighbor-group PEER_V4\n", applied)
    assert bgpcfgd.zebra_rs.ZebraRs.write("set router bgp neighbor-group PEER_V4\n")
    assert applied == []


def test_write_keeps_a_set_that_follows_a_delete_covering_it():
    # Delete-then-recreate: the running config has the line, but the
    # delete ahead of it removes it, so the set is not redundant.
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon("set router bgp neighbor 10.0.0.1 remote-as 65200\n", applied)
    text = (
        "delete router bgp neighbor 10.0.0.1\n"
        "set router bgp neighbor 10.0.0.1 remote-as 65200\n"
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write(text)
    assert applied == [text]


def test_write_drops_a_delete_of_what_is_not_there():
    # zebra-rs rejects a delete of a missing path and a rejected line
    # discards the commit. Traffic Shift Back on a device that was never
    # shifted away deletes entries that do not exist.
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon(
        "set policy TO_BGP_PEER_V4\n"
        "set policy TO_BGP_PEER_V4 entry 100\n"
        "set policy TO_BGP_PEER_V4 entry 100 action permit\n",
        applied,
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write(
        "delete policy TO_BGP_PEER_V4 entry 20\n"
        "delete policy TO_BGP_PEER_V4 entry 30\n"
        "delete policy TO_BGP_PEER_V4 entry 40\n"
    )
    assert applied == []


def test_write_keeps_a_delete_of_what_is_there_and_only_that():
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon(
        "set policy TO_BGP_PEER_V4 entry 20\n"
        "set policy TO_BGP_PEER_V4 entry 20 action permit\n"
        "set policy TO_BGP_PEER_V4 entry 100 action permit\n",
        applied,
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write(
        "delete policy TO_BGP_PEER_V4 entry 20\n"
        "delete policy TO_BGP_PEER_V4 entry 30\n"
    )
    assert applied == ["delete policy TO_BGP_PEER_V4 entry 20\n"]


def test_write_does_not_take_entry_2_for_entry_20():
    # Paths are matched on whole words: `entry 2` is not there just
    # because `entry 20` is.
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon("set policy P entry 20 action permit\n", applied)
    assert bgpcfgd.zebra_rs.ZebraRs.write("delete policy P entry 2\n")
    assert applied == []


def test_write_still_drops_redundant_sets_beside_an_unrelated_delete():
    # A delete elsewhere in the batch used to switch the filter off, and
    # a leaf-list member pushed with it was stored a second time.
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon(
        "set community-set C members no-export\n"
        "set policy P entry 20 action permit\n",
        applied,
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write(
        "delete policy P entry 20\n"
        "set community-set C members no-export\n"
    )
    assert applied == ["delete policy P entry 20\n"]


def test_write_keeps_a_delete_of_what_the_batch_itself_creates():
    applied = []
    bgpcfgd.zebra_rs.run_command = _fake_daemon("", applied)
    text = (
        "set policy P entry 20 action permit\n"
        "delete policy P entry 20\n"
    )
    assert bgpcfgd.zebra_rs.ZebraRs.write(text)
    assert applied == [text]


def test_restart_peer_groups_with_nothing_to_restart_succeeds():
    # ConfigMgr.commit() calls this on every commit, almost always with an
    # empty list; that must not read as a failed commit.
    assert bgpcfgd.zebra_rs.ZebraRs.restart_peer_groups([])
