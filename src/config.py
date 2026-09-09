from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "keys" / ".env"

# -------------------------------------------------------------
# LOAD ENV
# -------------------------------------------------------------

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def env_float(name, default):
    return float(os.getenv(name, default))


def env_int(name, default):
    return int(os.getenv(name, default))


def env_bool(name, default=False):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# -------------------------------------------------------------
# MODE
# -------------------------------------------------------------
# PAPER is the default.
#
# LIVE is enabled only when:
# - keys/.env exists
# - private key exists
# - API key exists
# - API secret exists
# - API passphrase exists
#
# This prevents accidentally sending real orders.
# -------------------------------------------------------------

ENV_FILE_EXISTS = ENV_FILE.exists()

LIVE_CREDENTIALS_COMPLETE = (
    bool(os.getenv("POLY_PRIVATE_KEY"))
    and bool(os.getenv("POLY_API_KEY"))
    and bool(os.getenv("POLY_API_SECRET"))
    and bool(os.getenv("POLY_API_PASSPHRASE"))
)

LIVE_MODE = (
    ENV_FILE_EXISTS
    and LIVE_CREDENTIALS_COMPLETE
)


@dataclass(frozen=True)
class Config:

    # =========================================================
    # MODE
    # =========================================================

    live_mode: bool = LIVE_MODE

    # =========================================================
    # POLYMARKET
    # =========================================================

    poly_clob_url: str = os.getenv(
        "POLY_CLOB_URL",
        "https://clob.polymarket.com",
    )

    poly_gamma_url: str = os.getenv(
        "POLY_GAMMA_URL",
        "https://gamma-api.polymarket.com",
    )

    poly_chain_id: int = env_int(
        "POLY_CHAIN_ID",
        137,
    )

    poly_private_key: str = os.getenv(
        "POLY_PRIVATE_KEY",
        "",
    )

    poly_api_key: str = os.getenv(
        "POLY_API_KEY",
        "",
    )

    poly_api_secret: str = os.getenv(
        "POLY_API_SECRET",
        "",
    )

    poly_api_passphrase: str = os.getenv(
        "POLY_API_PASSPHRASE",
        "",
    )

    poly_signature_type: int = env_int(
        "POLY_SIGNATURE_TYPE",
        0,
    )

    poly_funder: str = os.getenv(
        "POLY_FUNDER",
        "",
    )

    # =========================================================
    # PAPER ACCOUNT
    # =========================================================

    paper_starting_balance: float = env_float(
        "PAPER_STARTING_BALANCE",
        500.00,
    )

    # =========================================================
    # TRADE SIZE
    # =========================================================

    trade_usdc: float = env_float(
        "TRADE_USDC",
        200.00,
    )

    # =========================================================
    # BINANCE
    # =========================================================

    binance_symbol: str = os.getenv(
        "BINANCE_SYMBOL",
        "BTCUSDT",
    )

    binance_ws_url: str = os.getenv(
        "BINANCE_WS_URL",
        "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
    )

    # =========================================================
    # STRATEGY
    # =========================================================

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
