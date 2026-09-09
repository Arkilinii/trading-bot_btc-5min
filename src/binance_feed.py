import asyncio
import json
import logging
import time
from dataclasses import dataclass
import websockets

log = logging.getLogger(__name__)

@dataclass
class PriceState:
    price: float | None = None
    event_time_ms: int | None = None

# =============================================================
# TERMINAL COLORS
# =============================================================

YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

class BinanceFeed:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.state = PriceState()
        self._stop = False

    async def run(self):
        while not self._stop:
            try:
                log.info(YELLOW + "BINANCE websocket connecting" + RESET)
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                ) as ws:
                    log.info(YELLOW + "BINANCE websocket connected" + RESET)
                    async for raw in ws:
                        if self._stop:
                            break
                        msg = json.loads(raw)
                        if "p" in msg:
                            self.state.price = float(msg["p"])
                            self.state.event_time_ms = int(msg.get("E", time.time()*1000))
            except Exception as exc:
                log.warning(RED + "BINANCE websocket error: %s; reconnecting" + RESET, exc)
                await asyncio.sleep(2)

    def stop(self):
        self._stop = True
