#!/usr/bin/env python3

import os
import sys


sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(__file__)
    ),
)


from src.config import Config
from src.polymarket import Polymarket


def main():

    cfg = Config()

    print(
        "=== Polymarket BTC 5m connection test ==="
    )

    print(
        f"Mode: "
        f"{'LIVE' if cfg.live_mode else 'PAPER'}"
    )

    poly = Polymarket(cfg)

    # =========================================================
    # MARKET
    # =========================================================

    slug = poly.current_slug()

    print(
        f"Current market slug: {slug}"
    )

    market = poly.get_market(
        slug
    )

    print(
        f"Question: {market.question}"
    )

    print(
        f"Up token:   {market.up_token}"
    )

    print(
        f"Down token: {market.down_token}"
    )

    print(
        f"End date:   {market.end_date}"
    )

    # =========================================================
    # PUBLIC MARKET DATA
    # =========================================================

    print(
        "Up midpoint:",
        poly.midpoint(
            market.up_token
        ),
    )

    print(
        "Down midpoint:",
        poly.midpoint(
            market.down_token
        ),
    )

    print(
        "Up best ask:",
        poly.best_ask(
            market.up_token
        ),
    )

    print(
        "Down best ask:",
        poly.best_ask(
            market.down_token
        ),
    )

    # =========================================================
    # PAPER
    # =========================================================

    if not cfg.live_mode:

        print(
            "CLOB client: NOT INITIALIZED"
        )

        print(
            "Mode: PAPER"
        )

        print(
            "Virtual balance: "
            f"${cfg.paper_starting_balance:.2f}"
        )

        print(
            "Entry size: "
            f"${cfg.trade_usdc:.2f}"
        )

        return

    # =========================================================
    # LIVE
    # =========================================================

    print(
        "CLOB client: initialized"
    )

    print(
        "Account address:",
        poly.account_address(),
    )

    try:

        poly.check_auth()

        print(
            "Authentication configuration: OK"
        )

        balance = (
            poly.get_balance()
        )

        print(
            f"Live balance: ${balance:.2f}"
        )

        print(
            f"Entry size: ${cfg.trade_usdc:.2f}"
        )

    except Exception as exc:

        print(
            "Authenticated CLOB test failed:",
            exc,
        )

        raise


if __name__ == "__main__":
    main()
