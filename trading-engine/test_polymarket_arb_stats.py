"""Testes offline (sem rede) da matematica de arbitragem Polymarket.

Rodar: python test_polymarket_arb_stats.py   (ou: pytest -q test_polymarket_arb_stats.py)
"""
import polymarket_arb_stats as s


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_walk_book_cost_basic():
    asks = [(0.40, 100), (0.42, 100)]
    assert approx(s.walk_book_cost(asks, 50), 50 * 0.40)
    # anda dois niveis: 100@0.40 + 50@0.42
    assert approx(s.walk_book_cost(asks, 150), 100 * 0.40 + 50 * 0.42)


def test_walk_book_cost_insufficient_depth():
    asks = [(0.40, 10)]
    assert s.walk_book_cost(asks, 50) is None


def test_max_fillable_set_limited_by_shallowest():
    books = [[(0.40, 100)], [(0.55, 30)]]
    assert approx(s.max_fillable_set(books), 30)


def test_rebalancing_long_positive_edge():
    # YES_A best ask 0.42, YES_B best ask 0.55 -> soma 0.97 < 1 => edge bruto 0.03/un
    books = [[(0.42, 100)], [(0.55, 100)]]
    r = s.rebalancing_long_edge(books, qty=100, taker_rate=0.0)
    assert approx(r["sum_ask"], 0.97)
    assert approx(r["gross"], 100 * 0.03)
    assert r["net"] > 0


def test_rebalancing_long_killed_by_cost():
    # gap de 0.5c/un (0.995) mas taker 1.5% sobre notional come o edge
    books = [[(0.50, 100)], [(0.495, 100)]]
    r = s.rebalancing_long_edge(books, qty=100, taker_rate=0.015)
    assert r["sum_ask"] < 1.0          # parece arb no preco
    assert r["net"] < 0                 # mas net negativo apos custo => REFUTADA


def test_rebalancing_long_insufficient_depth_returns_none():
    books = [[(0.42, 10)], [(0.55, 100)]]
    r = s.rebalancing_long_edge(books, qty=100)
    assert r["net"] is None


def test_rebalancing_short_edge():
    # YES some 1.06 (sobrevalorizado): vender YES de 2 condicoes a bid
    bids = [[(0.56, 100)], [(0.50, 100)]]
    r = s.rebalancing_short_edge(bids, qty=100, n_conditions=2)
    assert approx(r["sum_bid"], 1.06)
    assert r["gross"] > 0


def test_cross_venue_edge_real_vs_fee_eaten():
    # 3c de gap aparente, mas Kalshi ~7% do lucro + bridge
    real = s.cross_venue_edge(0.62, 0.35, fee_a=0.0, fee_b=0.0)
    assert approx(real["cost"], 0.97)
    assert approx(real["gross"], 0.03)
    eaten = s.cross_venue_edge(0.62, 0.35, fee_a=0.0, fee_b=0.07, fixed_cost=0.02)
    assert eaten["net"] < real["net"]


def test_combinatorial_edge():
    r = s.combinatorial_edge(sum_s_ask=0.40, sum_sprime_bid=0.46, taker_rate=0.0)
    assert approx(r["gross"], 0.06)


def test_wilson_lower_bound_pessimistic():
    lo, hi = s.wilson_interval(8, 10)
    assert 0.0 <= lo <= 0.80 <= hi <= 1.0
    # amostra minuscula: limite inferior longe da media (pessimismo)
    assert lo < 0.55


def test_net_edge_bps():
    assert approx(s.net_edge_bps(0.03, 0.97), 10000 * 0.03 / 0.97)


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"  ok  {t.__name__}")
    print(f"\n{passed}/{len(tests)} testes passaram.")


if __name__ == "__main__":
    _run_all()
