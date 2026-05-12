import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from httpx import AsyncClient

from config import Config


@dataclass
class Storage:
    accessToken: Optional[str] = None
    refreshToken: Optional[str] = None
    isProvider: Optional[bool] = None
    isImpersonating: Optional[bool] = None
    userId: Optional[int] = None
    expiresAt: Optional[datetime] = None
    refreshTimeout: Optional[datetime] = None


class Auth:
    def __init__(self, config: Config, client: AsyncClient) -> None:
        self.config = config
        self.client = client
        self._refresh_lock = asyncio.Lock()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._renewal_task: Optional[asyncio.Task] = None

        self.storage = Storage()

        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        if self._renewal_task is None or self._renewal_task.done():
            self._renewal_task = self._loop.create_task(self._token_watcher())

    async def _token_watcher(self):
        """Runs continuously in the background to proactively renew the token before it expires."""
        try:
            while True:
                if timeout := self.storage.refreshTimeout:
                    time_left = (timeout - datetime.now(timezone.utc)).total_seconds()

                    if time_left < 0:
                        await self.refresh()

                        await asyncio.sleep(5)
                        continue

                    sleep_duration = min(time_left, 600)
                    await asyncio.sleep(sleep_duration)
                else:
                    # No refresh timeout: Logged out
                    await asyncio.sleep(900)
                    continue

        except asyncio.CancelledError:
            pass

    def _updateExpiresAt(self, expires_at_unix: float) -> None:
        expires_at = datetime.fromtimestamp(expires_at_unix, tz=timezone.utc)
        tokenLife = expires_at - datetime.now(timezone.utc)

        self.storage.expiresAt = expires_at
        self.storage.refreshTimeout = datetime.now(timezone.utc) + tokenLife * 0.75

    def storeCurrentUser(self, credentials: Dict[str, Any]) -> None:
        if user_id := credentials.get("userId"):
            self.storage.userId = user_id
            self.storage.isProvider = credentials.get("isProvider", False)
            self.storage.isImpersonating = credentials.get("isImpersonating", False)
        else:
            self.storage.isProvider = None
            self.storage.isImpersonating = None

    def storeCredentials(self, credentials: Dict[str, Any]) -> None:
        self.storeCurrentUser(credentials)
        self.storage.accessToken = credentials.get("accessToken")
        self.storage.refreshToken = credentials.get("refreshToken")

        self._updateExpiresAt(credentials["expiresAt"])

    def clearCredentials(self) -> None:
        self.storage = Storage()
        raise Exception("Credentials are invalid or expired. Please log in again.")

    def dumpCredentials(self) -> None:
        with open(self.config.data_dir / "token.json", "w") as f:
            json.dump(
                {
                    "refreshToken": self.storage.refreshToken,
                    "accessToken": self.storage.accessToken,
                    "expiresAt": (
                        self.storage.expiresAt.timestamp()
                        if self.storage.expiresAt
                        else 0
                    ),
                },
                f,
                indent=4,
            )

    async def _refreshToken(self) -> bool:
        refresh_token = self.storage.refreshToken
        if not refresh_token:
            return False

        response = await self.client.post(
            f"{self.config.api_url}/token",
            headers={"Content-Type": "application/json"},
            json={"refreshToken": refresh_token},
        )

        if response.status_code != 200:
            return False

        content = response.json()

        if "accessToken" not in content or "expiresAt" not in content:
            return False

        self.storage.accessToken = content["accessToken"]

        if "refreshToken" in content:
            self.storage.refreshToken = content["refreshToken"]

        self._updateExpiresAt(content["expiresAt"])
        return True

    async def refresh(self) -> bool:
        async with self._refresh_lock:
            refresh_result = await self._refreshToken()

            if not refresh_result:
                self.clearCredentials()

            self.dumpCredentials()

            return refresh_result

    async def getAccessToken(self) -> Optional[str]:
        if self._isExpired():
            success = await self.refresh()
            if not success:
                return None

        return self.storage.accessToken

    def _isExpired(self) -> bool:
        access_token = self.storage.accessToken
        expires_at = self.storage.expiresAt

        if not access_token or not expires_at:
            return True

        try:
            return datetime.now(timezone.utc) >= expires_at
        except ValueError:
            return True

    def isLoggedIn(self) -> bool:
        return not self._isExpired()

    def isProvider(self) -> bool:
        if self._isExpired():
            return False
        return self.storage.isProvider is True

    def isImpersonating(self) -> bool:
        if self._isExpired():
            return False
        return self.storage.isImpersonating is True

    def getUserId(self) -> str:
        if self._isExpired():
            return ""
        return str(self.storage.userId or "")