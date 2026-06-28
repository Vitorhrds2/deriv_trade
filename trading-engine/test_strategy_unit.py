"""Testes de regressão offline (sem rede) para a lógica de risco da Skynet.

Cobrem exatamente os 2 bugs da Batalha dos Esquadrões + o regex de PnL do monitor:
  1. stake nunca pode ter > 2 casas decimais;
  2. taxas de juros distintas produzem stakes distintas;
  3. o orquestrador precisa casar o formato de log antigo e o novo.

Rodar:  python -m unittest test_strategy_unit -v
"""
import unittest

from strategy_utils import (
    LOSS_PATTERN,
    WIN_PATTERN,
    apply_compound,
    apply_freeroll_split,
    sanitize_stake,
)


def decimals(x):
    s = f"{x:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


class TestSanitizeStake(unittest.TestCase):
    def test_never_more_than_2_decimals(self):
        for v in [10.2175, 10.005, 0.1 + 0.2, 65.789, 12.999, 100.0 / 3, 0.35]:
            self.assertLessEqual(decimals(sanitize_stake(v)), 2, msg=f"falhou para {v}")

    def test_known_roundings(self):
        self.assertEqual(sanitize_stake(10.2175), 10.22)
        self.assertEqual(sanitize_stake(10.001), 10.0)
        self.assertEqual(sanitize_stake(0.20), 0.2)


class TestCompound(unittest.TestCase):
    def test_distinct_rates_give_distinct_stakes(self):
        base, profit = 10.0, 0.96
        s0 = apply_compound(base, profit, 0.0)
        s25 = apply_compound(base, profit, 0.25)
        s50 = apply_compound(base, profit, 0.50)
        self.assertEqual(s0, 10.0)
        self.assertLess(s25, s50)
        self.assertNotEqual(s25, s50)

    def test_result_is_sanitized(self):
        self.assertLessEqual(decimals(apply_compound(10.0, 0.873, 0.25)), 2)


class TestFreerollSplit(unittest.TestCase):
    def test_split_values_and_rounding(self):
        new_stake, rescue = apply_freeroll_split(20.0, 4.0, reinvest=0.75)
        self.assertEqual(rescue, 1.0)
        self.assertEqual(new_stake, 23.0)
        self.assertLessEqual(decimals(new_stake), 2)
        self.assertLessEqual(decimals(rescue), 2)


class TestPnlRegex(unittest.TestCase):
    def test_new_format_matches(self):
        self.assertTrue(WIN_PATTERN.search("[1HZ10V] ✅ WIN (54W - 8L) | Lucro: +$1.21 | PnL"))
        self.assertTrue(LOSS_PATTERN.search("[1HZ10V] ❌ LOSS (10W - 2L) | Prejuízo: $-10.00 | PnL"))

    def test_old_format_still_matches(self):
        self.assertTrue(WIN_PATTERN.search("✅ WIN | Lucro: +$0.87 | PnL"))
        self.assertTrue(LOSS_PATTERN.search("❌ LOSS | Prejuízo: $-60.00 | PnL"))

    def test_value_extraction(self):
        self.assertEqual(WIN_PATTERN.search("✅ WIN (1W - 0L) | Lucro: +$1.21 |").group(1), "1.21")
        self.assertEqual(LOSS_PATTERN.search("❌ LOSS (0W - 1L) | Prejuízo: $-10.00 |").group(1), "10.00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
