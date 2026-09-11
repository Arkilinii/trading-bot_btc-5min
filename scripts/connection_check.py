#!/usr/bin/env python3

import asyncio
import os
import sys


sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(__file__)
    ),
)


from src.binance_feed import BinanceFeed
from src.config import Config
from src.polymarket import Polymarket


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"
RESET = "\033[0m"


async def check_binance(cfg):

    print(f"\n{UNDERLINE}BINANCE CONNECTION{RESET}")
    print(f"WebSocket: {cfg.binance_ws_url}")

    feed = BinanceFeed(cfg.binance_ws_url)
    task = asyncio.create_task(feed.run())

    try:
        for _ in range(10):
            await asyncio.sleep(1)
            if feed.state.price is not None:
                print(f"{GREEN}OK{RESET} | WebSocket connected")
                print(f"{GREEN}OK{RESET} | BTC-USDT: ${feed.state.price:,.2f}")
                print(f"{GREEN}OK{RESET} | Event time: {feed.state.event_time_ms}")
                return True

        print(f"{RED}FAIL{RESET} | Binance did not provide a price within 10 seconds")
        return False

    finally:
        feed.stop()
        try:
            await asyncio.wait_for(task, timeout=3)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass



def check_polymarket(cfg):
    print(f"\n{UNDERLINE}POLYMARKET CONNECTION{RESET}")
    print(f"Gamma API: {cfg.poly_gamma_url}")
    print(f"CLOB API:  {cfg.poly_clob_url}")

    poly = Polymarket(cfg)

    try:
        # ---------------------------------------------------------
        # Gamma market discovery
        # ---------------------------------------------------------
        slug = poly.current_slug()
        print(f"Current market: {slug}")

        market = poly.get_market(slug)

        print(f"{GREEN}OK{RESET} | Gamma market request")
        print(f"Question:  {market.question}")
        print(f"Condition: {market.condition_id}")
        print(f"Up token:  {market.up_token}")
        print(f"Down token:{market.down_token}")

        # ---------------------------------------------------------
        # Public CLOB endpoints
        # ---------------------------------------------------------
        up_mid = poly.midpoint(market.up_token)
        down_mid = poly.midpoint(market.down_token)

        print(f"{GREEN}OK{RESET} | CLOB midpoint endpoint | Up midpoint: {up_mid:.4f} | Down midpoint: {down_mid:.4f}")

        # Order books are tested directly.  A market can legitimately
        # have no asks/bids, so an empty book is reported separately.
        up_book = poly.get_order_book_public(market.up_token)
        down_book = poly.get_order_book_public(market.down_token)

        if isinstance(up_book, dict) and isinstance(down_book, dict):
            print(f"{GREEN}OK{RESET} | CLOB order book endpoint | Up book:   bids={len(up_book.get('bids', []))}, asks={len(up_book.get('asks', []))} | Down book: bids={len(down_book.get('bids', []))}, asks={len(down_book.get('asks', []))}")

        else:
            raise RuntimeError("Invalid order book response")

        # ---------------------------------------------------------
        # Private CLOB endpoints, only when credentials are complete
        # ---------------------------------------------------------
        if not cfg.live_mode:
            print(f"{YELLOW}INFO{RESET} | No complete credentials detected")
            print(f"{YELLOW}INFO{RESET} | Private CLOB authentication/balance check skipped")
            print(f"{GREEN}OK{RESET} | Polymarket public connection works in PAPER FALLBACK")
            return True

        print("\nAuthenticated CLOB check:")
        print(f"Account address: {poly.account_address()}")

        poly.check_auth()
        print(f"{GREEN}OK{RESET} | L2 credential configuration")

        balance = poly.get_balance()
        print(f"{GREEN}OK{RESET} | Authenticated CLOB balance request")
        print(f"Collateral balance: ${balance:.2f}")
        print(f"Entry size:         ${cfg.trade_usdc:.2f}")

        if balance < cfg.trade_usdc:
            print(
                f"{YELLOW}WARNING{RESET} | Balance is below configured entry size"
            )
        else:
            print(f"{GREEN}OK{RESET} | Balance covers configured entry size")

        return True

    except Exception as exc:
        print(f"{RED}FAIL{RESET} | Polymarket request failed: {exc}")
        return False



async def main():
    cfg = Config()

    print(f"Mode: {'LIVE' if cfg.live_mode else 'PAPER FALLBACK'}")

    binance_ok = await check_binance(cfg)
    polymarket_ok = check_polymarket(cfg)

    print(f"\n{BOLD}CONNECTION TEST RESULT{RESET}")
    print(
        f"Binance:    {GREEN}OK{RESET}"
        if binance_ok
        else f"Binance:    {RED}FAIL{RESET}"
    )
    print(
        f"Polymarket: {GREEN}OK{RESET}"
        if polymarket_ok
        else f"Polymarket: {RED}FAIL{RESET}"
    )

    if binance_ok and polymarket_ok:
        print(f"{GREEN}CONNECTION CHECK OK{RESET}")
        print("\nNo orders were created or sent.\n")
        return 0

    print(f"\n{RED}{BOLD}CONNECTION CHECK FAILED{RESET}")
    print("\nDo not start the bot until the failed connection is fixed.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
