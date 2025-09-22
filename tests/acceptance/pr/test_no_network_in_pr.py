# tests/acceptance/pr/test_no_network_in_pr.py
import os
import socket
import pytest


@pytest.mark.prlane
def test_no_network():
    if os.getenv("CI") and (os.getenv("LANE", "pr").lower() == "pr"):
        with pytest.raises(OSError):
            socket.socket().connect(("8.8.8.8", 53))
