#!/usr/bin/env python3

import asyncio
import logging
import os
import re
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
from src.log_manager import archive_log_file, TRADE_HEADER


# =============================================================
# LOGGING
# =============================================================

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STOP_FILE = ROOT / ".bot_stop"


# =============================================================
# LOGS NORMALES
# =============================================================

LOG_DIR = ROOT / "logs" / "paper"

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_FILE = LOG_DIR / "paper.log"


# =============================================================
# TRADES
# =============================================================

TRADES_DIR = ROOT / "trades" / "paper"

TRADES_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TRADES_FILE = TRADES_DIR / "paper_trades.log"


# =============================================================
# FORMATTER
# =============================================================

formatter = logging.Formatter(
    "%(asctime)s | %(message)s"
)


# =============================================================
# HANDLER LOG NORMAL
#
# Guarda TODOS los logs.
# =============================================================

file_handler = logging.FileHandler(
    LOG_FILE,
    encoding="utf-8",
)

file_handler.setFormatter(formatter)


# =============================================================
# HANDLER TRADES
#
# Solo guarda:
# - ROUND
# - Entry
# - Hedge
# - Exit
# =============================================================

class TradeFilter(logging.Filter):

    def filter(self, record):

        message = record.getMessage()

        # Eliminamos ANSI antes de buscar las palabras.
        message_clean = re.sub(
            r"\x1b\[[0-9;]*m",
            "",
            message,
        )

        return (
            "New 5m round" in message_clean
            or "ROUND" in message_clean
            or "(Paper) Entry" in message_clean
            or "(Paper) Hedge" in message_clean
            or "(Paper) Exit" in message_clean
        )


trade_handler = logging.FileHandler(
    TRADES_FILE,
    encoding="utf-8",
)

trade_handler.setFormatter(formatter)

trade_handler.addFilter(
    TradeFilter()
)


# =============================================================
# CONSOLA
# =============================================================

console_handler = logging.StreamHandler()

console_handler.setFormatter(
    formatter
)


# =============================================================
# ROOT LOGGER
# =============================================================

logger = logging.getLogger()

logger.setLevel(
    logging.INFO
)

logger.handlers.clear()

logger.addHandler(
    file_handler
)

logger.addHandler(
    trade_handler
)

logger.addHandler(
    console_handler
)


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
    # PAPER ACCOUNT
    # =========================================================

    starting_balance = (
        cfg.paper_starting_balance
    )

    paper_balance = (
        starting_balance
    )

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

    logging.warning(
        GREEN
        + BOLD
        + "PAPER MODE - Testing: it is a simulation"
        + RESET
    )

    logging.info(
        BOLD
        + "Starting balance: $%.2f | Stake amount: $%.2f"
        + RESET,
        starting_balance,
        entry_size,
    )

    logging.info(
        BOLD
        + "Address: 0x000"
        + RESET
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
        paper=True,
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

        return

    last_log = 0

    # Last known position price used if the public book has no bids.
    last_known_position_price = None

    # =========================================================
    # ROUND TRACKING
    # =========================================================

    last_round_logged = None
    completed_rounds = 0

    # =========================================================
    # PAPER LOOP
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
            # CALCULAR RONDA ACTUAL
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
            # NUEVA RONDA
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
            # SI LA RONDA YA FUE CERRADA:
            #
            # NO TOCAR POLYMARKET.
            #
            # Esperamos a que cambie la ronda.
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
            # POLYMARKET
            #
            # Solo se consulta cuando:
            # - es una nueva ronda
            # - o todavía no hemos cerrado la ronda
            # =====================================================

            try:

                market = poly.get_market()

            except Exception as exc:

                logging.warning(
                    RED
                    + "(Paper) Polymarket error: %s"
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
                # NORMAL LOG
                # =================================================

                if now - last_log >= 2:

                    log_price = (
                        decision.contract_price
                    )

                    if strategy.entered:

                        token_for_log = (
                            strategy.position_token
                        )

                        try:

                            log_price = (
                                poly.midpoint(
                                    token_for_log
                                )
                            )

                        except Exception:

                            log_price = (
                                decision.contract_price
                            )

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

                    price = (
                        decision.contract_price
                    )

                    if (
                        price is None
                        or price <= 0
                    ):

                        logging.warning(
                            "(Paper) Invalid entry price"
                        )

                    elif paper_balance < entry_size:

                        logging.warning(
                            RED
                            + BOLD
                            + "(Paper) Entry skipped | "
                            "Insufficient balance: $%.2f"
                            + RESET,
                            paper_balance,
                        )

                    elif strategy.entered:

                        pass

                    else:

                        shares = (
                            entry_size
                            / price
                        )

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
                            + "(Paper) Entry %s $%+.2f | "
                            "Range: %.2f | "
                            "Stake: $%.2f | "
                            "Balance: $%.2f | "
                            "Shares: %.2f"
                            + RESET,

                            decision.direction
                            or "?",

                            decision.move,

                            price,

                            entry_size,

                            paper_balance,

                            shares,
                        )

                # =================================================
                # HOLD
                # =================================================

                elif (
                    decision.action == "HOLD"
                    and strategy.entered
                ):

                    token = (
                        strategy.position_token
                    )

                    # -------------------------------------------------
                    # Obtener precio actual de la posición.
                    # -------------------------------------------------

                    try:

                        current_price = (
                            poly.midpoint(
                                token
                            )
                        )

                    except Exception:

                        current_price = None

                    # -------------------------------------------------
                    # Si no hay precio, no intentamos hedge.
                    # -------------------------------------------------

                    if current_price is not None:

                        last_known_position_price = current_price

                        # =================================================
                        # EARLY EXIT >= 0.99
                        # =================================================

                        if current_price >= 0.99:

                            exit_direction = (
                                strategy.position_direction
                            )

                            exit_shares = (
                                strategy.position_shares
                            )

                            exit_result = (
                                strategy.record_exit(
                                    decision.move,
                                    current_price,
                                    "contract >= 0.99",
                                )
                            )

                            if exit_result:

                                (
                                    result,
                                    result_usd,
                                    _,
                                    _,
                                ) = exit_result

                                total_pnl += (
                                    result_usd
                                )

                                paper_balance += (
                                    result_usd
                                )

                                if result == "WIN":

                                    wins += 1

                                else:

                                    losses += 1

                                exit_color = (
                                    GREEN
                                    + BOLD
                                    if result_usd >= 0
                                    else RED
                                    + BOLD
                                )

                                logging.info(
                                    exit_color
                                    + "(Paper) Exit %s $%+.2f (%.2f shares) | "
                                    "P&L: %s $%+.2f | "
                                    "Balance: $%.2f | "
                                    "Reason: contract >= 0.99"
                                    + RESET,

                                    exit_direction
                                    or "-",

                                    decision.move,

                                    exit_shares,

                                    result,

                                    result_usd,

                                    paper_balance,
                                )

                        else:

                            # =================================================
                            # HEDGE
                            # =================================================

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

                                logging.info(
                                    BLUE
                                    + BOLD
                                    + "(Paper) Hedge %s | "
                                    "Main price: %.2f | "
                                    "Opposite: %s | "
                                    "Opposite price: %.2f | "
                                    "Shares: %.2f"
                                    + RESET,

                                    strategy.position_direction,

                                    current_price,

                                    (
                                        "Down"
                                        if strategy.position_direction
                                        == "Up"
                                        else "Up"
                                    ),

                                    opposite_price,

                                    hedge_shares,
                                )

                # =================================================
                # SAFETY EXIT
                #
                # If there is no public bid near round end, use the
                # last known position price in PAPER so the position
                # is still closed and accounted for.
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
                            "(Paper) Exit bid unavailable: %s",
                            exc,
                        )

                        final_price = last_known_position_price
                        used_fallback_price = True

                    if final_price is None or final_price <= 0:
                        final_price = strategy.entry_price
                        used_fallback_price = True

                    if final_price is not None and final_price > 0:

                        exit_result = strategy.record_exit(
                            decision.move,
                            final_price,
                            decision.reason,
                        )

                        if exit_result:

                            (
                                result,
                                result_usd,
                                _,
                                _,
                            ) = exit_result

                            total_pnl += result_usd
                            paper_balance += result_usd

                            if result == "WIN":
                                wins += 1
                            else:
                                losses += 1

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

                            logging.info(
                                exit_color
                                + "(Paper) Exit %s $%+.2f (%.2f shares) | "
                                "P&L: %s $%+.2f | "
                                "Balance: $%.2f | "
                                "Reason: %s"
                                + RESET,
                                exit_direction or "-",
                                decision.move,
                                exit_shares,
                                result,
                                result_usd,
                                paper_balance,
                                reason_text,
                            )

                            last_known_position_price = None


            except Exception as exc:

                logging.warning(
                    "(Paper) Loop error: %s",
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

        logging.info(
            BOLD
            + UNDERLINE
            + "PAPER TRADING SUMMARY"
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

        print(
            "\nPaper trading stopped by user"
        )
