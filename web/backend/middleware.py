"""LAN-only middleware — reject non-RFC1918 source IPs."""

from __future__ import annotations

import ipaddress
import logging
import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

RFC1918 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def _is_rfc1918(ip: str) -> bool:
    """Check if an IP address is in a private (RFC1918) range."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in RFC1918)
    except ValueError:
        return False


class LanOnlyMiddleware(BaseHTTPMiddleware):
    """Reject requests from non-RFC1918 source IPs."""

    async def dispatch(self, request: Request, call_next):
        if os.environ.get("ORCHESTRATOR_EXPOSE_PUBLIC") == "1":
            return await call_next(request)

        # Check X-Forwarded-For if present and configured
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs; first one is client
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "0.0.0.0"

        if not _is_rfc1918(client_ip):
            logger.warning(
                "Blocked request from non-RFC1918 IP %s", client_ip
            )
            return JSONResponse(
                {"error": "LAN-only"}, status_code=403
            )

        return await call_next(request)
