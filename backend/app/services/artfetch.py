"""Download artwork bytes (screenshot/box art) for cover generation."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_TIMEOUT = httpx.Timeout(15.0)
_MAX_ART_BYTES = 8 * 1024 * 1024
_MAX_REDIRECTS = 5


def _is_safe_target(url: str) -> bool:
    """Reject anything that isn't a plain http(s) URL to a public host — the
    `cover/from-url` endpoint takes a URL straight from the client, so without
    this an attacker can make the server GET internal-only services or cloud
    metadata endpoints (SSRF). Checked on the initial URL AND on every
    redirect hop, since a public host can redirect to a private one."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


async def fetch_image(url: str) -> bytes | None:
    """
    GET an image URL, returning its bytes or None on any failure (missing
    art, 404, network error, blocked as unsafe). Never raises — a missing
    cover is not fatal.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                if not _is_safe_target(url):
                    return None
                resp = await client.get(url)
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return None
                    url = str(resp.next_request.url) if resp.next_request else location
                    continue
                break
            else:
                return None
        if resp.status_code != 200:
            return None
        data = resp.content
        if not data or len(data) > _MAX_ART_BYTES:
            return None
        return data
    except (httpx.HTTPError, OSError):
        return None
