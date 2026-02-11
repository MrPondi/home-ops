import logging
from base64 import b64encode
from datetime import datetime
from json import JSONDecodeError
from typing import Any

import httpx

from models import PBXConfig

logger = logging.getLogger(__name__)


class PBXClientError(Exception):
    """Base exception for PBX client errors"""

    pass


class PBXAuthenticationError(PBXClientError):
    """Raised when authentication fails"""

    pass


class PBXAPIError(PBXClientError):
    """Raised when API request fails"""

    pass


class PBXClient:
    """
    Client for interacting with Play PBX (Wirtualna Centrala) API.

    This client handles authentication and fetching call history data.
    """

    BASE_URL = "https://uslugidlafirm.play.pl"
    AUTH_ENDPOINT = "/oauth/token-jwt"
    CALL_HISTORY_ENDPOINT = "/api/wirtualnacentralka/getCallHistory"

    def __init__(self, config: PBXConfig, timeout: int = 30):
        """
        Initialize PBX client and authenticate.

        Args:
            config: PBX configuration with credentials
            timeout: Default timeout for HTTP requests in seconds

        Raises:
            PBXAuthenticationError: If authentication fails
        """
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
        self.jwt_token = self._authenticate(config.client_id, config.client_secret)

    def __del__(self):
        """Close HTTP client on cleanup"""
        if hasattr(self, "client"):
            self.client.close()

    def _authenticate(self, client_id: str, client_secret: str) -> str:
        """
        Authenticate with the PBX API and obtain JWT token.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Returns:
            JWT access token

        Raises:
            PBXAuthenticationError: If authentication fails
        """
        auth_str = f"{client_id}:{client_secret}"
        b64_auth_str = b64encode(auth_str.encode()).decode()

        url = f"{self.BASE_URL}{self.AUTH_ENDPOINT}"
        headers = {"Authorization": f"Basic {b64_auth_str}"}

        try:
            response = self.client.post(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            token = data.get("access_token")

            if not token:
                raise PBXAuthenticationError("No access token in response")

            logger.info("Successfully authenticated to Play PBX API")
            return token

        except JSONDecodeError as e:
            raise PBXAuthenticationError(
                "Invalid JSON response from auth endpoint"
            ) from e
        except httpx.HTTPStatusError as e:
            error_msg = f"Authentication failed with status {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg += f": {error_detail}"
            except JSONDecodeError:
                error_msg += f": {e.response.text}"
            raise PBXAuthenticationError(error_msg) from e
        except httpx.HTTPError as e:
            raise PBXAuthenticationError(
                f"HTTP error during authentication: {e}"
            ) from e

    def get_call_history(
        self,
        page: int = 1,
        per_page: int = 20,
        **params: Any,
    ) -> list[dict[str, Any]]:
        """
        Fetch a single page of call history from the PBX API.

        Args:
            page: Page number (1-indexed)
            per_page: Number of records per page
            **params: Additional query parameters (e.g., fromDate, toDate)

        Returns:
            List of call records

        Raises:
            PBXAPIError: If the API request fails
        """
        url = f"{self.BASE_URL}{self.CALL_HISTORY_ENDPOINT}"

        # Build query parameters
        query_params = {
            "page": page,
            "size": per_page,
            "orderProp": "timestamp",
            "orderDir": "asc",
            **params,
        }

        headers = {"Authorization": f"Bearer {self.jwt_token}"}

        try:
            response = self.client.get(url, headers=headers, params=query_params)
            response.raise_for_status()

            data = response.json()
            calls = data.get("calls", [])

            if not isinstance(calls, list):
                raise PBXAPIError("Unexpected response format: 'calls' is not a list")

            return calls

        except JSONDecodeError as e:
            raise PBXAPIError("Invalid JSON response from call history endpoint") from e
        except httpx.HTTPStatusError as e:
            error_msg = (
                f"Failed to fetch call history (status {e.response.status_code})"
            )
            try:
                error_detail = e.response.json()
                error_msg += f": {error_detail}"
            except JSONDecodeError:
                error_msg += f": {e.response.text}"
            raise PBXAPIError(error_msg) from e
        except httpx.HTTPError as e:
            raise PBXAPIError(f"HTTP error fetching call history: {e}") from e

    def get_all_call_history(
        self, after: datetime, before: datetime, per_page: int = 100
    ) -> list[dict[str, Any]]:
        """
        Fetch all call history records within a date range using pagination.

        Args:
            after: Fetch calls after this datetime
            before: Fetch calls before this datetime
            per_page: Number of records per page

        Returns:
            List of all call records in the date range

        Raises:
            PBXAPIError: If the API request fails
        """

        all_calls = []
        page = 1

        # Format dates for API
        params = {
            "fromDate": after.strftime("%Y-%m-%d %H:%M"),
            "toDate": before.strftime("%Y-%m-%d %H:%M"),
        }

        logger.info(
            f"Fetching call history from {params['fromDate']} to {params['toDate']}"
        )

        while True:
            logger.debug(f"Fetching page {page} of call history")

            try:
                calls = self.get_call_history(page=page, per_page=per_page, **params)
            except PBXAPIError as e:
                logger.error(f"Error fetching page {page}: {e}")
                # If we got some data already, return what we have
                if all_calls:
                    logger.warning(
                        f"Returning {len(all_calls)} calls fetched before error"
                    )
                    return all_calls
                # Otherwise, re-raise the error
                raise

            if not calls:
                logger.debug(f"No more calls on page {page}, stopping pagination")
                break

            all_calls.extend(calls)
            logger.info(f"Fetched {len(calls)} call records from page {page}")

            # If we got fewer results than requested, we're on the last page
            if len(calls) < per_page:
                logger.debug(
                    f"Page {page} had fewer than {per_page} records, stopping pagination"
                )
                break

            page += 1

        logger.info(f"Successfully fetched {len(all_calls)} total call records")
        return all_calls
