import socket

import pytest
from pytest_socket import SocketBlockedError


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
@pytest.mark.parametrize("kind", [socket.SOCK_STREAM, socket.SOCK_DGRAM])
def test_tcp_socket_is_blocked_before_any_network_io(family: int, kind: int) -> None:
    with (
        pytest.warns(UserWarning, match="A test tried to use socket.socket"),
        pytest.raises(SocketBlockedError),
    ):
        with socket.socket(family, kind) as connection:
            connection.connect(("127.0.0.1", 1))
