#!/usr/bin/env python3

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path


sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(__file__)),
)


from src.config import Config
from src.binance_feed import BinanceFeed
from src.polymarket import Polymarket
from src.strategy import Strategy
from src.log_manager import archive_log_file, TRADE_HEADER


# =============================================================
# PATHS
# =============================================================

ROOT = Path(__file__).resolve().parents[1]
STOP_FILE = ROOT / ".bot_stop"

LOG_DIR = ROOT / "logs" / "live"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "live.log"

TRADES_DIR = ROOT / "trades" / "live"
TRADES_DIR.mkdir(parents=True, exist_ok=True)
TRADES_FILE = TRADES_DIR / "live_trades.log"


# =============================================================
# FORMATTER
# =============================================================

formatter = logging.Formatter(
    "%(asctime)s | %(message)s"
)


# =============================================================
# NORMAL LOG
# =============================================================

file_handler = logging.FileHandler(
    LOG_FILE,
    encoding="utf-8",
)

file_handler.setFormatter(formatter)


# =============================================================
# TRADES LOG
#
# Siempre guarda:
# - New 5m round
# - Entry
# - Hedge
# - Exit
# =============================================================

class TradeFilter(logging.Filter):

    def filter(self, record):

        message = record.getMessage()

        message_clean = re.sub(
            r"\x1b\[[0-9;]*m",
            "",
            message,
        )

        return (
            "New 5m round" in message_clean
            or "ROUND" in message_clean
            or "(Live) Entry" in message_clean
            or "(Live) Hedge" in message_clean
            or "(Live) Exit" in message_clean
            or "(LIVE) Entry" in message_clean
            or "(LIVE) Hedge" in message_clean
            or "(LIVE) Exit" in message_clean
        )


trade_handler = logging.FileHandler(
    TRADES_FILE,
    encoding="utf-8",
)

trade_handler.setFormatter(formatter)
trade_handler.addFilter(TradeFilter())


# =============================================================
# CONSOLE
# =============================================================

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)


# =============================================================
# ROOT LOGGER
# =============================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(file_handler)
logger.addHandler(trade_handler)
logger.addHandler(console_handler)


# =============================================================
# COLORS
# =============================================================

BLUE = "\033[34m"
ORANGE = "\033[38;5;208m"
GREEN = "\033[32m"
RED = "\033[31m"
PURPLE = "\033[35m"
PINK = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"


async def main():

    cfg = Config()

    # =========================================================
    # MODE
    # =========================================================
    #
    # Con credenciales completas -> REAL.
    # Sin credenciales -> PAPER FALLBACK.
    #
    # En el segundo caso NUNCA se llama a buy/sell.
    # =========================================================

    real_mode = cfg.live_mode

    starting_balance = cfg.paper_starting_balance
    paper_balance = starting_balance
    entry_size = cfg.trade_usdc

    wins = 0
    losses = 0
    total_pnl = 0.00

    logging.info("")
    logging.info(
        "████████╗██████╗  █████╗ ██████╗ ██╗███╗   ██╗ ██████╗     ██████╗  ██████╗ ████████╗"
    )
    logging.info(
        "╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝     ██╔══██╗██╔═══██╗╚══██╔══╝"
    )
    logging.info(
        "   ██║   ██████╔╝███████║██║  ██║██║██╔██╗ ██║██║  ███╗    ██████╔╝██║   ██║   ██║   "
    )
    logging.info(
        "   ██║   ██╔══██╗██╔══██║██║  ██║██║██║╚██╗██║██║   ██║    ██╔══██╗██║   ██║   ██║   "
    )
    logging.info(
        "   ██║   ██║  ██║██║  ██║██████╔╝██║██║ ╚████║╚██████╔╝    ██████╔╝╚██████╔╝   ██║   "
    )
    logging.info(
        "   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝   "
    )
    logging.info("")
    logging.info(
        "                              by Arkilinux"
    )
    logging.info("")

    if real_mode:

        logging.warning(
            RED
            + BOLD
            + "LIVE MODE - REAL ORDERS ENABLED"
            + RESET
        )

    else:

        logging.warning(
            GREEN
            + BOLD
            + "LIVE MODE - PAPER FALLBACK"
            + RESET
        )

        logging.warning(
            RED
            + BOLD
            + "Operation not performed: Polymarket real credentials are undefined."
            + RESET
        )

        logging.info(
            "Live will use the same strategy and paper execution until real credentials are configured."
        )

    logging.info(
        BOLD
        + "Entry size: $%.2f"
        + RESET,
        entry_size,
    )

    # =========================================================
    # CONNECTIONS
    # =========================================================

    poly = Polymarket(cfg)

    feed = BinanceFeed(
        cfg.binance_ws_url
    )

    strategy = Strategy(
        cfg,
        paper=not real_mode,
    )

    feed_task = asyncio.create_task(
        feed.run()
    )

    # =========================================================
    # POLYMARKET CONNECTION
    # =========================================================

    try:

        market = poly.get_market()

        logging.info(
            ORANGE
            + "POLYMARKET connected | Market: %s"
            + RESET,
            market.slug,
        )

    except Exception as exc:

        logging.error(
            RED
            + "POLYMARKET connection error: %s"
            + RESET,
            exc,
        )

        feed.stop()

        if not feed_task.done():
            feed_task.cancel()

        return

    # =========================================================
    # REAL ACCOUNT
    # =========================================================

    if real_mode:

        try:

            poly.check_auth()

            account_address = (
                poly.account_address()
            )

            live_balance = (
                poly.get_balance()
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

        except Exception as exc:

            logging.error(
                RED
                + BOLD
                + "LIVE credentials/account check failed: %s"
                + RESET,
                exc,
            )

            logging.warning(
                GREEN
                + "Switching to PAPER FALLBACK. No real operation will be performed."
                + RESET
            )

            real_mode = False
            strategy = Strategy(
                cfg,
                paper=True,
            )

    last_log = 0
    pre_entry_wait_round = None
    next_pre_entry_wait_log = None

    # Last known position price used as an emergency reference.
    last_known_position_price = None
    last_round_logged = None
    completed_rounds = 0

    # =========================================================
    # MAIN LOOP
    # =========================================================

    try:

        while True:

            # Cross-platform graceful stop requested by the web UI.
            if STOP_FILE.exists():
                logging.info("Stop requested by web interface")
                break

            if feed.state.price is None:

                await asyncio.sleep(0.5)
                continue

            now = time.time()

            # =====================================================
            # CURRENT ROUND
            # =====================================================

            current_round_id = (
                int(
                    now
                    // cfg.round_seconds
                )
                * cfg.round_seconds
            )

            elapsed = (
                now
                - current_round_id
            )

            remaining = (
                cfg.round_seconds
                - elapsed
            )

            # =====================================================
            # NEW ROUND
            # =====================================================

            if current_round_id != last_round_logged:

                # The previous round is now complete. Archive its
                # trade events every round, and the normal logs every
                # six completed rounds (30 minutes).
                if last_round_logged is not None:

                    completed_rounds += 1

                    archive_log_file(
                        TRADES_FILE,
                        header=TRADE_HEADER,
                    )

                    if completed_rounds % 6 == 0:

                        archive_log_file(
                            LOG_FILE,
                            clear=False,
                        )

                logging.info(
                    BOLD
                    + "New 5m round %s started | BTC: $%.2f"
                    + RESET,
                    current_round_id,
                    feed.state.price,
                )

                last_round_logged = current_round_id

            # =====================================================
            # CLOSED ROUND
            # =====================================================

            if (
                strategy.round_id
                == current_round_id
                and strategy.round_finished
            ):

                if now - last_log >= 2:

                    logging.info(
                        "%.0fs | "
                        "BTC: $%+.2f | "
                        "Action: WAIT next round",
                        remaining,
                        feed.state.price
                        - strategy.round_start_price,
                    )

                    last_log = now

                await asyncio.sleep(
                    cfg.poll_seconds
                )
                continue

            # =====================================================
            # PUBLIC MARKET
            # =====================================================

            try:

                market = poly.get_market()

            except Exception as exc:

                logging.warning(
                    RED
                    + "(Live) Polymarket error: %s"
                    + RESET,
                    exc,
                )

                await asyncio.sleep(
                    cfg.poll_seconds
                )
                continue

            try:

                decision = strategy.evaluate(
                    now,
                    feed.state.price,
                    market,
                    poly,
                )

                # =================================================
                # NORMAL STATUS LOG
                # =================================================

                should_log_status = False

                # Before the entry window, log once at the first observed
                # value and then at 20-second marks.
                if remaining > cfg.entry_window_seconds:

                    if pre_entry_wait_round != current_round_id:
                        pre_entry_wait_round = current_round_id
                        next_pre_entry_wait_log = (
                            int(remaining // 20) * 20
                        )
                        should_log_status = True

                    elif (
                        next_pre_entry_wait_log is not None
                        and remaining <= next_pre_entry_wait_log
                    ):
                        should_log_status = True
                        next_pre_entry_wait_log -= 20

                else:
                    # Keep the existing 2-second cadence inside the
                    # entry window.
                    should_log_status = now - last_log >= 2

                if should_log_status:

                    log_price = decision.contract_price

                    if strategy.entered:

                        token_for_log = strategy.position_token

                        try:

                            log_price = poly.midpoint(
                                token_for_log
                            )

                        except Exception:

                            log_price = decision.contract_price

                    logging.info(
                        "%.0fs | "
                        "BTC: $%+.2f | "
                        "Action: %s %s | "
                        "Contract: %s %s",
                        remaining,
                        decision.move,
                        decision.action,
                        decision.reason,
                        (
                            f"{log_price:.2f}"
                            if log_price is not None
                            else "None"
                        ),
                        (
                            strategy.position_direction
                            if strategy.entered
                            else decision.direction
                        ),
                    )

                    last_log = now

                # =================================================
                # ENTRY
                # =================================================

                if decision.action == "ENTER":

                    price = decision.contract_price

                    if price is None or price <= 0:

                        logging.warning(
                            "(Live) Invalid entry price | Operation not performed"
                        )

                    elif strategy.entered:

                        pass

                    elif real_mode:

                        try:

                            live_balance = poly.get_balance()

                            if live_balance < entry_size:

                                logging.warning(
                                    RED
                                    + BOLD
                                    + "(Live) Entry skipped | Balance $%.2f < entry $%.2f | Operation not performed"
                                    + RESET,
                                    live_balance,
                                    entry_size,
                                )

                                await asyncio.sleep(cfg.poll_seconds)
                                continue

                            response = poly.buy(
                                strategy.position_token,
                                entry_size,
                            )

                            shares = entry_size / price

                            strategy.record_entry(
                                decision.move,
                                price,
                                entry_size,
                                shares,
                            )

                            last_known_position_price = price

                            logging.info(
                                ORANGE
                                + BOLD
                                + UNDERLINE
                                + "(Live) Entry %s $%+.2f | "
                                "Range: %.2f | "
                                "Stake: $%.2f | "
                                "Shares: %.2f"
                                + RESET,
                                decision.direction or "?",
                                decision.move,
                                price,
                                entry_size,
                                shares,
                            )

                            logging.info(
                                "(Live) Entry response: %s",
                                response,
                            )

                        except Exception as exc:

                            logging.error(
                                RED
                                + BOLD
                                + "(Live) Entry operation failed | Operation not performed correctly: %s"
                                + RESET,
                                exc,
                            )

                    else:

                        shares = entry_size / price

                        strategy.record_entry(
                            decision.move,
                            price,
                            entry_size,
                            shares,
                        )

                        last_known_position_price = price

                        logging.info(
                            ORANGE
                            + BOLD
                            + "(Live/Paper fallback) Entry %s $%+.2f | "
                            "Range: %.2f | "
                            "Stake: $%.2f | "
                            "Balance: $%.2f | "
                            "Shares: %.2f"
                            + RESET,
                            decision.direction or "?",
                            decision.move,
                            price,
                            entry_size,
                            paper_balance,
                            shares,
                        )

                # =================================================
                # HOLD / HEDGE / EXIT
                # =================================================

                elif (
                    decision.action == "HOLD"
                    and strategy.entered
                ):

                    token = strategy.position_token

                    try:

                        current_price = poly.midpoint(token)

                    except Exception:

                        current_price = None

                    if current_price is not None:

                        last_known_position_price = current_price

                        # =================================================
                        # EARLY EXIT >= 0.99
                        # =================================================

                        if current_price >= 0.99:

                            exit_direction = strategy.position_direction
                            exit_shares = strategy.position_shares

                            if real_mode:

                                try:

                                    response = poly.sell(
                                        token,
                                        exit_shares,
                                    )

                                except Exception as exc:

                                    logging.error(
                                        RED
                                        + BOLD
                                        + "(Live) Exit operation failed | Operation not performed correctly: %s"
                                        + RESET,
                                        exc,
                                    )

                                    response = None

                                if response is None:
                                    await asyncio.sleep(cfg.poll_seconds)
                                    continue

                            exit_result = strategy.record_exit(
                                decision.move,
                                current_price,
                                "contract >= 0.99",
                            )

                            if exit_result:

                                result, result_usd, _, _ = exit_result

                                total_pnl += result_usd

                                if result == "WIN":
                                    wins += 1
                                else:
                                    losses += 1

                                if not real_mode:
                                    paper_balance += result_usd

                                exit_color = (
                                    GREEN + BOLD
                                    if result_usd >= 0
                                    else RED + BOLD
                                )

                                balance_text = (
                                    f"Balance: ${paper_balance:.2f} | "
                                    if not real_mode
                                    else ""
                                )

                                logging.info(
                                    exit_color
                                    + "(Live) Exit %s $%+.2f (%.2f shares) | "
                                    "P&L: %s $%+.2f | "
                                    + balance_text
                                    + "Reason: contract >= 0.99"
                                    + RESET,
                                    exit_direction or "-",
                                    decision.move,
                                    exit_shares,
                                    result,
                                    result_usd,
                                )

                                if real_mode:
                                    logging.info(
                                        "(Live) Exit response: %s",
                                        response,
                                    )

                        else:

                            # =================================================
                            # PARTIAL HEDGE
                            # =================================================

                            if strategy.position_direction == "Up":
                                opposite_token = market.down_token
                            else:
                                opposite_token = market.up_token

                            try:
                                opposite_price = poly.best_ask(opposite_token)
                            except Exception:
                                opposite_price = None

                            hedge_shares = strategy.maybe_partial_hedge(
                                decision.move,
                                current_price,
                                remaining,
                                opposite_token,
                                opposite_price,
                            )

                            if hedge_shares:

                                hedge_usdc = hedge_shares * opposite_price

                                if real_mode:

                                    try:

                                        response = poly.buy(
                                            opposite_token,
                                            hedge_usdc,
                                        )

                                    except Exception as exc:

                                        logging.error(
                                            RED
                                            + BOLD
                                            + "(Live) Hedge operation failed | Operation not performed correctly: %s"
                                            + RESET,
                                            exc,
                                        )

                                        # The strategy already marked the hedge.
                                        # Keep the process alive and report the failure.
                                        response = None

                                    if response is not None:

                                        logging.info(
                                            BLUE
                                            + BOLD
                                            + "(Live) Hedge %s | "
                                            "Main price: %.2f | "
                                            "Opposite: %s | "
                                            "Opposite price: %.2f | "
                                            "Shares: %.2f"
                                            + RESET,
                                            strategy.position_direction,
                                            current_price,
                                            (
                                                "Down"
                                                if strategy.position_direction == "Up"
                                                else "Up"
                                            ),
                                            opposite_price,
                                            hedge_shares,
                                        )

                                        logging.info(
                                            "(Live) Hedge response: %s",
                                            response,
                                        )

                                else:

                                    logging.info(
                                        BLUE
                                        + BOLD
                                        + "(Live/Paper fallback) Hedge %s | "
                                        "Main price: %.2f | "
                                        "Opposite: %s | "
                                        "Opposite price: %.2f | "
                                        "Shares: %.2f"
                                        + RESET,
                                        strategy.position_direction,
                                        current_price,
                                        (
                                            "Down"
                                            if strategy.position_direction == "Up"
                                            else "Up"
                                        ),
                                        opposite_price,
                                        hedge_shares,
                                    )

                # =================================================
                # SAFETY EXIT / ROUND END
                #
                # A missing public bid must not leave the position
                # open indefinitely. In PAPER/fallback mode we close
                # against the last known price. In REAL mode the real
                # sell order must still succeed.
                # =================================================

                elif (
                    decision.action == "EXIT"
                    and strategy.entered
                ):

                    token = strategy.position_token
                    exit_direction = strategy.position_direction
                    exit_shares = strategy.position_shares

                    try:
                        final_price = poly.best_bid(token)
                        used_fallback_price = False

                    except Exception as exc:

                        logging.warning(
                            "(Live) Exit bid unavailable: %s",
                            exc,
                        )

                        final_price = last_known_position_price
                        used_fallback_price = True

                    if final_price is None or final_price <= 0:
                        final_price = strategy.entry_price
                        used_fallback_price = True

                    if final_price is not None and final_price > 0:

                        if real_mode:

                            try:
                                response = poly.sell(
                                    token,
                                    exit_shares,
                                )

                            except Exception as exc:

                                logging.error(
                                    RED
                                    + BOLD
                                    + "(Live) Exit operation failed | "
                                    "Operation not performed correctly: %s"
                                    + RESET,
                                    exc,
                                )

                                response = None

                            if response is None:
                                await asyncio.sleep(cfg.poll_seconds)
                                continue

                        exit_result = strategy.record_exit(
                            decision.move,
                            final_price,
                            decision.reason,
                        )

                        if exit_result:

                            result, result_usd, _, _ = exit_result

                            total_pnl += result_usd
                            if result == "WIN":
                                wins += 1
                            else:
                                losses += 1

                            if not real_mode:
                                paper_balance += result_usd

                            if used_fallback_price:
                                exit_color = (
                                    PURPLE + BOLD
                                    if result_usd >= 0
                                    else PINK + BOLD
                                )
                                reason_text = (
                                    "safety exit - last known price "
                                    f"({decision.reason})"
                                )
                            else:
                                exit_color = (
                                    GREEN + BOLD
                                    if result_usd >= 0
                                    else RED + BOLD
                                )
                                reason_text = decision.reason

                            balance_text = (
                                f"Balance: ${paper_balance:.2f} | "
                                if not real_mode
                                else ""
                            )

                            logging.info(
                                exit_color
                                + "(Live) Exit %s $%+.2f (%.2f shares) | "
                                "P&L: %s $%+.2f | "
                                + balance_text
                                + "Reason: %s"
                                + RESET,
                                exit_direction or "-",
                                decision.move,
                                exit_shares,
                                result,
                                result_usd,
                                reason_text,
                            )

                            if real_mode:
                                logging.info(
                                    "(Live) Exit response: %s",
                                    response,
                                )

                            last_known_position_price = None


            except Exception as exc:

                logging.warning(
                    "(Live) Loop error: %s",
                    exc,
                )

            await asyncio.sleep(
                cfg.poll_seconds
            )

    finally:

        feed.stop()

        if not feed_task.done():
            feed_task.cancel()

        try:
            await feed_task
        except asyncio.CancelledError:
            pass

        logging.info("")

        if real_mode:

            logging.info(
                BOLD
                + UNDERLINE
                + "LIVE TRADING SUMMARY"
                + RESET
            )

            try:
                final_balance = poly.get_balance()
                logging.info(
                    "Final account balance: $%.2f",
                    final_balance,
                )
            except Exception:
                logging.info(
                    "Final account balance: unavailable"
                )

        else:

            logging.info(
                BOLD
                + UNDERLINE
                + "LIVE PAPER FALLBACK SUMMARY"
                + RESET
            )

            logging.info(
                "Starting balance: $%.2f",
                starting_balance,
            )

            logging.info(
                "Final balance: $%.2f",
                paper_balance,
            )

        logging.info(
            "Wins: %d",
            wins,
        )

        logging.info(
            "Losses: %d",
            losses,
        )

        logging.info(
            "Total trades: %d",
            wins + losses,
        )

        logging.info(
            "P&L: %+.2f USD",
            total_pnl,
        )

        logging.info("")
        logging.info(
            ITALIC
            + "Logs saved!"
            + RESET
        )

        # Archive the incomplete final round when the bot stops.
        archive_log_file(LOG_FILE, clear=False)
        archive_log_file(
            TRADES_FILE,
            clear=False,
            header=TRADE_HEADER,
        )


if __name__ == "__main__":

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLive trading stopped by user")
