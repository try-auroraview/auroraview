"""Fail closed at Python networking boundaries during contract tests."""

import ipaddress
import socket
from urllib import request as urllib_request

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: Numeric loopback Core HTTP/MCP tests")


@pytest.fixture(autouse=True)
def network_guard(monkeypatch, request):
    calls = []
    loopback = request.node.get_closest_marker("integration") is not None
    getaddrinfo = socket.getaddrinfo
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    bind = socket.socket.bind
    sendto = socket.socket.sendto

    def local(host):
        try:
            return loopback and ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def forbidden(operation):
        def blocked(*args, **kwargs):
            calls.append((operation, args))
            pytest.fail("Real network access forbidden: " + operation)

        return blocked

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        if not local(host):
            return forbidden("getaddrinfo")(host, port)
        # Numeric flags prevent even allowed local requests from reaching DNS
        # or a system service-name resolver.
        flags |= socket.AI_NUMERICHOST | socket.AI_NUMERICSERV
        return getaddrinfo(host, port, family, type, proto, flags)

    def connection(operation, original):
        def guarded(sock, address, *args):
            if not isinstance(address, tuple) or not local(address[0]):
                return forbidden(operation)(address)
            return original(sock, address, *args)

        return guarded

    def datagram(sock, data, *args):
        address = args[-1]
        if not isinstance(address, tuple) or not local(address[0]):
            return forbidden("sendto")(address)
        return sendto(sock, data, *args)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    for name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
        monkeypatch.setattr(socket, name, forbidden(name))
    monkeypatch.setattr(socket.socket, "connect", connection("connect", connect))
    monkeypatch.setattr(socket.socket, "connect_ex", connection("connect_ex", connect_ex))
    monkeypatch.setattr(socket.socket, "bind", connection("bind", bind))
    monkeypatch.setattr(socket.socket, "sendto", datagram)
    if hasattr(socket.socket, "sendmsg"):
        monkeypatch.setattr(socket.socket, "sendmsg", forbidden("sendmsg"))
    monkeypatch.setattr(urllib_request.OpenerDirector, "open", forbidden("urllib"))
    return calls
