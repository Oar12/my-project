import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import to_checksum_address

# USDC has 6 decimal places
USDC_DECIMALS = 6

@dataclass
class Order:
    token_id: str
    price: float
    size: float
    side: str
    maker: str
    nonce: Optional[int] = None
    fee_rate_bps: int = 0
    signature_type: int = 2

    def __post_init__(self):
        """Validate and normalize order parameters."""
        self.side = self.side.upper()
        if self.side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {self.side}")

        if not 0 < self.price <= 1:
            raise ValueError(f"Invalid price: {self.price}")

        if self.size <= 0:
            raise ValueError(f"Invalid size: {self.size}")

        if self.nonce is None:
            self.nonce = int(time.time())

        # Convert to integers for blockchain
        self.maker_amount = str(int(self.size * self.price * 10**USDC_DECIMALS))
        self.taker_amount = str(int(self.size * 10**USDC_DECIMALS))
        self.side_value = 0 if self.side == "BUY" else 1

class SignerError(Exception):
    """Base exception for signer operations."""
    pass

class OrderSigner:

    # Polymarket CLOB EIP-712 domain
    DOMAIN = {
        "name": "ClobAuthDomain",
        "version": "1",
        "chainId": 137,  # Polygon mainnet
    }

    # Order type definition for EIP-712
    ORDER_TYPES = {
        "Order": [
            {"name": "salt", "type": "uint256"},
            {"name": "maker", "type": "address"},
            {"name": "signer", "type": "address"},
            {"name": "taker", "type": "address"},
            {"name": "tokenId", "type": "uint256"},
            {"name": "makerAmount", "type": "uint256"},
            {"name": "takerAmount", "type": "uint256"},
            {"name": "expiration", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "feeRateBps", "type": "uint256"},
            {"name": "side", "type": "uint8"},
            {"name": "signatureType", "type": "uint8"},
        ]
    }

    def __init__(self, private_key: str):

        if private_key.startswith("0x"):
            private_key = private_key[2:]

        try:
            self.wallet = Account.from_key(f"0x{private_key}")
        except Exception as e:
            raise ValueError(f"Invalid private key: {e}")

        self.address = self.wallet.address

    @classmethod
    def from_encrypted(
        cls,
        encrypted_data: dict,
        password: str
    ) -> "OrderSigner":

        from .crypto import KeyManager, InvalidPasswordError

        manager = KeyManager()
        private_key = manager.decrypt(encrypted_data, password)
        return cls(private_key)

    def sign_auth_message(
        self,
        timestamp: Optional[str] = None,
        nonce: int = 0
    ) -> str:

        if timestamp is None:
            timestamp = str(int(time.time()))

        # Auth message types
        auth_types = {
            "ClobAuth": [
                {"name": "address", "type": "address"},
                {"name": "timestamp", "type": "string"},
                {"name": "nonce", "type": "uint256"},
                {"name": "message", "type": "string"},
            ]
        }

        message_data = {
            "address": self.address,
            "timestamp": timestamp,
            "nonce": nonce,
            "message": "This message attests that I control the given wallet",
        }

        signable = encode_typed_data(
            domain_data=self.DOMAIN,
            message_types=auth_types,
            message_data=message_data
        )

        signed = self.wallet.sign_message(signable)
        return "0x" + signed.signature.hex()

    def sign_order(self, order: Order) -> Dict[str, Any]:

        try:
            # Build order message for EIP-712
            order_message = {
                "salt": 0,
                "maker": to_checksum_address(order.maker),
                "signer": self.address,
                "taker": "0x0000000000000000000000000000000000000000",
                "tokenId": int(order.token_id),
                "makerAmount": int(order.maker_amount),
                "takerAmount": int(order.taker_amount),
                "expiration": 0,
                "nonce": order.nonce,
                "feeRateBps": order.fee_rate_bps,
                "side": order.side_value,
                "signatureType": order.signature_type,
            }

            # Sign the order using new API format
            signable = encode_typed_data(
                domain_data=self.DOMAIN,
                message_types=self.ORDER_TYPES,
                message_data=order_message
            )

            signed = self.wallet.sign_message(signable)

            return {
                "order": {
                    "tokenId": order.token_id,
                    "price": order.price,
                    "size": order.size,
                    "side": order.side,
                    "maker": order.maker,
                    "nonce": order.nonce,
                    "feeRateBps": order.fee_rate_bps,
                    "signatureType": order.signature_type,
                },
                "signature": "0x" + signed.signature.hex(),
                "signer": self.address,
            }

        except Exception as e:
            raise SignerError(f"Failed to sign order: {e}")

    def sign_order_dict(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str,
        maker: str,
        nonce: Optional[int] = None,
        fee_rate_bps: int = 0
    ) -> Dict[str, Any]:

        order = Order(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
            maker=maker,
            nonce=nonce,
            fee_rate_bps=fee_rate_bps,
        )
        return self.sign_order(order)

    def sign_message(self, message: str) -> str:

        from eth_account.messages import encode_defunct

        signable = encode_defunct(text=message)
        signed = self.wallet.sign_message(signable)
        return "0x" + signed.signature.hex()

# Alias for backwards compatibility
WalletSigner = OrderSigner
