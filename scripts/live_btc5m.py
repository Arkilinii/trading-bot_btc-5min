#!/usr/bin/env python3

import asyncio
import logging
import os
import sys
import time


sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(__file__)
    ),
)


from src.config import Config
from src.binance_feed import BinanceFeed
from src.polymarket import Polymarket
from src.strategy import Strategy


# =============================================================
# LOGGING
# =============================================================

from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOG_DIR = ROOT / "logs" / "paper"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "paper.log"


file_handler = TimedRotatingFileHandler(
    filename=LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=90,
    encoding="utf-8",
)

file_handler.suffix = "%Y-%m-%d"


console_handler = logging.StreamHandler()


formatter = logging.Formatter(
    "%(asctime)s | %(message)s"
)


file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)


logger = logging.getLogger()

logger.setLevel(logging.INFO)

logger.handlers.clear()

logger.addHandler(file_handler)
logger.addHandler(console_handler)


# =============================================================
# COLORS
# =============================================================

GREEN = "\033[32m"
RED = "\033[31m"
ORANGE = "\033[38;5;208m"
BLUE = "\033[34m"
RESET = "\033[0m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"


async def main():

    cfg = Config()

    # =========================================================
    # SAFETY CHECK
    # =========================================================

    if not cfg.live_mode:

        raise SystemExit(
            "LIVE MODE requested but "
            "keys/.env does not contain "
            "complete Polymarket credentials."
        )

    if not cfg.poly_funder:

        raise SystemExit(
            "Missing POLY_FUNDER in keys/.env"
        )

    # =========================================================
    # CONNECTIONS
    # =========================================================

    poly = Polymarket(cfg)

    poly.check_auth()

    feed = BinanceFeed(
        cfg.binance_ws_url
    )

    strategy = Strategy(
        cfg,
        paper=False,
    )

    # =========================================================
    # ACCOUNT
    # =========================================================

    account_address = (
        poly.account_address()
    )

    try:

        live_balance = (
            poly.get_balance()
        )

    except Exception as exc:

        raise SystemExit(
            "Could not read live balance: "
            f"{exc}"
        )

    logging.warning(
        RED
        + BOLD
        + "================ LIVE MODE ================"
        + RESET
    )

    logging.warning(
        RED
        + BOLD
        + "REAL ORDERS WILL BE SENT!"
        + RESET
    )

    logging.info(
        BOLD
        + "Address: %s"
        + RESET,
        account_address,
    )

    logging.info(
        BOLD
        + "Account balance: $%.2f"
        + RESET,
        live_balance,
    )

    logging.info(
        BOLD
        + "Entry size: $%.2f"
        + RESET,
        cfg.trade_usdc,
    )

    logging.warning(
        RED
        + BOLD
        + "============================================"
        + RESET
    )

    # =========================================================
    # BINANCE
    # =========================================================

    asyncio.create_task(
        feed.run()
    )

    await asyncio.sleep(2)

    last_log = 0

    # =========================================================
    # MAIN LOOP
    # =========================================================

    while True:

        if feed.state.price is None:

            await asyncio.sleep(
                0.5
            )

            continue

        now = time.time()

        try:

            market = poly.get_market()

            decision = strategy.evaluate(
                now,
                feed.state.price,
                market,
                poly,
            )

            elapsed = (
                now
                - (
                    int(
                        now
                        // cfg.round_seconds
                    )
                    * cfg.round_seconds
                )
            )

            remaining = (
                cfg.round_seconds
                - elapsed
            )

            # =================================================
            # PERIODIC STATUS
            # =================================================

            if now - last_log >= 2:

                if now - last_log >= 2:

                    logging.info(
                        "Live | "
                        "Time: %.0fs | "
                        "BTC: $%.2f %+.2f | "
                        "Action: %s %s | "
                        "Range: %s | "
                        "Dir: %s",

                        remaining,

                        feed.state.price,

                        decision.move,

                        decision.action,

                        decision.reason,

                        (
                            f"{decision.contract_price:.2f}"
                            if decision.contract_price
                            is not None
                            else "?"
                        ),

                        decision.direction
                        or "?",
                    )

                    last_log = now

            # =================================================
            # ENTRY
            # =================================================

            if (
                decision.action == "ENTER"
                and not strategy.entered
            ):

                if (
                    decision.contract_price
                    is None
                    or decision.contract_price <= 0
                ):

                    logging.warning(
                        "Live | Invalid entry price"
                    )

                    continue

                # -------------------------------------------------
                # CHECK CURRENT BALANCE
                # -------------------------------------------------

                live_balance = (
                    poly.get_balance()
                )

                if live_balance < cfg.trade_usdc:

                    logging.warning(
                        RED
                        + BOLD
                        + "Live | Entry skipped | "
                        "Balance $%.2f < entry $%.2f"
                        + RESET,
                        live_balance,
                        cfg.trade_usdc,
                    )

                    continue

                # -------------------------------------------------
                # REAL BUY
                # -------------------------------------------------

                response = poly.buy(
                    strategy.position_token,
                    cfg.trade_usdc,
                )

                price = (
                    decision.contract_price
                )

                # Conservative accounting.
                #
                # The actual fill should later be reconciled
                # from the returned order/trade data.
                shares = (
                    cfg.trade_usdc
                    / price
                )

                strategy.record_entry(
                    decision.move,
                    price,
                    cfg.trade_usdc,
                    shares,
                )

                logging.info(
                    ORANGE
                    + BOLD
                    + UNDERLINE
                    + "Live | Entry | "
                    "Round: %s | "
                    "Dir: %s | "
                    "Move: %+.2f | "
                    "Price: %.4f | "
                    "Shares: %.4f | "
                    "Stake: $%.2f"
                    + RESET,

                    strategy.round_id,

                    strategy.position_direction
                    or "-",

                    decision.move,

                    price,

                    shares,

                    cfg.trade_usdc,
                )

                logging.info(
                    "Live | Entry response: %s",
                    response,
                )

            # =================================================
            # HOLD / HEDGE
            # =================================================

            elif (
                decision.action == "HOLD"
                and strategy.entered
            ):

                token = (
                    strategy.position_token
                )

                current_price = (
                    poly.midpoint(
                        token
                    )
                )

                if (
                    strategy.position_direction
                    == "Up"
                ):

                    opposite_token = (
                        market.down_token
                    )

                else:

                    opposite_token = (
                        market.up_token
                    )

                try:

                    opposite_price = (
                        poly.best_ask(
                            opposite_token
                        )
                    )

                except Exception:

                    opposite_price = None

                hedge_shares = (
                    strategy.maybe_partial_hedge(
                        decision.move,
                        current_price,
                        remaining,
                        opposite_token,
                        opposite_price,
                    )
                )

                if hedge_shares:

                    hedge_usdc = (
                        hedge_shares
                        * opposite_price
                    )

                    # -------------------------------------------------
                    # BUY OPPOSITE TOKEN
                    # -------------------------------------------------

                    response = poly.buy(
                        opposite_token,
                        hedge_usdc,
                    )

                    logging.info(
                        BLUE
                        + BOLD
                        + UNDERLINE
                        + "LIVE | Hedge | "
                        "Round: %s | "
                        "Main: %s | "
                        "Main price: %.4f | "
                        "Opposite price: %.4f | "
                        "Shares: %.4f | "
                        "Value: $%.2f"
                        + RESET,

                        strategy.round_id,

                        strategy.position_direction,

                        current_price,

                        opposite_price,

                        hedge_shares,

                        hedge_usdc,
                    )

                    logging.info(
                        "Live | Hedge response: %s",
                        response,
                    )

                # =================================================
                # EXIT NEAR 1.00
                # =================================================

                if current_price >= 0.99:

                    exit_direction = (
                        strategy.position_direction
                    )

                    exit_shares = (
                        strategy.position_shares
                    )

                    response = poly.sell(
                        strategy.position_token,
                        exit_shares,
                    )

                    exit_result = (
                        strategy.record_exit(
                            decision.move,
                            current_price,
                            "contract reached >= 0.99",
                        )
                    )

                    if exit_result:

                        (
                            result,
                            result_usd,
                            _,
                            _,
                        ) = exit_result

                        exit_color = (
                            GREEN
                            + BOLD
                            + UNDERLINE
                            if result_usd >= 0
                            else RED
                            + BOLD
                            + UNDERLINE
                        )

                        logging.info(
                            exit_color
                            + "LIve | Exit | "
                            "Round: %s | "
                            "Dir: %s | "
                            "Move: %+.2f | "
                            "Price: %.4f | "
                            "Shares: %.4f | "
                            "P&L estimated: %s %+.2f USD | "
                            "Reason: contract >= 0.99"
                            + RESET,

                            strategy.round_id,

                            exit_direction
                            or "-",

                            decision.move,

                            current_price,

                            exit_shares,

                            result,

                            result_usd,
                        )

                        logging.info(
                            "Live | Exit response: %s",
                            response,
                        )

            # =================================================
            # ROUND END
            # =================================================

            elif (
                decision.action == "EXIT"
                and strategy.entered
            ):

                token = (
                    strategy.position_token
                )

                final_price = (
                    poly.best_bid(
                        token
                    )
                )

                exit_direction = (
                    strategy.position_direction
                )

                exit_shares = (
                    strategy.position_shares
                )

                response = poly.sell(
                    token,
                    exit_shares,
                )

                exit_result = (
                    strategy.record_exit(
                        decision.move,
                        final_price,
                        "round ended",
                    )
                )

                if exit_result:

                    (
                        result,
                        result_usd,
                        _,
                        _,
                    ) = exit_result

                    exit_color = (
                        GREEN
                        + BOLD
                        + UNDERLINE
                        if result_usd >= 0
                        else RED
                        + BOLD
                        + UNDERLINE
                    )

                    logging.info(
                        exit_color
                        + "Live | Exit | "
                        "Round: %s | "
                        "Dir: %s | "
                        "Move: %+.2f | "
                        "Price: %.4f | "
                        "Shares: %.4f | "
                        "P&L estimated: %s %+.2f USD | "
                        "Reason: round ended"
                        + RESET,

                        strategy.round_id,

                        exit_direction
                        or "-",

                        decision.move,

                        final_price,

                        exit_shares,

                        result,

                        result_usd,
                    )

                    logging.info(
                        "Live | Exit response: %s",
                        response,
                    )

        except Exception as exc:

            logging.exception(
                "Live | Loop error: %s",
                exc,
            )

        await asyncio.sleep(
            cfg.poll_seconds
        )


if __name__ == "__main__":
    asyncio.run(main())
