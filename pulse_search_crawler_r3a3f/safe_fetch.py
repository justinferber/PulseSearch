"""Bounded HTTP fetching.

The fetcher never dials a hostname directly: every hop is resolved, checked
and pinned (see netguard). Redirects are re-validated one by one, bodies are
capped, only http/https is allowed, and 429/503 carry their Retry-After back
to the scheduler instead of being retried in a loop.
"""

from __future__ import annotations

import gzip
import http.client
import socket
import ssl
import time
import zlib
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from . import netguard
from .config import CrawlConfig
from .urls import canonicalize

REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int = 0
    mime: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    truncated: bool = False
    error: str = ""
    retry_after_s: float | None = None
    chain: list[str] = field(default_factory=list)
    latency_ms: int = 0
    bytes_received: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and self.status == 200


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


class Fetcher:
    def __init__(self, config: CrawlConfig):
        self.config = config
        self.requests = 0
        self.bytes_received = 0

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> FetchResult:
        limit = max_bytes or self.config.max_bytes
        started = time.monotonic()
        scheme = urlsplit(url).scheme.lower()
        if scheme and scheme not in ("http", "https"):
            return FetchResult(url, url, error=f"scheme_not_allowed:{scheme}")
        current = url
        chain: list[str] = []
        for hop in range(self.config.max_redirects + 1):
            try:
                current = canonicalize(current)
            except ValueError as exc:
                return FetchResult(url, current, error=f"bad_url:{exc}", chain=chain)
            chain.append(current)
            result = self._one(current, limit, extra_headers, chain, started)
            if result.error or result.status not in REDIRECT_CODES:
                return result
            location = result.headers.get("location")
            if not location:
                result.error = "redirect_without_location"
                return result
            if hop >= self.config.max_redirects:
                result.error = "too_many_redirects"
                return result
            current = urljoin(current, location)
        return FetchResult(url, current, error="too_many_redirects", chain=chain)

    def _one(self, url, limit, extra_headers, chain, started) -> FetchResult:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            return FetchResult(url, url, error=f"scheme_not_allowed:{scheme}", chain=chain)
        port = parts.port or (443 if scheme == "https" else 80)
        loopback_allowed = bool(self.config.allow_loopback) and netguard_is_loopback(parts.hostname or "")
        try:
            ip = netguard.resolve_public(parts.hostname or "", port, allow_loopback=loopback_allowed)
        except netguard.UnsafeTarget as exc:
            return FetchResult(url, url, error=f"unsafe_target:{exc}", chain=chain)
        conn_cls = _PinnedHTTPS if scheme == "https" else _PinnedHTTP
        conn = conn_cls(parts.hostname, port, ip, self.config.timeout_s)
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.8,*/*;q=0.5",
            "Accept-Encoding": "gzip",
            "Connection": "close",
            "Host": parts.netloc,
        }
        if extra_headers:
            headers.update(extra_headers)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            status = response.status
            mime = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
            hdrs = {k.lower(): v for k, v in response.getheaders()}
            self.requests += 1
            declared = hdrs.get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                return FetchResult(url, url, status=status, mime=mime, headers=hdrs,
                                   error="declared_oversize", chain=chain)
            body = response.read(limit + 1)
            truncated = len(body) > limit
            body = body[:limit]
            encoding = hdrs.get("content-encoding", "").lower()
            if not truncated and encoding in ("gzip", "x-gzip"):
                try:
                    body = gzip.decompress(body)[:limit]
                except (OSError, EOFError, zlib.error):
                    return FetchResult(url, url, status=status, mime=mime, headers=hdrs,
                                       error="bad_gzip", chain=chain)
            self.bytes_received += len(body)
            return FetchResult(
                url=url,
                final_url=url,
                status=status,
                mime=mime,
                headers=hdrs,
                body=body,
                truncated=truncated,
                retry_after_s=parse_retry_after(hdrs.get("retry-after")),
                chain=chain,
                latency_ms=int((time.monotonic() - started) * 1000),
                bytes_received=len(body),
            )
        except (socket.timeout, TimeoutError):
            return FetchResult(url, url, error="timeout", chain=chain)
        except (connection_error_types()) as exc:
            return FetchResult(url, url, error=f"network:{type(exc).__name__}", chain=chain)
        finally:
            conn.close()


def connection_error_types():
    return (OSError, ssl.SSLError, http.client.HTTPException)


def netguard_is_loopback(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")
