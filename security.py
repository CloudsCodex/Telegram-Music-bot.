# Developer by : Mr_Manas_Op
"""URL safety checks (basic SSRF protection for user supplied links)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


async def is_public_url(url: str) -> bool:
    """Return True only for http(s) URLs whose host resolves to public IPs."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        return False

    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=5
        )
    except (OSError, asyncio.TimeoutError):
        return False

    if not infos:
        return False

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
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
