"""
Which routing stack bgpcfgd is driving.

bgpcfgd's managers encode SONiC's CONFIG_DB semantics; what differs
between routing stacks is the backend (how configuration is pushed) and
the dialect (what text is pushed). The container that runs bgpcfgd says
which one it is through SONIC_ROUTING_STACK in bgpcfgd's environment —
docker-fpm-zebra-rs sets it in its supervisord program stanza, and
docker-fpm-frr sets nothing, so FRR stays the default and an FRR image is
unaffected by anything in the zebra-rs path.
"""
import os

FRR = "frr"
ZEBRA_RS = "zebra-rs"


def routing_stack():
    """ Name of the routing stack this bgpcfgd instance drives """
    return os.environ.get("SONIC_ROUTING_STACK", FRR)


def is_zebra_rs():
    """ True when bgpcfgd is driving zebra-rs rather than FRR """
    return routing_stack() == ZEBRA_RS
