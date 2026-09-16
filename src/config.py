from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "keys" / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

try:
    import configuration
except ImportError:
    configuration = None


def _configured(name, env_name=None, default=None):
    """Configuration.py takes priority when its value is defined."""
    if configuration is not None and hasattr(configuration, name):
        value = getattr(configuration, name)
        if value is not None and str(value).strip().lower() != "undefined":
            return value

    if env_name is None:
        env_name = name

    value = os.getenv(env_name)
    if value is not None and value.strip().lower() != "undefined":
        return value

    return default


def env_float(name, default):
    value = _configured(name, name, default)
    return float(value)


def env_int(name, default):
    value = _configured(name, name, default)
    return int(value)


def env_bool(name, default=False):
    value = _configured(name, name, None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def credential(config_name, env_name):
    value = _configured(config_name, env_name, "")
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() == "undefined" else value


ENV_FILE_EXISTS = ENV_FILE.exists()

POLY_PRIVATE_KEY = credential("POLY_PRIVATE_KEY", "POLY_PRIVATE_KEY")
POLY_API_KEY = credential("POLY_API_KEY", "POLY_API_KEY")
POLY_API_SECRET = credential("POLY_API_SECRET", "POLY_API_SECRET")
POLY_API_PASSPHRASE = credential("POLY_API_PASSPHRASE", "POLY_API_PASSPHRASE")
POLY_FUNDER = credential("POLY_FUNDER", "POLY_FUNDER")

LIVE_CREDENTIALS_COMPLETE = all(
    (
        POLY_PRIVATE_KEY,
        POLY_API_KEY,
        POLY_API_SECRET,
        POLY_API_PASSPHRASE,
        POLY_FUNDER,
    )
)

LIVE_MODE = LIVE_CREDENTIALS_COMPLETE


@dataclass(frozen=True)
class Config:

    live_mode: bool = LIVE_MODE

    poly_clob_url: str = str(
        _configured(
            "POLY_CLOB_URL",
            "POLY_CLOB_URL",
            "https://clob.polymarket.com",
        )
    )

    poly_gamma_url: str = str(
        _configured(
            "POLY_GAMMA_URL",
            "POLY_GAMMA_URL",
            "https://gamma-api.polymarket.com",
        )
    )

    poly_chain_id: int = env_int(
        "POLY_CHAIN_ID",
        137,
    )

    poly_private_key: str = POLY_PRIVATE_KEY
    poly_api_key: str = POLY_API_KEY
    poly_api_secret: str = POLY_API_SECRET
    poly_api_passphrase: str = POLY_API_PASSPHRASE

    poly_signature_type: int = env_int(
        "POLY_SIGNATURE_TYPE",
        0,
    )

    poly_funder: str = POLY_FUNDER

    paper_starting_balance: float = env_float(
        "PAPER_STARTING_BALANCE",
        500.00,
    )

    trade_usdc: float = env_float(
        "TRADE_USDC",
        200.00,
    )

    binance_symbol: str = str(
        _configured(
            "BINANCE_SYMBOL",
            "BINANCE_SYMBOL",
            "BTCUSDT",
        )
    )

    binance_ws_url: str = str(
        _configured(
            "BINANCE_WS_URL",
            "BINANCE_WS_URL",
            "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
        )
    )

    round_seconds: int = env_int(
        "ROUND_SECONDS",
        300,
    )

    entry_window_seconds: int = env_int(
        "ENTRY_WINDOW_SECONDS",
        120,
    )

    min_move_usd: float = env_float(
        "MIN_MOVE_USD",
        70,
    )

    max_move_usd: float = env_float(
        "MAX_MOVE_USD",
        100,
    )

    min_contract_price: float = env_float(
        "MIN_CONTRACT_PRICE",
        0.75,
    )

    max_contract_price: float = env_float(
        "MAX_CONTRACT_PRICE",
        0.99,
    )

    extreme_probability: float = env_float(
        "EXTREME_PROBABILITY",
        0.95,
    )

    partial_hedge_pct: float = env_float(
        "PARTIAL_HEDGE_PCT",
        0.10,
    )

    poll_seconds: float = env_float(
        "POLL_SECONDS",
        1,
    )
