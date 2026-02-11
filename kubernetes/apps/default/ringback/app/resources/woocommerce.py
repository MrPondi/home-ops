import logging
from datetime import datetime
from typing import Any

import httpx

from models import StoreConfig

logger = logging.getLogger(__name__)


class WooCommerceClientError(Exception):
    """Base exception for WooCommerce API client errors"""

    pass


class WooCommerceAuthError(WooCommerceClientError):
    """Raised when authentication fails"""

    pass


class WooCommerceAPIError(WooCommerceClientError):
    """Raised when API request fails"""

    pass


class WooCommerceClient:
    """
    Client for interacting with WooCommerce REST API.

    Supports multiple stores and handles pagination automatically.
    """

    def __init__(self, configs: list[StoreConfig], timeout: int = 30) -> None:
        """
        Initialize WooCommerce client with store configurations.

        Args:
            configs: List of store configurations
            timeout: Default timeout for HTTP requests in seconds

        Raises:
            WooCommerceClientError: If no valid sites configured
        """
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
        self.sites: dict[str, dict[str, str]] = {}

        for site_data in configs:
            site = {
                "api_url": f"https://{site_data.url}/wp-json/wc/v3",
                "consumer_key": site_data.secrets.consumer_key,
                "consumer_secret": site_data.secrets.consumer_secret,
            }
            # Use the cleaned URL as the key
            self.sites[site_data.url] = site

        if not self.sites:
            raise WooCommerceClientError("No valid sites configured")

        logger.info(f"Initialized WooCommerce client with {len(self.sites)} store(s)")

    def __del__(self):
        """Close HTTP client on cleanup"""
        if hasattr(self, "client"):
            self.client.close()

    def get_orders(
        self,
        site: dict[str, str],
        page: int = 1,
        per_page: int = 20,
        **params: Any,
    ) -> list[dict[str, Any]]:
        """
        Fetch orders from a WooCommerce store.

        Args:
            site: Site configuration dictionary with api_url and credentials
            page: Page number (1-indexed)
            per_page: Number of orders per page
            **params: Additional query parameters to filter orders
                      (e.g., status='processing', after='2025-01-01T00:00:00')

        Returns:
            List of order dictionaries

        Raises:
            WooCommerceAPIError: If there's an error fetching orders
        """
        endpoint = f"{site['api_url']}/orders"

        # Build query parameters
        query_params = {"page": page, "per_page": per_page, **params}

        try:
            response = self.client.get(
                endpoint,
                params=query_params,
                auth=(site["consumer_key"], site["consumer_secret"]),
            )
            response.raise_for_status()

            orders = response.json()

            if not isinstance(orders, list):
                raise WooCommerceAPIError(
                    f"Unexpected response format: expected list, got {type(orders)}"
                )

            return orders

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code} error fetching orders"

            # Try to extract error message from response
            try:
                error_detail = e.response.json()
                if isinstance(error_detail, dict):
                    error_msg += f": {error_detail.get('message', error_detail)}"
                else:
                    error_msg += f": {error_detail}"
            except Exception:
                error_msg += f": {e.response.text[:200]}"  # First 200 chars

            # Check if it's an auth error
            if e.response.status_code in (401, 403):
                raise WooCommerceAuthError(error_msg) from e

            raise WooCommerceAPIError(error_msg) from e

        except httpx.HTTPError as e:
            raise WooCommerceAPIError(f"HTTP error fetching orders: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error fetching orders: {e}")
            raise WooCommerceAPIError(f"Unexpected error fetching orders: {e}") from e

    def get_all_orders(
        self, after: datetime, per_page: int = 100, **extra_params: Any
    ) -> list[dict[str, Any]]:
        """
        Fetch all orders from all configured stores after a specific date.

        Note: WooCommerce filters orders by creation date when using 'after' parameter.
        We don't use 'before' because we want to catch orders placed after calls.

        Args:
            after: Fetch orders created after this datetime
            per_page: Number of orders per page
            **extra_params: Additional query parameters (e.g., status filters)

        Returns:
            List of all orders from all stores

        Raises:
            WooCommerceAPIError: If there's a critical error (logs non-critical errors)
        """
        all_orders = []

        if not self.sites:
            logger.warning("No sites configured. Cannot fetch orders.")
            return all_orders

        # Format date for WooCommerce API (ISO 8601)
        after_iso = after.isoformat()

        logger.info(
            f"Fetching orders created after {after_iso} from {len(self.sites)} store(s)"
        )

        for store_name, site in self.sites.items():
            page = 1
            store_orders = []

            # Build parameters for this store
            params = {"after": after_iso, **extra_params}

            try:
                while True:
                    logger.debug(f"Fetching page {page} of orders from {store_name}")

                    try:
                        orders = self.get_orders(
                            site=site, page=page, per_page=per_page, **params
                        )
                    except WooCommerceAuthError as e:
                        logger.error(
                            f"Authentication error for {store_name}: {e}. "
                            "Check your consumer_key and consumer_secret."
                        )
                        break  # Skip this store
                    except WooCommerceAPIError as e:
                        logger.error(
                            f"API error fetching orders from {store_name}: {e}"
                        )
                        break  # Skip this store

                    if not orders:
                        logger.debug(f"No more orders on page {page} for {store_name}")
                        break

                    store_orders.extend(orders)
                    logger.info(
                        f"Fetched {len(orders)} orders from {store_name} (page {page})"
                    )

                    # If we got fewer results than requested, we're on the last page
                    if len(orders) < per_page:
                        logger.debug(
                            f"Page {page} had fewer than {per_page} orders, "
                            f"stopping pagination for {store_name}"
                        )
                        break

                    page += 1

                all_orders.extend(store_orders)
                logger.info(
                    f"Successfully fetched {len(store_orders)} total orders from {store_name}"
                )

            except Exception as e:
                logger.error(f"Unexpected error fetching orders from {store_name}: {e}")
                # Continue with other stores rather than failing completely
                continue

        logger.info(f"Fetched {len(all_orders)} total orders from all stores")
        return all_orders
