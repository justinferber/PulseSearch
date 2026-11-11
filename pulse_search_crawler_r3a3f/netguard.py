"""SSRF protection: every connection and redirect is resolved and checked.

A URL is never dialled by hostname. We resolve, verify that every returned
address is public, and then connect to that exact address while keeping the
original Host header/TLS server name. Loopback and private ranges are refused
unless the crawl was explicitly configured for the offline simulator.
"""

from __future__ import annotations

import ipaddress
import socket

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


class UnsafeTarget(RuntimeError):
    """Raised when a URL resolves to a non-public or disallowed address."""


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_public(host: str, port: int, allow_loopback: bool = False) -> str:
    host = (host or "").strip().lower()
    if not host:
        raise UnsafeTarget("missing host")
    if host in BLOCKED_HOSTNAMES - {"localhost", "localhost.localdomain"}:
        raise UnsafeTarget("metadata hostname blocked")
    if host in ("localhost", "localhost.localdomain"):
        if not allow_loopback:
            raise UnsafeTarget("loopback hostname blocked")
        return "127.0.0.1"
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if literal.is_loopback and allow_loopback:
            return str(literal)
        if not _ip_is_public(literal):
            raise UnsafeTarget(f"non-public address blocked: {literal}")
        return str(literal)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTarget(f"dns resolution failed: {exc}") from exc
    addresses = []
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeTarget(f"unparseable resolved address: {address}") from exc
        if ip.is_loopback and allow_loopback:
            addresses.append(str(ip))
            continue
        if not _ip_is_public(ip):
            raise UnsafeTarget(f"resolved to non-public address: {ip}")
        addresses.append(str(ip))
    if not addresses:
        raise UnsafeTarget("no addresses resolved")
    return addresses[0]
