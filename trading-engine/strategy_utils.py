"""Funções puras de gestão de risco da Skynet (Oráculo Dinâmico).

Centralizadas aqui para terem fonte única de verdade e serem testáveis sem rede.
Foi nesta lógica que moravam os 2 bugs da "Batalha dos Esquadrões":
  - casas decimais > 2 na stake (rejeitada pela Deriv);
  - taxa de juros composta indistinta entre esquadrões.
"""
import re


def sanitize_stake(value):
    """A Deriv rejeita ordens DIGIT com stake de mais de 2 casas decimais.

    Formatar com 2 casas e reconverter garante que o JSON enviado nunca tenha
    ruído de ponto flutuante (ex.: 10.2175 -> 10.22, 0.1+0.2 -> 0.3).
    """
    return float(f"{float(value):.2f}")


def apply_compound(current_stake, profit, rate):
    """Fase 1 (Breakeven): reinveste `rate` do lucro na próxima stake."""
    return sanitize_stake(current_stake + profit * rate)


def apply_freeroll_split(current_stake, profit, reinvest=0.75):
    """Fase 2 (Freeroll/House Money): reinveste parte do lucro, resgata o resto.

    Retorna (nova_stake, valor_resgatado), ambos saneados a 2 casas.
    """
    rescue = sanitize_stake(profit * (1 - reinvest))
    new_stake = sanitize_stake(current_stake + profit * reinvest)
    return new_stake, rescue


# Padrões de PnL tolerantes ao formato antigo (`WIN | Lucro`) e ao novo
# (`WIN (54W - 8L) | Lucro`). Usados pelos orquestradores para o PnL global.
WIN_PATTERN = re.compile(r"✅ WIN(?: \([^)]*\))? \| Lucro: \+\$([\d\.]+)")
LOSS_PATTERN = re.compile(r"❌ LOSS(?: \([^)]*\))? \| Prejuízo: \$\-?([\d\.]+)")
