# best effort, httpx resolves again on connect so rebinding can get past this

import ipaddress
import socket
from urllib.parse import urlsplit


class TargetNotAllowed(Exception):
    pass


def check_target(url: str, allow_private: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise TargetNotAllowed("target must be an http or https URL")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise TargetNotAllowed("target host does not resolve") from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise TargetNotAllowed("target resolves to a non-public address")
