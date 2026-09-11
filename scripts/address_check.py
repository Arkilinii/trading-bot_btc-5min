#!/usr/bin/env python3

import os
import sys


sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(__file__)
    ),
)


from eth_account import Account

from src.config import Config
from src.polymarket import Polymarket


BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def status(label, ok, detail):

    icon = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"

    print(
        f"{icon} | {label}: {detail}"
    )


def mask(value, visible=6):

    if not value:
        return "-"

    value = str(value)

    if len(value) <= visible * 2:
        return "*" * len(value)

    return (
        value[:visible]
        + "..."
        + value[-visible:]
    )


def normalize_address(value):

    if not value:
        return ""

    return str(value).strip().lower()


def main():

    cfg = Config()

    print(f"\n{BOLD}POLYMARKET ADDRESS CONNECTION{RESET}")

    # =========================================================
    # CONFIGURATION
    # =========================================================
    print(
        f"Chain ID:          {cfg.poly_chain_id}"
    )
    print(
        f"CLOB:              {cfg.poly_clob_url}"
    )
    print(
        f"Signature type:    {cfg.poly_signature_type}"
    )
    print(
        f"Credentials:       {GREEN}COMPLETE{RESET}"
        if cfg.live_mode
        else f"Credentials:       {RED}INCOMPLETE{RESET}"
    )
    print(
        f"Funder configured: "
        f"{'YES' if cfg.poly_funder else 'NO'}"
    )
    print()

    if not cfg.live_mode:

        print(
            f"{YELLOW}PAPER FALLBACK{RESET}: "
            "live credentials are incomplete."
        )
        print(
            "Fill all five POLY_* credential fields in keys/.env "
            "before using this connection test."
        )
        print()
        return 1

    # =========================================================
    # PRIVATE KEY -> SIGNER ADDRESS
    # =========================================================

    print(BOLD + "[ WALLET ]" + RESET)

    try:

        signer_account = Account.from_key(
            cfg.poly_private_key
        )

        signer_address = signer_account.address

        status(
            "Private key",
            True,
            "loaded"
        )

        print(
            f"Signer address:   {signer_address}"
        )

    except Exception as exc:

        status(
            "Private key",
            False,
            str(exc)
        )

        return 1

    # =========================================================
    # FUNDER / ACCOUNT ADDRESS
    # =========================================================

    funder_address = (
        cfg.poly_funder.strip()
        if cfg.poly_funder
        else ""
    )

    print(
        f"Funder address:   {funder_address or '-'}"
    )

    signer_matches_funder = (
        normalize_address(signer_address)
        == normalize_address(funder_address)
    )

    if cfg.poly_signature_type == 0:

        status(
            "Signer / funder match",
            signer_matches_funder,
            "MATCH" if signer_matches_funder else "DOES NOT MATCH"
        )

        if not signer_matches_funder:

            print()
            print(
                f"{RED}STOP:{RESET} signature type 0 uses the "
                "private-key wallet directly."
            )
            print(
                "For signature type 0, POLY_FUNDER should normally "
                "be the same address as the private key."
            )
            print()
            return 1

    else:

        status(
            "Signer / funder relationship",
            bool(funder_address),
            "proxy/funder configured"
            if funder_address
            else "POLY_FUNDER is missing"
        )

        if not funder_address:
            print()
            print(
                f"{RED}STOP:{RESET} POLY_FUNDER is required for "
                f"signature type {cfg.poly_signature_type}."
            )
            print()
            return 1

    # =========================================================
    # CLOB CLIENT
    # =========================================================

    print()
    print(BOLD + "[ CLOB CONNECTION ]" + RESET)

    try:

        poly = Polymarket(cfg)

        if poly.client is None:

            status(
                "CLOB client",
                False,
                "not initialized"
            )

            return 1

        status(
            "CLOB client",
            True,
            "initialized"
        )

        try:

            poly.check_auth()

            status(
                "CLOB authentication",
                True,
                "authenticated"
            )

        except Exception as exc:

            status(
                "CLOB authentication",
                False,
                str(exc)
            )

            return 1

    except Exception as exc:

        status(
            "CLOB connection",
            False,
            str(exc)
        )

        return 1

    # =========================================================
    # ACCOUNT / BALANCE
    # =========================================================

    print()
    print(BOLD + "[ ACCOUNT ]" + RESET)

    account_address = poly.account_address()

    print(
        f"Account address:  {account_address}"
    )

    account_matches_funder = (
        normalize_address(account_address)
        == normalize_address(funder_address)
    )

    status(
        "Account / funder match",
        account_matches_funder,
        "MATCH" if account_matches_funder else "DOES NOT MATCH"
    )

    try:

        balance = poly.get_balance()

        status(
            "USDC balance",
            True,
            f"${balance:.2f}"
        )

    except Exception as exc:

        status(
            "USDC balance",
            False,
            str(exc)
        )

        return 1

    # =========================================================
    # BALANCE ALLOWANCE / TRADING PERMISSION
    # =========================================================

    try:

        allowance_response = poly.client.get_balance_allowance()

        if isinstance(allowance_response, dict):

            allowance = allowance_response.get(
                "allowance"
            )

            balance_raw = allowance_response.get(
                "balance"
            )

            print()
            print(
                BOLD + "[ CLOB ACCOUNT DATA ]" + RESET
            )
            print(
                f"Collateral balance raw: {balance_raw}"
            )
            print(
                f"Allowance raw:          {allowance}"
            )

            status(
                "Balance response",
                balance_raw is not None,
                "received"
                if balance_raw is not None
                else "missing"
            )

            status(
                "Allowance response",
                allowance is not None,
                "received"
                if allowance is not None
                else "missing"
            )

        else:

            status(
                "Balance/allowance response",
                False,
                f"invalid response: {allowance_response}"
            )

            return 1

    except Exception as exc:

        status(
            "Balance/allowance",
            False,
            str(exc)
        )

        return 1

    # =========================================================
    # FINAL PRE-FLIGHT RESULT
    # =========================================================

    print()
    print(
        BOLD
        + "============================================================"
        + RESET
    )

    print(
        f"{GREEN}{BOLD}ADDRESS CONNECTION OK{RESET}"
    )

    print(
        "The configured credentials authenticate successfully "
        "and the account/funder address is consistent."
    )

    print(
        f"Address:  {account_address}"
    )
    print(
        f"Balance:  ${balance:.2f}"
    )
    print(
        f"Chain:    {cfg.poly_chain_id}"
    )
    print(
        f"Sig type: {cfg.poly_signature_type}"
    )

    print(
        BOLD
        + "============================================================"
        + RESET
    )
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
