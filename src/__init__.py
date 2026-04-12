from .bot import TradingBot, OrderResult
from .signer import OrderSigner, Order
from .client import ApiClient, ClobClient, RelayerClient
from .crypto import KeyManager
from .config import Config, BuilderConfig
from .gamma_client import GammaClient
from .websocket_client import MarketWebSocket, OrderbookManager, OrderbookSnapshot

# Utility functions
from .utils import (
    create_bot_from_env,
    validate_address,
    validate_private_key,
    format_price,
    format_usdc,
    truncate_address,
)

__version__ = "1.0.0"
__author__ = "Polymarket Trading Bot Contributors"

__all__ = [
    # Core classes
    "TradingBot",
    "OrderResult",
    "OrderSigner",
    "Order",
    "ApiClient",
    "ClobClient",
    "RelayerClient",
    "KeyManager",
    "Config",
    "BuilderConfig",
    "GammaClient",
    "MarketWebSocket",
    "OrderbookManager",
    "OrderbookSnapshot",
    # Utility functions
    "create_bot_from_env",
    "validate_address",
    "validate_private_key",
    "format_price",
    "format_usdc",
    "truncate_address",
]
