import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone


log = logging.getLogger(__name__)


BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class Decision:
    action: str
    direction: str | None
    move: float
    contract_price: float | None
    reason: str


class Strategy:

    def __init__(
        self,
        cfg,
        paper=None,
    ):

        self.cfg = cfg

        if paper is None:
            paper = not cfg.live_mode

        self.paper = paper

        self.round_id = None
        self.round_start_price = None

        self.entered = False
        self.hedged = False

        self.position_shares = 0.0
        self.position_token = None
        self.position_direction = None
        self.entry_price = None

        self.hedge_shares = 0.0
        self.hedge_token = None
        self.hedge_price = None

        # True = ya se ha cerrado la operación de esta ronda.
        # Mientras sea True, el paper loop NO debe volver a consultar
        # Polymarket hasta que empiece una nueva ronda.
        self.round_finished = False

        self._ensure_csv()

    # =============================================================
    # TRADE LOG
    # =============================================================

    def _trade_file(self):

        return (
            "data/paper_trades.csv"
            if self.paper
            else "data/live_trades.csv"
        )

    def _ensure_csv(self):

        os.makedirs(
            "data",
            exist_ok=True,
        )

        path = self._trade_file()

        if not os.path.exists(path):

            with open(
                path,
                "w",
                encoding="utf-8",
            ) as f:

                f.write(
                    "TRADE LOG\n"
                )

    def _log_trade(
        self,
        event,
        direction="",
        move="",
        price="",
        shares="",
        usdc="",
        result="",
        result_usd="",
        reason="",
    ):

        os.makedirs(
            "data",
            exist_ok=True,
        )

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        if move != "":

            try:
                move_text = f"{float(move):+.2f}"
            except (TypeError, ValueError):
                move_text = str(move)

        else:
            move_text = "-"

        if price != "":

            try:
                price_text = f"{float(price):.4f}"
            except (TypeError, ValueError):
                price_text = str(price)

        else:
            price_text = "-"

        if shares != "":

            try:
                shares_text = f"{float(shares):.4f}"
            except (TypeError, ValueError):
                shares_text = str(shares)

        else:
            shares_text = "-"

        if usdc != "":

            try:
                usdc_text = f"${float(usdc):.2f}"
            except (TypeError, ValueError):
                usdc_text = str(usdc)

        else:
            usdc_text = "-"

        if result and result_usd != "":

            try:
                pnl_text = (
                    f"{result} "
                    f"{float(result_usd):+.2f} USD"
                )
            except (TypeError, ValueError):
                pnl_text = (
                    f"{result} "
                    f"{result_usd}"
                )

        else:

            pnl_text = "-"

        line = (
            f"timestamp: {timestamp} | "
            f"round: {self.round_id} | "
            f"event: {event} | "
            f"direction: {direction or '-'} | "
            f"move: {move_text} | "
            f"price: {price_text} | "
            f"shares: {shares_text} | "
            f"stake/value: {usdc_text} | "
            f"P&L: {pnl_text} | "
            f"reason: {reason or '-'}"
        )

        with open(
            self._trade_file(),
            "a",
            encoding="utf-8",
        ) as f:

            f.write(line + "\n")

    # =============================================================
    # ROUND RESET
    # =============================================================

    def reset_if_new_round(
        self,
        round_id,
        price,
    ):

        # Ya estamos en esta ronda.
        if self.round_id == round_id:
            return

        self.round_id = round_id
        self.round_start_price = price

        # NUEVA RONDA = desbloqueamos el trading.
        self.round_finished = False

        self.entered = False
        self.hedged = False

        self.position_shares = 0.0
        self.position_token = None
        self.position_direction = None
        self.entry_price = None

        self.hedge_shares = 0.0
        self.hedge_token = None
        self.hedge_price = None

        log.info(
            BOLD
            + "ROUND %s | BTC: $%.2f"
            + RESET,
            round_id,
            price,
        )

    # =============================================================
    # STRATEGY
    # =============================================================

    def evaluate(
        self,
        now_epoch,
        btc_price,
        market,
        polymarket,
    ):

        round_id = (
            int(
                now_epoch
                // self.cfg.round_seconds
            )
            * self.cfg.round_seconds
        )

        self.reset_if_new_round(
            round_id,
            btc_price,
        )

        elapsed = (
            now_epoch - round_id
        )

        remaining = (
            self.cfg.round_seconds
            - elapsed
        )

        move_signed = (
            btc_price
            - self.round_start_price
        )

        move_abs = abs(move_signed)

        # =========================================================
        # SI LA RONDA YA SE CERRÓ, NO HACER NADA MÁS
        # =========================================================

        if self.round_finished:

            return Decision(
                "WAIT",
                None,
                move_signed,
                None,
                "round already finished",
            )

        # =========================================================
        # EXIT DE SEGURIDAD
        # =========================================================
        #
        # Cerramos 18 segundos antes del final si todavía existe
        # una posición abierta.
        #
        # Esto evita que una posición llegue viva al cambio de ronda.
        # =========================================================

        if (
            self.entered
            and remaining <= 18
        ):

            return Decision(
                "EXIT",
                self.position_direction,
                move_signed,
                None,
                "safety exit before round end",
            )

        # =========================================================
        # RONDA TERMINADA
        # =========================================================

        if remaining <= 0:

            if self.entered:

                return Decision(
                    "EXIT",
                    self.position_direction,
                    move_signed,
                    None,
                    "round ended",
                )

            self.round_finished = True

            return Decision(
                "WAIT",
                None,
                move_signed,
                None,
                "round ended",
            )

        # =========================================================
        # FUERA DE ENTRY WINDOW
        # =========================================================

        if (
            remaining
            > self.cfg.entry_window_seconds
        ):

            return Decision(
                "WAIT",
                None,
                move_signed,
                None,
                "outside entry window",
            )

        # =========================================================
        # POSICIÓN ACTIVA
        # =========================================================

        if self.entered:

            return Decision(
                "HOLD",
                self.position_direction,
                move_signed,
                None,
                "position active",
            )

        # =========================================================
        # MOVIMIENTO BTC
        # =========================================================

        if not (
            self.cfg.min_move_usd
            <= move_abs
            <= self.cfg.max_move_usd
        ):

            return Decision(
                "WAIT",
                None,
                move_signed,
                None,
                "BTC move outside configured range",
            )

        direction = (
            "Up"
            if move_signed > 0
            else "Down"
        )

        token = (
            market.up_token
            if direction == "Up"
            else market.down_token
        )

        # =========================================================
        # ORDER BOOK
        # =========================================================

        try:

            ask = polymarket.best_ask(
                token
            )

        except Exception as exc:

            # Un order book sin asks NO debe romper el loop.
            # Simplemente esperamos al siguiente ciclo.
            log.info(
                "Paper | No ask available | "
                "Direction: %s | waiting",
                direction,
            )

            return Decision(
                "WAIT",
                direction,
                move_signed,
                None,
                "no ask in public order book",
            )

        # =========================================================
        # PRECIO CONTRATO
        # =========================================================

        if not (
            self.cfg.min_contract_price
            <= ask
            <= self.cfg.max_contract_price
        ):

            return Decision(
                "WAIT",
                direction,
                move_signed,
                ask,
                "contract ask outside price range",
            )

        # =========================================================
        # PREPARAR POSICIÓN
        # =========================================================

        self.position_token = token
        self.position_direction = direction
        self.entry_price = ask

        return Decision(
            "ENTER",
            direction,
            move_signed,
            ask,
            "all entry conditions met",
        )

    # =============================================================
    # ENTRY
    # =============================================================

    def record_entry(
        self,
        move,
        price,
        usdc,
        shares,
    ):

        self.entered = True
        self.round_finished = False

        self.position_shares = shares
        self.entry_price = price

        self._log_trade(
            (
                "PAPER_ENTRY"
                if self.paper
                else "LIVE_ENTRY"
            ),
            self.position_direction,
            move,
            price,
            shares,
            usdc,
            "",
            "",
            "momentum entry",
        )

    # =============================================================
    # PARTIAL HEDGE
    # =============================================================

    def maybe_partial_hedge(
        self,
        btc_move,
        current_price,
        remaining_seconds,
        opposite_token=None,
        opposite_price=None,
    ):

        if not self.entered:
            return 0.0

        if self.hedged:
            return 0.0

        if remaining_seconds <= 18:
            return 0.0

        if (
            current_price
            < self.cfg.extreme_probability
        ):
            return 0.0

        if opposite_token is None:
            return 0.0

        if opposite_price is None:
            return 0.0

        shares = (
            self.position_shares
            * self.cfg.partial_hedge_pct
        )

        if shares <= 0:
            return 0.0

        self.hedged = True
        self.hedge_shares = shares
        self.hedge_token = opposite_token
        self.hedge_price = opposite_price

        hedge_usdc = (
            shares
            * opposite_price
        )

        self._log_trade(
            (
                "PAPER_HEDGE"
                if self.paper
                else "LIVE_HEDGE"
            ),
            self.position_direction,
            btc_move,
            opposite_price,
            shares,
            hedge_usdc,
            "",
            "",
            "market extreme; bought small opposite position",
        )

        return shares

    # =============================================================
    # EXIT
    # =============================================================

    def record_exit(
        self,
        move,
        price,
        reason,
    ):

        if not self.entered:
            return None

        shares = self.position_shares
        entry_price = self.entry_price
        direction = self.position_direction

        usdc = (
            shares
            * price
        )

        result_usd = (
            price
            - entry_price
        ) * shares

        result = (
            "WIN"
            if result_usd >= 0
            else "LOSS"
        )

        self._log_trade(
            (
                "PAPER_EXIT"
                if self.paper
                else "LIVE_EXIT"
            ),
            direction,
            move,
            price,
            shares,
            usdc,
            result,
            result_usd,
            reason,
        )

        # =========================================================
        # MUY IMPORTANTE:
        # LA RONDA QUEDA BLOQUEADA DESPUÉS DEL EXIT.
        # =========================================================

        self.entered = False
        self.round_finished = True

        self.position_shares = 0.0
        self.position_token = None
        self.position_direction = None
        self.entry_price = None

        self.hedged = False
        self.hedge_shares = 0.0
        self.hedge_token = None
        self.hedge_price = None

        return (
            result,
            result_usd,
            direction,
            shares,
        )