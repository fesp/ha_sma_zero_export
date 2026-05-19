"""Async API client for SMA Sunny Portal (EnnexOS / UIAPI)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import time
from typing import Any

import aiohttp

from .const import (
    CLIENT_ID,
    MAX_5XX_RETRIES,
    REALM_URL,
    REDIRECT_URI,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_BASE,
    UIAPI_BASE,
)

_LOGGER = logging.getLogger(__name__)


# ── Custom exceptions ─────────────────────────────────────────────────────────

class SMAAuthError(Exception):
    """Raised when authentication fails and cannot be recovered."""


class SMAApiError(Exception):
    """Non-auth API error (network, 5xx, data parse)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SMARateLimitError(SMAApiError):
    """Raised on HTTP 429."""


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


# ── API Client ────────────────────────────────────────────────────────────────

class SMAApiClient:
    """Async API client for SMA Sunny Portal.

    Owns its own aiohttp session.  Tokens are held internally and must be
    persisted by the coordinator via ``get_tokens()`` after any operation that
    may have refreshed them.
    """

    def __init__(
        self,
        username: str,
        password: str,
        plant_id: str,
        access_token: str = "",
        refresh_token: str = "",
        id_token: str = "",
        debug: bool = False,
    ) -> None:
        self._username = username
        self._password = password
        self._plant_id = plant_id
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._id_token = id_token
        self._debug = debug
        self._session: aiohttp.ClientSession | None = None
        # Serialise token-recovery so only one coroutine refreshes at a time.
        self._auth_lock = asyncio.Lock()

    # ── Session ───────────────────────────────────────────────────────────────

    def _session_or_new(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
                connector=aiohttp.TCPConnector(ssl=True),
            )
        return self._session

    async def async_close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Token accessors ───────────────────────────────────────────────────────

    def get_tokens(self) -> dict[str, str]:
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "id_token": self._id_token,
        }

    def load_tokens(self, access_token: str, refresh_token: str, id_token: str) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._id_token = id_token

    # ── PKCE login ────────────────────────────────────────────────────────────

    async def async_login(self) -> None:
        """Full PKCE login using stored credentials.

        Updates internal tokens. Raises SMAAuthError on failure.
        """
        session = self._session_or_new()
        verifier, challenge = _generate_pkce()

        # Step 1 — GET the login page
        auth_url = (
            f"{REALM_URL}/protocol/openid-connect/auth"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&response_type=code"
            f"&scope=openid"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
        )
        try:
            async with session.get(auth_url, allow_redirects=True) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except aiohttp.ClientError as exc:
            raise SMAAuthError(f"Network error fetching login page: {exc}") from exc

        # Step 2 — extract form action URL
        m = re.search(r'action="([^"]+)"', html)
        if not m:
            raise SMAAuthError("Could not find login form action in page HTML")
        action_url = m.group(1).replace("&amp;", "&")
        if action_url.startswith("/"):
            action_url = "https://login.sma.energy" + action_url

        # Step 3 — POST credentials (no redirect follow; we need the Location header)
        payload = {
            "username": self._username,
            "password": self._password,
            "credentialId": "",
        }
        try:
            async with session.post(action_url, data=payload, allow_redirects=False) as resp:
                location = resp.headers.get("Location", "")
        except aiohttp.ClientError as exc:
            raise SMAAuthError(f"Network error submitting credentials: {exc}") from exc

        # Step 4 — extract auth code from redirect Location
        code_match = re.search(r"[?&]code=([^&]+)", location)
        if not code_match:
            raise SMAAuthError(
                f"Authorization code not found in redirect. "
                f"Location: {location!r}. Wrong username/password?"
            )
        auth_code = code_match.group(1)

        # Step 5 — exchange code for tokens
        token_url = f"{REALM_URL}/protocol/openid-connect/token"
        token_payload = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
        try:
            async with session.post(token_url, data=token_payload) as resp:
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise SMAAuthError(f"Network error during token exchange: {exc}") from exc

        if "access_token" not in data:
            raise SMAAuthError(f"Token exchange failed: {data}")

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", "")
        self._id_token = data.get("id_token", "")
        if self._debug:
            _LOGGER.debug("PKCE login successful")

    # ── Token refresh ─────────────────────────────────────────────────────────

    async def _async_refresh_token(self) -> bool:
        """Try to refresh access token.  Returns True on success."""
        if not self._refresh_token:
            return False
        token_url = f"{REALM_URL}/protocol/openid-connect/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": self._refresh_token,
        }
        try:
            session = self._session_or_new()
            async with session.post(token_url, data=payload) as resp:
                if resp.status in (400, 401):
                    _LOGGER.debug("Token refresh rejected (HTTP %s)", resp.status)
                    return False
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _LOGGER.debug("Network error during token refresh: %s", exc)
            return False

        if "access_token" not in data:
            return False

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._id_token = data.get("id_token", self._id_token)
        if self._debug:
            _LOGGER.debug("Token refreshed successfully")
        return True

    async def _async_recover_auth(self) -> None:
        """Token refresh → full re-login.  Raises SMAAuthError if both fail."""
        async with self._auth_lock:
            # Another coroutine may have recovered auth while we were waiting.
            # Trying refresh again is cheap and safe.
            if await self._async_refresh_token():
                return
            _LOGGER.warning("Token refresh failed; attempting full PKCE re-login")
            await self.async_login()   # raises SMAAuthError on failure

    # ── Generic HTTP wrapper ──────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Authenticated HTTP request with 401 recovery and 5xx backoff.

        Returns a dict with keys:
          - ``data``: parsed JSON body
          - ``latency_ms``: int round-trip milliseconds

        Raises:
          SMAAuthError      – auth failed and could not be recovered
          SMARateLimitError – HTTP 429
          SMAApiError       – network / 5xx / parse error
        """
        auth_retried = False
        last_exc: Exception | None = None

        for attempt in range(MAX_5XX_RETRIES):
            session = self._session_or_new()
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                **kwargs.pop("headers", {}),
            }
            try:
                t0 = time.monotonic()
                async with session.request(method, url, headers=headers, **kwargs) as resp:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    raw = await resp.text()

                    if self._debug:
                        _LOGGER.debug("%s %s → %d (%d ms)", method, url, resp.status, latency_ms)

                    if resp.status == 200:
                        if not raw.strip():
                            return {"data": {}, "latency_ms": latency_ms}
                        try:
                            import json
                            body = json.loads(raw)
                        except Exception as exc:
                            raise SMAApiError(f"JSON parse error: {exc}") from exc
                        return {"data": body, "latency_ms": latency_ms}

                    if resp.status == 401:
                        if not auth_retried:
                            auth_retried = True
                            await self._async_recover_auth()
                            # Update the Authorization header for the retry
                            kwargs["headers"] = headers
                            headers["Authorization"] = f"Bearer {self._access_token}"
                            continue
                        raise SMAAuthError("Authentication failed after token recovery")

                    if resp.status == 429:
                        raise SMARateLimitError("Rate limited by SMA API (HTTP 429)", status_code=429)

                    if resp.status >= 500:
                        # Avoid including raw response bodies in exception messages
                        # (may contain sensitive or large payloads). Keep verbose
                        # body output restricted to debug mode only.
                        last_exc = SMAApiError(f"Server error {resp.status}", status_code=resp.status)
                        if self._debug:
                            try:
                                preview = raw[:200]
                                if self._access_token:
                                    preview = preview.replace(self._access_token, "[REDACTED]")
                                _LOGGER.debug("Server response body (truncated): %s", preview)
                            except Exception:
                                _LOGGER.debug("Server response body unavailable for debug logging")
                        delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                        _LOGGER.warning(
                            "SMA API %d on attempt %d/%d – retrying in %.1fs",
                            resp.status, attempt + 1, MAX_5XX_RETRIES, delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    # Do not include raw response bodies in exception message.
                    if self._debug:
                        try:
                            preview = raw[:200]
                            if self._access_token:
                                preview = preview.replace(self._access_token, "[REDACTED]")
                            _LOGGER.debug("Unexpected HTTP %s response body (truncated): %s", resp.status, preview)
                        except Exception:
                            _LOGGER.debug("Unexpected HTTP %s and response body unavailable for debug logging", resp.status)
                    raise SMAApiError(f"Unexpected HTTP {resp.status}", status_code=resp.status)

            except (SMAAuthError, SMARateLimitError, SMAApiError):
                raise
            except aiohttp.ClientError as exc:
                last_exc = SMAApiError(f"Network error: {exc}")
                delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                _LOGGER.warning(
                    "Network error on attempt %d/%d – retrying in %.1fs: %s",
                    attempt + 1, MAX_5XX_RETRIES, delay, exc,
                )
                await asyncio.sleep(delay)
                continue

        raise last_exc or SMAApiError("Request failed after all retries")

    # ── Public API methods ────────────────────────────────────────────────────

    async def async_get_grid_management(self) -> dict[str, Any]:
        """GET /plants/{plant_id}/gridmanagement → full result dict."""
        url = f"{UIAPI_BASE}/plants/{self._plant_id}/gridmanagement"
        return await self._request("GET", url)

    async def async_set_zero_export(self, enable: bool) -> dict[str, Any]:
        """PUT /plants/{plant_id}/gridmanagement/feedinlimitation."""
        url = f"{UIAPI_BASE}/plants/{self._plant_id}/gridmanagement/feedinlimitation"
        # Spec section 4.3: enabling requires valueType field; disabling does not.
        if enable:
            payload = {"residential": {"active": True, "valueType": "ZeroExport"}}
        else:
            payload = {"residential": {"active": False}}
        return await self._request("PUT", url, json=payload)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def parse_zero_export_active(grid_data: dict[str, Any]) -> bool | None:
        """Extract residential.feedInLimitation.active from GET response."""
        try:
            return bool(grid_data["residential"]["feedInLimitation"]["active"])
        except (KeyError, TypeError):
            return None
