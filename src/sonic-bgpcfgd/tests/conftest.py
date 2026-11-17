import pytest


@pytest.fixture(autouse=True)
def default_routing_stack(monkeypatch):
    """ Run every test against FRR unless the test asks for another stack.

    bgpcfgd picks its backend from SONIC_ROUTING_STACK in its environment
    (bgpcfgd/dialect.py). The build exports a variable of the same name
    (slave.mk), so in an image built with SONIC_ROUTING_STACK = zebra-rs
    the FRR tests would otherwise run against the zebra-rs backend. A test
    of the zebra-rs path sets the variable itself with monkeypatch.
    """
    monkeypatch.delenv("SONIC_ROUTING_STACK", raising=False)
