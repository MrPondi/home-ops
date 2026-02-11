import logging
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from models import SyncConfig
from play import PBXClient, PBXClientError
from woocommerce import WooCommerceClient, WooCommerceClientError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DB_PATH = "/data/notified_calls.db"
CONFIG_PATH = "/config/config.json"
TIMEOUT_DAYS = 7  # Check calls from the last 7 days
RETRY_WINDOW_DAYS = 14  # Check unnotified calls up to 14 days
PHONE_NUMBER_LENGTH = 9  # Polish phone numbers (without country code)


class NotificationError(Exception):
    """Custom exception for notification failures"""

    pass


def normalize_phone_number(phone: str, country_code: str = "48") -> Optional[str]:
    """
    Normalize phone number to standard format: country code + number.

    Args:
        phone: Raw phone number from order
        country_code: Country code to prepend

    Returns:
        Normalized phone number or None if invalid
    """
    if not phone:
        return None

    # Remove all formatting characters
    cleaned = (
        phone.replace(" ", "")
        .replace("-", "")
        .replace("+", "")
        .replace("(", "")
        .replace(")", "")
    )

    # Take last N digits (handles cases where country code might already be included)
    if len(cleaned) < PHONE_NUMBER_LENGTH:
        logger.warning(f"Phone number too short after cleaning: {phone} -> {cleaned}")
        return None

    number_part = cleaned[-PHONE_NUMBER_LENGTH:]
    normalized = f"{country_code}{number_part}"

    logger.debug(f"Normalized {phone} -> {normalized}")
    return normalized


def initialize_database(db_path: str) -> None:
    """
    Initialize the SQLite database with required tables and indexes.

    Args:
        db_path: Path to the SQLite database file
    """
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notified_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calling_number TEXT UNIQUE NOT NULL,
                    first_call_date TEXT,
                    notification_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_calling_number
                ON notified_calls(calling_number)
            """)

            conn.commit()
    logger.info("Database initialized successfully")


def load_config(config_path: str) -> SyncConfig:
    """
    Load and validate configuration from JSON file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Validated SyncConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = SyncConfig.model_validate_json(f.read())
        logger.info("Configuration loaded successfully")
        return config_data
    except Exception as e:
        raise ValueError(f"Invalid configuration file: {e}") from e


def send_notification(channel: str, phone_number: str, timeout: int = 10) -> None:
    """
    Send notification via ntfy.sh.

    Args:
        channel: ntfy.sh channel name
        phone_number: The calling phone number
        timeout: Request timeout in seconds

    Raises:
        NotificationError: If notification fails
    """
    url = f"https://ntfy.sh/{channel}"
    message = f"Klient dzwoniący z numeru {phone_number} nie złożył zamówienia"

    try:
        response = httpx.post(
            url,
            content=message.encode("utf-8"),
            headers={
                "Title": "Klient bez zakupu",
                "Click": f"tel:+{phone_number}",
                "Priority": "default",
                "Tags": "telephone,warning",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        logger.info(f"Notification sent successfully for {phone_number}")
    except httpx.HTTPError as e:
        raise NotificationError(f"Failed to send notification: {e}") from e


def mark_as_notified(
    conn: sqlite3.Connection, phone_number: str, call_date: Optional[str] = None
) -> None:
    """
    Mark a phone number as notified in the database.

    Args:
        conn: SQLite database connection
        phone_number: The phone number to mark
        call_date: Optional date of the first call
    """
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            INSERT INTO notified_calls (calling_number, first_call_date, notification_date)
            VALUES (?, ?, ?)
            ON CONFLICT(calling_number) DO NOTHING
            """,
            (phone_number, call_date, datetime.now().isoformat()),
        )
        conn.commit()


def is_already_notified(conn: sqlite3.Connection, phone_number: str) -> bool:
    """
    Check if a phone number has already been notified.

    Args:
        conn: SQLite database connection
        phone_number: The phone number to check

    Returns:
        True if already notified, False otherwise
    """
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            "SELECT 1 FROM notified_calls WHERE calling_number = ?", (phone_number,)
        )
        result = cursor.fetchone()
        return result is not None


def build_order_phone_set(orders: list[dict], country_code: str = "48") -> set[str]:
    """
    Build a set of normalized phone numbers from orders for O(1) lookup.

    Args:
        orders: List of WooCommerce orders
        country_code: Country code for phone normalization

    Returns:
        Set of normalized phone numbers
    """
    phone_set = set()
    excluded_statuses = {"checkout-draft", "trash", "auto-draft"}

    for order in orders:
        # Skip orders with excluded statuses
        if order.get("status") in excluded_statuses:
            continue

        # Safely get phone number from billing info
        billing = order.get("billing", {})
        if not isinstance(billing, dict):
            continue

        phone = billing.get("phone")
        if phone:
            normalized = normalize_phone_number(phone, country_code)
            if normalized:
                phone_set.add(normalized)
                logger.debug(f"Added order #{order.get('id')} phone: {normalized}")

    logger.info(
        f"Built phone set with {len(phone_set)} unique numbers from {len(orders)} orders"
    )
    return phone_set


def process_calls(
    calls: list[dict],
    order_phones: set[str],
    config: SyncConfig,
    db_conn: sqlite3.Connection,
) -> tuple[int, int, int]:
    """
    Process calls and send notifications for those without matching orders.

    Args:
        calls: List of calls from PBX
        order_phones: Set of phone numbers with orders
        config: Sync configuration
        db_conn: Database connection

    Returns:
        Tuple of (processed, matched, notified) counts
    """
    processed = 0
    matched = 0
    notified = 0

    for call in calls:
        processed += 1
        calling_number = call.get("callingNumber")

        if not calling_number:
            logger.warning(f"Call missing callingNumber field: {call}")
            continue

        logger.debug(f"Processing call from {calling_number}")

        # Check if this number has an associated order
        if calling_number in order_phones:
            logger.info(f"✓ Match found: {calling_number} has an order")
            matched += 1
            continue

        # Check if we already notified about this number
        if is_already_notified(db_conn, calling_number):
            logger.debug(f"Already notified about {calling_number}, skipping")
            continue

        # Send notification for call without order
        try:
            send_notification(config.ntfy_channel, calling_number)
            mark_as_notified(
                db_conn,
                calling_number,
                call.get("timestamp"),  # Store when they called if available
            )
            notified += 1
        except NotificationError as e:
            logger.error(f"Failed to notify about {calling_number}: {e}")
            # Continue processing other calls even if one notification fails
            continue

    return processed, matched, notified


def main() -> int:
    """
    Main entry point for the call-order sync script.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Initialize database
        logger.info("Starting call-order sync process")
        initialize_database(DB_PATH)

        # Load configuration
        config = load_config(CONFIG_PATH)

        # Calculate date ranges
        date_before = (datetime.now() - timedelta(days=TIMEOUT_DAYS)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        date_after = (datetime.now() - timedelta(days=RETRY_WINDOW_DAYS)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        logger.info(
            f"Checking calls from {date_after.strftime('%Y-%m-%d')} to {date_before.strftime('%Y-%m-%d')}"
        )
        logger.info(f"Checking orders from {date_after.strftime('%Y-%m-%d')} onwards")

        # Initialize API clients
        pbx_client = PBXClient(config.pbx_config)
        wc_client = WooCommerceClient(config.woocommerce_stores)

        # Fetch data from APIs
        logger.info("Fetching call history from PBX...")
        calls = pbx_client.get_all_call_history(after=date_after, before=date_before)

        logger.info("Fetching orders from WooCommerce...")
        orders = wc_client.get_all_orders(after=date_after)

        logger.info(f"Fetched {len(calls)} calls and {len(orders)} orders")

        if not calls:
            logger.info("No calls to process")
            return 0

        # Build set of phone numbers that have orders (O(n) instead of O(n²))
        order_phones = build_order_phone_set(orders, country_code="48")

        # Process calls and send notifications
        with closing(sqlite3.connect(DB_PATH)) as db_conn:
            processed, matched, notified = process_calls(
                calls, order_phones, config, db_conn
            )

        # Summary
        logger.info("=" * 60)
        logger.info("Processing complete:")
        logger.info(f"  - Calls processed: {processed}")
        logger.info(f"  - Calls with orders: {matched}")
        logger.info(f"  - New notifications sent: {notified}")
        logger.info(f"  - Calls without orders: {processed - matched}")
        logger.info("=" * 60)

        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except (PBXClientError, WooCommerceClientError) as e:
        logger.error(f"API error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
