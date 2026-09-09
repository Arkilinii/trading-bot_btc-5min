import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from py_clob_client_v2 import (
    ApiCreds,
    AssetType,
    BalanceAllowanceParams,
    ClobClient,
    MarketOrderArgs,
    OrderType,
    PartialCreateOrderOptions,
    Side,
)


log = logging.getLogger(__name__)


@dataclass
class Market:
    slug: str
    question: str
    condition_id: str
    end_date: str
    up_token: str
    down_token: str


class Polymarket:

    def __init__(self, cfg):

        self.cfg = cfg
        self.session = requests.Session()
        self.client = None

        # ---------------------------------------------------------
        # PRIVATE CLOB CLIENT
        # ---------------------------------------------------------

        if cfg.poly_private_key:

            creds = None

            if (
                cfg.poly_api_key
                and cfg.poly_api_secret
                and cfg.poly_api_passphrase
            ):

                creds = ApiCreds(
                    api_key=cfg.poly_api_key,
                    api_secret=cfg.poly_api_secret,
                    api_passphrase=cfg.poly_api_passphrase,
                )

            kwargs = dict(
                host=cfg.poly_clob_url,
                chain_id=cfg.poly_chain_id,
                key=cfg.poly_private_key,
                creds=creds,
            )

            if cfg.poly_funder:
                kwargs["funder"] = cfg.poly_funder

            kwargs["signature_type"] = (
                cfg.poly_signature_type
            )

            self.client = ClobClient(
                **kwargs
            )

    # =============================================================
    # ACCOUNT
    # =============================================================

    def account_address(self):

        if self.cfg.poly_funder:
            return self.cfg.poly_funder

        if self.client is not None:

            try:
                signer = getattr(
                    self.client,
                    "signer",
                    None,
                )

                address = getattr(
                    signer,
                    "address",
                    None,
                )

                if address:
                    return address

            except Exception:
                pass

        return "-"

    def get_balance(self):

        if not self.client:
            raise RuntimeError(
                "Private CLOB client is not configured"
            )

        response = self.client.get_balance_allowance(
            BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL
            )
        )

        if not isinstance(response, dict):
            raise RuntimeError(
                f"Invalid balance response: {response}"
            )

        raw_balance = response.get(
            "balance"
        )

        if raw_balance is None:
            raise RuntimeError(
                f"Balance missing in response: {response}"
            )

        balance = float(
            raw_balance
        )

        # ---------------------------------------------------------
        # USDC/pUSD uses 6 decimal places.
        #
        # The API may return the raw integer amount.
        # ---------------------------------------------------------

        if balance > 10000:
            balance /= 1_000_000

        return balance

    # =============================================================
    # MARKET DISCOVERY
    # =============================================================

    @staticmethod
    def round_start_epoch(
        now=None,
        seconds=300,
    ):

        now = (
            now
            or datetime.now(
                timezone.utc
            ).timestamp()
        )

        return int(
            now // seconds * seconds
        )

    def current_slug(self):

        return (
            f"btc-updown-5m-"
            f"{self.round_start_epoch()}"
        )

    def get_market(
        self,
        slug=None,
    ):

        slug = (
            slug
            or self.current_slug()
        )

        url = (
            f"{self.cfg.poly_gamma_url}"
            f"/markets/slug/{slug}"
        )

        r = self.session.get(
            url,
            timeout=10,
        )

        r.raise_for_status()

        data = r.json()

        outcomes = data.get(
            "outcomes",
            [],
        )

        tokens = (
            data.get("clobTokenIds")
            or data.get(
                "clob_token_ids"
            )
            or []
        )

        if isinstance(
            outcomes,
            str,
        ):

            outcomes = json.loads(
                outcomes
            )

        if isinstance(
            tokens,
            str,
        ):

            tokens = json.loads(
                tokens
            )

        mapping = {
            str(o).lower(): str(t)
            for o, t in zip(
                outcomes,
                tokens,
            )
        }

        if (
            "up" not in mapping
            or "down" not in mapping
        ):

            raise RuntimeError(
                "Could not map Up/Down "
                "token IDs. "
                f"outcomes={outcomes} "
                f"tokens={tokens}"
            )

        return Market(
            slug=slug,
            question=data.get(
                "question",
                slug,
            ),
            condition_id=data.get(
                "conditionId",
                "",
            ),
            end_date=data.get(
                "endDate",
                "",
            ),
            up_token=mapping["up"],
            down_token=mapping["down"],
        )

    # =============================================================
    # PUBLIC CLOB DATA
    # =============================================================

    def _public_get(
        self,
        endpoint,
        params,
    ):

        url = (
            f"{self.cfg.poly_clob_url.rstrip('/')}"
            f"/{endpoint.lstrip('/')}"
        )

        r = self.session.get(
            url,
            params=params,
            timeout=10,
        )

        r.raise_for_status()

        return r.json()

    @staticmethod
    def _extract_price(level):

        if isinstance(
            level,
            dict,
        ):

            price = level.get(
                "price"
            )

        else:

            price = getattr(
                level,
                "price",
                None,
            )

        if price is None:

            raise RuntimeError(
                f"Invalid order book level: "
                f"{level}"
            )

        return float(price)

    def get_order_book_public(
        self,
        token_id,
    ):

        return self._public_get(
            "/book",
            {
                "token_id": str(
                    token_id
                )
            },
        )

    def midpoint(
        self,
        token_id,
    ):

        data = self._public_get(
            "/midpoint",
            {
                "token_id": str(
                    token_id
                )
            },
        )

        if isinstance(
            data,
            dict,
        ):

            value = data.get(
                "mid"
            )

            if value is None:

                value = data.get(
                    "midpoint"
                )

        else:

            value = data

        if value is None:

            raise RuntimeError(
                f"Invalid midpoint "
                f"response: {data}"
            )

        return float(value)

    def best_ask(
        self,
        token_id,
    ):

        book = (
            self.get_order_book_public(
                token_id
            )
        )

        asks = book.get(
            "asks",
            [],
        )

        if not asks:

            raise RuntimeError(
                "No asks in public "
                "order book for token "
                f"{token_id}"
            )

        asks = sorted(
            asks,
            key=self._extract_price,
        )

        return self._extract_price(
            asks[0]
        )

    def best_bid(
        self,
        token_id,
    ):

        book = (
            self.get_order_book_public(
                token_id
            )
        )

        bids = book.get(
            "bids",
            [],
        )

        if not bids:

            raise RuntimeError(
                "No bids in public "
                "order book for token "
                f"{token_id}"
            )

        bids = sorted(
            bids,
            key=self._extract_price,
            reverse=True,
        )

        return self._extract_price(
            bids[0]
        )

    # =============================================================
    # LIVE ORDERS
    # =============================================================

    def buy(
        self,
        token_id: str,
        usdc: float,
    ):

        if not self.client:

            raise RuntimeError(
                "Polymarket private "
                "client is not configured"
            )

        return (
            self.client
            .create_and_post_market_order(
                order_args=MarketOrderArgs(
                    token_id=token_id,
                    amount=usdc,
                    side=Side.BUY,
                    order_type=OrderType.FOK,
                ),
                options=PartialCreateOrderOptions(
                    tick_size="0.01"
                ),
                order_type=OrderType.FOK,
            )
        )

    def sell(
        self,
        token_id: str,
        shares: float,
    ):

        if not self.client:

            raise RuntimeError(
                "Polymarket private "
                "client is not configured"
            )

        return (
            self.client
            .create_and_post_market_order(
                order_args=MarketOrderArgs(
                    token_id=token_id,
                    amount=shares,
                    side=Side.SELL,
                    order_type=OrderType.FOK,
                ),
                options=PartialCreateOrderOptions(
                    tick_size="0.01"
                ),
                order_type=OrderType.FOK,
            )
        )

    # =============================================================
    # AUTH
    # =============================================================

    def check_auth(self):

        if not self.client:

            raise RuntimeError(
                "Missing POLY_PRIVATE_KEY"
            )

        if not (
            self.cfg.poly_api_key
            and self.cfg.poly_api_secret
            and self.cfg.poly_api_passphrase
        ):

            raise RuntimeError(
                "Missing L2 CLOB credentials"
            )

        return True
