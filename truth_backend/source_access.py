"""Ephemeral origin-scoped source authentication. No accounts are stored."""
from __future__ import annotations

import base64
from urllib.parse import urlsplit, unquote

from .models import SourceCredential
from .security import ServiceError, check_url_shape, sensitive_header_values, check_url_for_secrets


def public_origin(url: str) -> str:
    scheme, host, port = check_url_shape(url)
    bracketed = f"[{host}]" if ":" in host else host
    return f"{scheme}://{bracketed}" + (f":{port}" if port != (443 if scheme == "https" else 80) else "")


def credential_headers(credentials: list[SourceCredential]) -> dict[str, dict[str, str]]:
    origins = {}
    for credential in credentials:
        parsed = urlsplit(credential.origin)
        origin = public_origin(credential.origin)
        if parsed.scheme != "https" or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ServiceError("invalid_source_credentials", "来源账户的 origin 必须是公网 HTTPS 根地址，不含路径、查询或片段。", 400)
        if origin in origins:
            raise ServiceError("invalid_source_credentials", "同一来源 origin 只能提供一种账户凭据。", 400)
        password = credential.password.get_secret_value()
        token = credential.token.get_secret_value()
        if any(any(ord(character) < 32 or ord(character) == 127 for character in item)
               for item in (credential.username, password, token)) or len(password) > 8192 or len(token) > 8192:
            raise ServiceError("invalid_source_credentials", "来源账户字段含无效字符或超过长度限制。", 400)
        if credential.kind == "basic":
            if not credential.username or not password or ":" in credential.username:
                raise ServiceError("invalid_source_credentials", "Basic 账户需要用户名和密码，用户名不能包含冒号。", 400)
            encoded = base64.b64encode(f"{credential.username}:{password}".encode()).decode("ascii")
            headers = {"Authorization": "Basic " + encoded}
        else:
            if not token:
                raise ServiceError("invalid_source_credentials", "Cookie 或 Bearer 账户需要非空 token。", 400)
            if not token.isascii():
                raise ServiceError("invalid_source_credentials", "Cookie 或 Bearer token 必须是有效的 ASCII HTTP 标头值。", 400)
            headers = {"Cookie": token} if credential.kind == "cookie" else {"Authorization": "Bearer " + token}
        origins[origin] = headers
    return origins


def headers_for_url(url: str, origins: dict[str, dict[str, str]]) -> dict[str, str] | None:
    # Only exact HTTPS scheme + hostname + port can receive credentials.
    if not origins:
        return None
    origin = public_origin(url)
    return origins.get(origin)


def secret_strings(credentials: list[SourceCredential], origins: dict[str, dict[str, str]]) -> list[str]:
    values = [value for credential in credentials for value in
              (credential.password.get_secret_value(), credential.token.get_secret_value()) if value]
    values.extend(value for headers in origins.values() for value in sensitive_header_values(headers))
    return sorted({value for value in values if value}, key=len, reverse=True)


def reject_credentials_in_public_input(inputs: list[str], secrets: list[str]) -> None:
    """Reject rather than rewrite a URL/topic that accidentally embeds credentials."""
    for value in inputs:
        check_url_for_secrets(value, secrets)


def redact_source_secrets(evidence, secrets: list[str]) -> bool:
    changed = False
    for field in ("title", "excerpt", "context"):
        original = getattr(evidence, field)
        redacted = original
        for secret in secrets:
            redacted = redacted.replace(secret, "[REDACTED CREDENTIAL]")
        if original != redacted:
            changed = True
            limit = 1000 if field == "title" else 5000 if field == "excerpt" else 6000
            setattr(evidence, field, redacted[:limit])
    return changed
