"""
zebra-rs backend for bgpcfgd, mirroring the `FRR` proxy in frr.py.

bgpcfgd's managers already encode SONiC's CONFIG_DB semantics correctly;
what is FRR-specific is the *backend* (how configuration is pushed) and
the *templates* (what syntax is pushed). This is the backend half. The
templates are the larger remaining piece.

Differences from the FRR backend that matter to callers:

* **No diffing needed here.** `ConfigMgr` reads FRR's running config,
  parses it into a canonical tree and computes a delta, because `vtysh -f`
  applies a flat command list with no notion of desired state. zebra-rs
  has a candidate/running config model and does that work itself, and
  `show running-config formal` returns a flat *set-style* listing rather
  than FRR's indented blocks. So a zebra-rs ConfigMgr can push `set` /
  `delete` lines and let the daemon reconcile — the FRR-shaped
  `to_canonical` machinery has nothing to do.

* **`show` takes the full command string**, leading keyword included:
  `vtyctl show "show running-config formal"`, not `vtyctl show
  "running-config formal"`. Omitting it fails with `NoMatch`.

* **Session ownership.** zebra-rs ties a VTY session to the caller's
  parent shell and rejects clients whose ppid is <= 1
  (`SessionError::OrphanClient`). That rules out a bare `docker exec
  vtyctl ...`, but not this: bgpcfgd runs under supervisord and shells
  out with subprocess, so vtyctl's parent is the bgpcfgd process itself.
  Verified in the container.
"""

import datetime
import os
import tempfile
import time

from bgpcfgd.log import log_crit, log_err, log_info, log_warn

from .vars import g_debug
from .utils import run_command

VTYCTL = "vtyctl"


class ZebraRs(object):
    """Proxy object with zebra-rs"""

    def __init__(self, daemons=None):
        # Kept for interface parity with FRR(daemons). zebra-rs is a
        # single process carrying the RIB and every protocol, so there is
        # no per-daemon readiness to check — only whether the daemon is
        # answering at all.
        self.daemons = daemons or []

    def wait_for_daemons(self, seconds):
        """
        Wait until zebra-rs is ready to accept configuration.
        :param seconds: number of seconds to wait, until raise an error
        """
        stop_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        log_info("Start waiting for zebra-rs: %s" % str(datetime.datetime.now()))
        while datetime.datetime.now() < stop_time:
            ret_code, out, err = run_command(
                [VTYCTL, "show", "show version"], hide_errors=True
            )
            if ret_code == 0 and out.strip():
                log_info("zebra-rs is ready: %s" % str(datetime.datetime.now()))
                return
            log_warn("Can't read version from zebra-rs: %s" % str(err))
            time.sleep(0.1)  # sleep 100 ms
        raise RuntimeError("zebra-rs hasn't been started in %d seconds" % seconds)

    @staticmethod
    def get_config():
        """
        Read the running configuration as flat `set`-style statements.

        Returned lines carry no `set ` prefix — that is the format
        `show running-config formal` emits — while `write()` expects one.
        Callers comparing the two must account for that rather than
        assuming they are directly comparable.
        """
        ret_code, out, err = run_command([VTYCTL, "show", "show running-config formal"])
        if ret_code != 0:
            log_crit(
                "can't update running config: rc=%d out='%s' err='%s'"
                % (ret_code, out, err)
            )
            return ""
        return out

    @staticmethod
    def write(config_text):
        """
        Apply configuration to zebra-rs.
        :param config_text: `set` / `delete` lines, one per line
        :return: True on success
        """
        fd, tmp_filename = tempfile.mkstemp(dir="/tmp")
        os.close(fd)
        with open(tmp_filename, "w") as fp:
            fp.write("%s\n" % config_text)
        command = [VTYCTL, "apply", "-f", tmp_filename]
        ret_code, out, err = run_command(command)
        if ret_code != 0:
            err_tuple = tmp_filename, ret_code, out, err
            log_err(
                "ZebraRs::write(): can't push configuration from file='%s', rc='%d', stdout='%s', stderr='%s'"
                % err_tuple
            )
        else:
            if not g_debug:
                os.remove(tmp_filename)
        return ret_code == 0

    @staticmethod
    def restart_peer_groups(peer_groups):
        """
        Soft-clear peer-groups.

        Not implemented, deliberately and loudly. zebra-rs's `clear bgp`
        takes a neighbor (or `all`), not a peer-group
        (zebra-bgp-clear.yang), and this backend has no view of group
        membership to expand the name itself. The two ways out are a
        `clear bgp peer-group` command in zebra-rs, or resolving members
        here from CONFIG_DB.

        Falling back to `clear bgp all` would work but is not a quiet
        substitute: soft-clearing every session because one peer-group's
        policy changed is an availability event, not an implementation
        detail. Returning False lets the caller see the operation did not
        happen — BBR (managers_bbr) is the consumer to check first.
        """
        log_err(
            "ZebraRs::restart_peer_groups(): peer-group soft-clear is not supported yet "
            "(zebra-rs clears by neighbor, not by peer-group); groups=%s"
            % sorted(peer_groups)
        )
        return False
