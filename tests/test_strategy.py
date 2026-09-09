from types import SimpleNamespace
from src.strategy import Strategy

def test_entry_window_and_direction():
    cfg = SimpleNamespace(
        round_seconds=300, entry_window_seconds=120,
        min_move_usd=70, max_move_usd=100,
        min_contract_price=.80, max_contract_price=.99,
        extreme_probability=.95, partial_hedge_pct=.10,
    )
    class Poly:
        def best_ask(self, token): return .90
    m = SimpleNamespace(up_token="UP", down_token="DOWN")
    s = Strategy(cfg, paper=True)
    d = s.evaluate(240, 10080, m, Poly())  # round start 0, move +80
    assert d.action == "ENTER"
    assert d.direction == "Up"
    assert d.contract_price == .90

def test_no_entry_if_move_too_small():
    cfg = SimpleNamespace(
        round_seconds=300, entry_window_seconds=120,
        min_move_usd=70, max_move_usd=100,
        min_contract_price=.80, max_contract_price=.99,
        extreme_probability=.95, partial_hedge_pct=.10,
    )
    class Poly:
        def best_ask(self, token): return .90
    m = SimpleNamespace(up_token="UP", down_token="DOWN")
    s = Strategy(cfg, paper=True)
    d = s.evaluate(240, 10050, m, Poly())
    assert d.action == "WAIT"
