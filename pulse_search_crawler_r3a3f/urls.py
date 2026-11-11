"""URL canonicalisation, trap detection and origin scope.

Canonicalisation is deliberately conservative: it never invents a URL that
the server would not serve. It lowercases scheme/host, drops the fragment,
removes known tracking parameters, sorts the remaining parameters and
resolves dot segments. Everything that could carry meaning (path case,
unknown parameters and their order) is preserved.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "yclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_name",
        "utm_reader",
        "utm_referrer",
        "utm_social",
        "utm_social-type",
    }
)
PAGINATION_PARAMS = frozenset({"page", "paged", "p", "offset", "start", "pg", "pagenum"})
SESSION_PARAMS = frozenset({"sid", "sessionid", "phpsessid", "jsessionid", "aspsessionid"})
DEFAULT_PORTS = {"http": 80, "https": 443}


class UrlError(ValueError):
    """Raised for URLs that must never enter the frontier."""


def _split(url: str):
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:  # malformed IPv6 or port
        raise UrlError(f"unparseable url: {exc}") from exc
    return parts


def canonicalize(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    parts = _split(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in DEFAULT_PORTS:
        raise UrlError(f"unsupported scheme: {scheme or '(none)'}")
    if parts.username or parts.password:
        raise UrlError("embedded credentials are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UrlError("missing host")
    try:
        port = parts.port
    except ValueError as exc:
        raise UrlError(f"invalid port: {exc}") from exc
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    segments: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    path = "/" + "/".join(segments)
    if path.endswith("/") and path != "/":
        path = path[:-1]
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def origin_of(url: str) -> str:
    parts = _split(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port in (None, DEFAULT_PORTS.get(scheme)):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def host_port(url: str) -> str:
    return _split(url).netloc.lower()


def is_loopback_host(hostport: str) -> bool:
    host = hostport.split(":")[0]
    return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")


def is_indexable_shape(url: str) -> tuple[bool, str]:
    """Reject shapes that are common crawl traps or non-pages."""
    parts = _split(url)
    path = parts.path.lower()
    if len(url) > 2000:
        return False, "url_too_long"
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|ico|css|js|woff2?|ttf|eot|zip|gz|"
                 r"pdf|mp4|mp3|avi|mov|exe|dmg|iso)$", path):
        return False, "non_html_asset"
    if any(key.lower() in SESSION_PARAMS for key, _ in parse_qsl(parts.query)):
        return False, "session_identifier"
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if len(pairs) > 6:
        return False, "parameter_explosion"
    for key, value in pairs:
        if key.lower() in PAGINATION_PARAMS:
            if not value.isdigit():
                return False, "pagination_not_numeric"
            if int(value) > 50:
                return False, "pagination_trap"
    segments = [s for s in path.split("/") if s]
    for segment in set(segments):
        if segments.count(segment) >= 3:
            return False, "repeated_path_segment"
    if re.search(r"/(19|20)\d\d/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])"
                 r"/(19|20)\d\d/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])", path):
        return False, "nested_date_trap"
    return True, "ok"


def in_scope(url: str, origin: str, allowed_paths: list[str]) -> bool:
    if origin_of(url) != origin.rstrip("/"):
        return False
    path = _split(url).path or "/"
    for allowed in allowed_paths:
        if allowed == "/":
            return True
        if path == allowed or path.startswith(allowed.rstrip("/") + "/"):
            return True
    return False
