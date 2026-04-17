"""API client for the Sweepy integration."""

from __future__ import annotations

import time
from typing import Any

import aiohttp

from .const import API_BASE_URL, LOGGER, OAUTH_TOKEN_URL


class SweepyAuthError(Exception):
    """Raised on authentication failure."""


class SweepyApiError(Exception):
    """Raised on general API errors."""


class SweepyApiClient:
    """Async client for the Sweepy REST API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_type: str = "Bearer"
        self._expires_at: float = 0
        self._resource_owner_id: str | None = None

    @property
    def resource_owner_id(self) -> str | None:
        return self._resource_owner_id

    def get_token_data(self) -> dict[str, Any]:
        """Export current token state for persistence."""
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "token_type": self._token_type,
            "expires_at": self._expires_at,
            "resource_owner_id": self._resource_owner_id,
        }

    def set_token_data(self, data: dict[str, Any]) -> None:
        """Restore token state from persisted data."""
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        self._token_type = data.get("token_type", "Bearer")
        self._expires_at = data.get("expires_at", 0)
        self._resource_owner_id = data.get("resource_owner_id")

    async def async_login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate with email and password. Returns token data."""
        data = {
            "grant_type": "password",
            "email": email,
            "password": password,
        }
        return await self._async_token_request(data)

    async def async_refresh_token(self) -> dict[str, Any]:
        """Refresh the access token using the stored refresh token."""
        if not self._refresh_token:
            raise SweepyAuthError("No refresh token available")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        return await self._async_token_request(data)

    async def _async_token_request(self, data: dict) -> dict[str, Any]:
        """Execute token request and store credentials."""
        resp = await self._session.post(
            f"{API_BASE_URL}{OAUTH_TOKEN_URL}",
            json=data,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        if resp.status == 401 or resp.status == 400:
            body = await resp.json()
            raise SweepyAuthError(body.get("error_description", "Authentication failed"))
        resp.raise_for_status()

        result = await resp.json()
        self._access_token = result["access_token"]
        self._token_type = result.get("token_type", "Bearer")
        self._refresh_token = result["refresh_token"]
        self._expires_at = result["created_at"] + result["expires_in"]
        self._resource_owner_id = result.get("resource_owner_id")
        return result

    def _is_token_expired(self) -> bool:
        return time.time() >= self._expires_at - 60  # 60s buffer

    async def _async_ensure_token(self) -> None:
        """Refresh the token if expired."""
        if self._is_token_expired():
            LOGGER.debug("Access token expired, refreshing")
            try:
                await self.async_refresh_token()
            except (SweepyAuthError, aiohttp.ClientError):
                raise SweepyAuthError("Token refresh failed")

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"{self._token_type} {self._access_token}"}

    async def _async_get(self, path: str) -> Any:
        """Make an authenticated GET request."""
        await self._async_ensure_token()
        resp = await self._session.get(
            f"{API_BASE_URL}{path}",
            headers=self._auth_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        )
        if resp.status == 401:
            raise SweepyAuthError("Unauthorized")
        if not resp.ok:
            raise SweepyApiError(f"API error {resp.status} on {path}")
        return await resp.json()

    async def async_get_today_schedule(self) -> dict[str, Any]:
        return await self._async_get("/v1/profiles/me/today_schedule")

    async def async_get_rooms(self) -> list[dict[str, Any]]:
        return await self._async_get("/v1/rooms")

    async def async_get_profiles(self) -> list[dict[str, Any]]:
        return await self._async_get("/v1/profiles")

    async def async_get_tasks(self) -> list[dict[str, Any]]:
        return await self._async_get("/v1/tasks")

    async def async_get_homes(self) -> list[dict[str, Any]]:
        return await self._async_get("/v1/homes")

    async def async_get_schedules(self) -> list[dict[str, Any]]:
        return await self._async_get("/v1/schedules/all")

    async def async_mark_task_done(self, task_id: str) -> dict[str, Any]:
        return await self._async_get(f"/v1/tasks/{task_id}/clean")
