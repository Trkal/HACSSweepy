"""API client for the Sweepy integration."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import aiohttp

from .const import API_BASE_URL, LOGGER, OAUTH_TOKEN_URL, TOKEN_EXPIRY_BUFFER


class SweepyAuthError(Exception):
    """Raised on authentication failure."""


class SweepyApiError(Exception):
    """Raised on general API errors."""


class SweepyApiClient:
    """Async client for the Sweepy REST API.

    Sweepy's OAuth server rotates refresh tokens: using one issues a new token
    and revokes the old one. All token handling therefore runs under a single
    lock, so concurrent callers can never spend the same refresh token twice.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str | None = None,
        password: str | None = None,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token_callback = token_callback
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_type: str = "Bearer"
        self._expires_at: float = 0
        self._resource_owner_id: str | None = None
        self._lock = asyncio.Lock()
        # Bumped on every successful token request. Lets a caller say "the
        # token I just used was rejected" without clobbering a newer one that
        # a concurrent caller may have obtained in the meantime.
        self._generation = 0

    @property
    def resource_owner_id(self) -> str | None:
        return self._resource_owner_id

    @property
    def token_generation(self) -> int:
        return self._generation

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
        async with self._lock:
            return await self._async_login_locked(email, password)

    async def async_refresh_token(self) -> dict[str, Any]:
        """Refresh the access token using the stored refresh token."""
        async with self._lock:
            return await self._async_refresh_token_locked()

    async def async_ensure_authenticated(
        self, stale_generation: int | None = None
    ) -> None:
        """Make sure a usable access token is available.

        This is the single entry point for authentication. It is serialised, so
        a burst of concurrent API calls triggers exactly one token request: the
        losers of the race acquire the lock after the winner has already stored
        a fresh token, see it is valid, and return without touching the network.

        Pass `stale_generation` (the value of `token_generation` read before the
        request that got a 401) to force a re-auth of that specific token. If a
        concurrent caller has already replaced it, this returns without issuing
        a redundant request -- otherwise a burst of 401s would stampede exactly
        like an expiry burst does.

        If the refresh token has been revoked, fall back to a password login
        using the stored credentials, so a broken refresh chain heals itself
        instead of prompting the user to reauthenticate.
        """
        async with self._lock:
            if stale_generation is None:
                if self._access_token and not self._is_token_expired():
                    return
            elif self._generation != stale_generation:
                return

            if self._refresh_token:
                try:
                    await self._async_refresh_token_locked()
                    return
                except SweepyAuthError as err:
                    LOGGER.debug(
                        "Refresh token rejected (%s), falling back to password login",
                        err,
                    )

            if not (self._email and self._password):
                raise SweepyAuthError(
                    "Token refresh failed and no stored credentials are available"
                )

            await self._async_login_locked(self._email, self._password)

    async def _async_login_locked(self, email: str, password: str) -> dict[str, Any]:
        """Password grant. Caller must hold the lock."""
        return await self._async_token_request(
            {
                "grant_type": "password",
                "email": email,
                "password": password,
            }
        )

    async def _async_refresh_token_locked(self) -> dict[str, Any]:
        """Refresh token grant. Caller must hold the lock."""
        if not self._refresh_token:
            raise SweepyAuthError("No refresh token available")
        return await self._async_token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            }
        )

    async def _async_token_request(self, data: dict) -> dict[str, Any]:
        """Execute token request and store credentials. Caller must hold the lock."""
        resp = await self._session.post(
            f"{API_BASE_URL}{OAUTH_TOKEN_URL}",
            json=data,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        if resp.status in (400, 401):
            try:
                body = await resp.json()
            except (aiohttp.ClientError, ValueError):
                body = {}
            raise SweepyAuthError(body.get("error_description", "Authentication failed"))
        resp.raise_for_status()

        result = await resp.json()
        self._access_token = result["access_token"]
        self._token_type = result.get("token_type", "Bearer")
        # A rotating server returns a new refresh token on every grant, but a
        # non-rotating one may omit it — never clobber a working token with None.
        if result.get("refresh_token"):
            self._refresh_token = result["refresh_token"]
        # Derive expiry from the local clock rather than the server's created_at,
        # since it is the local clock we later compare against.
        expires_in = result.get("expires_in", 7200)
        self._expires_at = time.time() + expires_in
        self._resource_owner_id = result.get(
            "resource_owner_id", self._resource_owner_id
        )
        self._generation += 1
        LOGGER.debug(
            "Obtained Sweepy access token via %s grant, valid for %s seconds",
            data["grant_type"],
            expires_in,
        )
        self._notify_token_updated()
        return result

    def _notify_token_updated(self) -> None:
        """Hand the rotated token to the owner so it is persisted immediately."""
        if self._token_callback is not None:
            self._token_callback(self.get_token_data())

    def _is_token_expired(self) -> bool:
        return time.time() >= self._expires_at - TOKEN_EXPIRY_BUFFER

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"{self._token_type} {self._access_token}"}

    async def _async_raw_get(self, path: str) -> aiohttp.ClientResponse:
        return await self._session.get(
            f"{API_BASE_URL}{path}",
            headers=self._auth_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        )

    async def _async_get(self, path: str) -> Any:
        """Make an authenticated GET request, re-authenticating once on a 401."""
        await self.async_ensure_authenticated()
        generation = self._generation
        resp = await self._async_raw_get(path)

        if resp.status == 401:
            # The token was invalidated server-side before its stated expiry.
            LOGGER.debug("Got 401 on %s, re-authenticating and retrying", path)
            await self.async_ensure_authenticated(stale_generation=generation)
            resp = await self._async_raw_get(path)
            if resp.status == 401:
                raise SweepyAuthError(f"Unauthorized on {path} after re-authentication")

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
