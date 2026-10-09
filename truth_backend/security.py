"""Public URL validation and DNS-pinned, bounded HTTP requests."""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote, unquote_plus

import httpx


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def sensitive_header_values(headers: dict | None) -> list[str]:
    """Keep secret URL guards after authentication headers are dropped on redirects."""
    values = []
    for name, value in (headers or {}).items():
        lower = name.lower()
        if lower not in {"authorization", "cookie", "x-subscription-token"}:
            continue
        values.append(value)
        if lower == "authorization":
            scheme, separator, payload = value.partition(" ")
            if separator and payload:
                values.append(payload)
                if scheme.lower() == "basic":
                    try:
                        decoded = base64.b64decode(payload, validate=True).decode("utf-8")
                        _username, has_password, password = decoded.partition(":")
                        if has_password and password:
                            values.append(password)
                    except (ValueError, UnicodeError):
                        pass
        elif lower == "cookie":
            for cookie in value.split(";"):
                _name, separator, item = cookie.partition("=")
                if separator and item.strip():
                    values.extend((item.strip(), item.strip().strip('"')))
    return sorted({value for value in values if value}, key=len, reverse=True)


def check_url_for_secrets(url: str, secrets: list[str]) -> None:
    candidates = {url}
    # Normal percent-encoding, query '+' encoding, and one nested encoded URL
    # must not make a known credential safe to transmit or publish.
    for _ in range(2):
        candidates.update(unquote(value) for value in list(candidates))
        candidates.update(unquote_plus(value) for value in list(candidates))
    if any(secret in candidate for secret in secrets for candidate in candidates):
        raise ServiceError("credentials_in_public_input", "来源 URL 或重定向包含已知凭据，已阻止访问和输出。", 400)


def check_url_shape(url: str, *, allow_loopback: bool = False) -> tuple[str, str, int]:
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError
        if parts.username is not None or parts.password is not None:
            raise ValueError
        host = parts.hostname.encode("idna").decode("ascii").rstrip(".").lower()
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if any(c.isspace() for c in url) or "\\" in url or len(url) > 4000:
            raise ValueError
        literal = None
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            if host in {"localhost", "localhost.localdomain"}:
                if not allow_loopback:
                    raise ValueError
            elif "." not in host or host.endswith((".local", ".internal", ".localhost")):
                raise ValueError
        local = (literal is not None and literal.is_loopback) or host == "localhost"
        if literal is not None and not literal.is_global and not (allow_loopback and local):
            raise ValueError
        if not (allow_loopback and local) and port not in {80, 443}:
            raise ValueError
        if not 1 <= port <= 65535:
            raise ValueError
        return parts.scheme, host, port
    except (ValueError, UnicodeError):
        raise ServiceError("unsafe_url", "地址被安全策略阻止：仅允许公网 HTTP/HTTPS 与安全端口；AI 可使用本机回环地址。", 400) from None


async def resolve_public(url: str, *, allow_loopback: bool = False) -> tuple[str, str, int, str]:
    scheme, host, port = check_url_shape(url, allow_loopback=allow_loopback)
    literal_loopback = False
    try:
        literal_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    permitted_loopback = allow_loopback and (host == "localhost" or literal_loopback)
    try:
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=5
        )
    except (OSError, asyncio.TimeoutError):
        raise ServiceError("dns_failed", "无法解析来源地址。") from None
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise ServiceError("dns_failed", "无法解析来源地址。")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global and not (permitted_loopback and ip.is_loopback):
            raise ServiceError("unsafe_url", "地址解析到非公网目标，已阻止访问。", 400)
    return scheme, host, port, addresses[0]


@dataclass
class Fetched:
    url: str
    content: bytes
    content_type: str
    status_code: int


async def pinned_request(
    url: str, *, method: str = "GET", headers: dict | None = None, json_body: dict | None = None,
    allow_loopback: bool = False, redirects: int = 0, max_bytes: int = 1_500_000, timeout: float = 15,
) -> Fetched:
    """Connect to the validated IP, preserving Host and TLS SNI; never re-resolve it."""
    current = url
    secrets = sensitive_header_values(headers)
    for step in range(redirects + 1):
        check_url_for_secrets(current, secrets)
        scheme, host, port, address = await resolve_public(current, allow_loopback=allow_loopback)
        parts = urlsplit(current)
        ip_host = f"[{address}]" if ":" in address else address
        target = urlunsplit((scheme, f"{ip_host}:{port}", parts.path or "/", parts.query, ""))
        host_value = f"[{host}]" if ":" in host else host
        if port != (443 if scheme == "https" else 80):
            host_value += f":{port}"
        request_headers = {"User-Agent": "TellMeTruth/1.0 (evidence research)", **(headers or {}), "Host": host_value}
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
                request = client.build_request(method, target, headers=request_headers, json=json_body)
                request.extensions["sni_hostname"] = host
                response = await client.send(request, stream=True)
                try:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if step >= redirects or not location:
                            raise ServiceError("redirect_blocked", "目标返回了不允许的重定向。")
                        next_url = urljoin(current, location)
                        check_url_for_secrets(next_url, secrets)
                        old_origin = check_url_shape(current, allow_loopback=allow_loopback)
                        next_origin = check_url_shape(next_url, allow_loopback=allow_loopback)
                        # Source credentials survive only exact same-origin redirects.
                        # Cross-origin redirects never inherit Authorization or Cookie.
                        if old_origin != next_origin:
                            headers = None
                        current = next_url
                        json_body = None
                        method = "GET"
                        continue
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise ServiceError("content_too_large", "来源内容超过安全读取上限。")
                    return Fetched(current, bytes(content), response.headers.get("content-type", ""), response.status_code)
                finally:
                    await response.aclose()
        except (httpx.HTTPError, OSError):
            raise ServiceError("network_error", "网络连接失败或超时，请检查网络和服务地址。") from None
    raise ServiceError("redirect_blocked", "重定向次数超过上限。")
