from pydantic import BaseModel, Field, field_validator

"""
Data models for the call-order synchronization system.

These models use Pydantic for validation and serialization of configuration data.
"""


class PBXConfig(BaseModel):
    """
    Configuration for Play PBX API authentication.

    Attributes:
        client_id: OAuth client ID for PBX API
        client_secret: OAuth client secret for PBX API
    """

    client_id: str = Field(..., min_length=1, description="PBX API client ID")
    client_secret: str = Field(..., min_length=1, description="PBX API client secret")


class ApiCredentials(BaseModel):
    """
    WooCommerce API credentials.

    Attributes:
        consumer_key: WooCommerce consumer key
        consumer_secret: WooCommerce consumer secret
    """

    consumer_key: str = Field(..., min_length=1, description="WooCommerce consumer key")
    consumer_secret: str = Field(
        ..., min_length=1, description="WooCommerce consumer secret"
    )


class StoreConfig(BaseModel):
    """
    Configuration for a single WooCommerce store.

    Attributes:
        url: Store domain (e.g., 'example.com' or 'shop.example.com')
        secrets: API credentials for this store
    """

    url: str = Field(..., min_length=1, description="Store domain without protocol")
    secrets: ApiCredentials

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Remove protocol and trailing slashes from URL"""
        # Remove protocol if present
        v = v.replace("https://", "").replace("http://", "")
        # Remove trailing slashes
        v = v.rstrip("/")
        # Remove port specification if present (we'll use HTTPS by default)
        v = v.split(":")[0]
        return v


class SyncConfig(BaseModel):
    """
    Main configuration for the sync system.

    Attributes:
        ntfy_channel: Channel name for ntfy.sh notifications
        pbx_config: PBX API configuration
        woocommerce_stores: List of WooCommerce store configurations
    """

    ntfy_channel: str = Field(..., min_length=1, description="ntfy.sh channel name")
    pbx_config: PBXConfig
    woocommerce_stores: list[StoreConfig] = Field(
        min_length=1, description="At least one store required"
    )

    @field_validator("woocommerce_stores")
    @classmethod
    def validate_stores(cls, v: list[StoreConfig]) -> list[StoreConfig]:
        """Ensure at least one store is configured"""
        if not v:
            raise ValueError("At least one WooCommerce store must be configured")
        return v
