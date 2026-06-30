"""Estatistica e matematica PURA (sem rede, sem dependencias) para o cacador de
arbitragem na Polymarket.

Por que existe
--------------
Mesma filosofia que matou o Oraculo e refutou a H3 de latencia: NADA de capital sem
significancia estatistica e sem vencer a BARRA DE CUSTO com profundidade EXECUTAVEL
(nao o midpoint). Um "gap de preco" exibido nao e lucro; so e edge o que sobra depois
de andar o livro de ofertas e pagar taxa/gas/spread.

Convencoes
----------
  - precos de token em [0, 1] (preco do "YES" = probabilidade implicita).
  - um livro e uma lista de niveis (price, size), asks em ordem crescente de preco,
    bids em ordem decrescente. `size` em unidades de token (cada unidade paga 1 USDC
    se a condicao resolver TRUE).
  - edge liquido por conjunto = 1 - (custo executavel de comprar 1 unidade de cada
    "YES" do conjunto completo) - custos. > 0 com folga de custo = arbitragem long.

Todas as funcoes sao deterministicas e cobertas por `test_polymarket_arb_stats.py`.
"""
import math

# Valor critico |z| bicaudal para IC de Wilson (mesma tabela do anomaly_stats).
Z_CRIT = {
    0.05: 1.959964,
    0.01: 2.575829,
    0.001: 3.290527,
}


def wilson_interval(successes, n, z=1.959964):
    """IC de Wilson para uma proporcao binomial. Retorna (low, high) em [0, 1].

    Usado para exigir significancia ANTES de capital: uma janela so vira "edge" se o
    LIMITE INFERIOR do IC do net-positivo bater a barra — pessimista de proposito,
    igual ao monitor de anomalias.
    """
    if n <= 0:
        return (0.0, 1.0)
    phat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2.0 * n)) / denom
    margin = (z * math.sqrt((phat * (1.0 - phat) + z2 / (4.0 * n)) / n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def walk_book_cost(levels, qty):
    """Custo EXECUTAVEL de comprar (ou receita de vender) `qty` unidades andando o livro.

    `levels`: [(price, size), ...] ja na ordem certa (asks crescente p/ comprar,
    bids decrescente p/ vender). Retorna o custo/receita total em USDC, ou None se
    a profundidade for insuficiente (nao da pra mentir sobre o que nao existe).
    """
    if qty <= 0:
        return 0.0
    remaining = qty
    total = 0.0
    for price, size in levels:
        if size <= 0:
            continue
        take = min(remaining, size)
        total += take * price
        remaining -= take
        if remaining <= 1e-12:
            return total
    return None  # profundidade insuficiente


def max_fillable_set(books_asks):
    """Maior `qty` de CONJUNTO COMPLETO comprável: limitado pela perna mais rasa.

    `books_asks`: lista de livros de ask (um por condicao "YES"). Para travar arbitragem
    de rebalanceamento precisamos comprar 1 unidade de CADA perna; a quantidade viavel
    e o minimo da profundidade total de cada livro.
    """
    depths = []
    for asks in books_asks:
        depths.append(sum(max(0.0, s) for _, s in asks))
    return min(depths) if depths else 0.0


def rebalancing_long_edge(books_asks, qty, taker_rate=0.0, fixed_cost=0.0):
    """Edge LIQUIDO de uma arbitragem de rebalanceamento LONG (Σ "YES" < 1).

    Compra `qty` de cada "YES" do conjunto completo. No resolve, exatamente uma perna
    paga 1 USDC/unidade -> recebe `qty`. Edge bruto = qty - Σ custo_executavel.
    Custo = taker_rate sobre o notional comprado + fixed_cost (gas/bridge).

    Retorna dict com bruto, custos e net. net = None se faltar profundidade em qualquer perna.
    """
    if qty <= 0:
        return {"qty": 0.0, "gross": 0.0, "fees": 0.0, "net": 0.0, "sum_ask": 0.0}
    total_buy = 0.0
    for asks in books_asks:
        c = walk_book_cost(asks, qty)
        if c is None:
            return {"qty": qty, "gross": None, "fees": None, "net": None, "sum_ask": None}
        total_buy += c
    payout = qty  # uma perna resolve TRUE -> 1 USDC/unidade
    gross = payout - total_buy
    fees = taker_rate * total_buy + fixed_cost
    net = gross - fees
    sum_ask = total_buy / qty if qty else 0.0
    return {"qty": qty, "gross": gross, "fees": fees, "net": net, "sum_ask": sum_ask}


def rebalancing_short_edge(books_bids, qty, taker_rate=0.0, fixed_cost=0.0, n_conditions=None):
    """Edge LIQUIDO de uma arbitragem de rebalanceamento SHORT (Σ "YES" > 1).

    Estrategia: para cada condicao, cria um SPLIT (compra 1 YES + 1 NO por 1 USDC) e
    vende o "YES" imediatamente. Receita de vender = Σ executavel dos bids de "YES".
    Custo do split = qty * n_conditions (1 USDC por par) e fica com os "NO".
    Edge SHORT por unidade ~ (Σ preco YES executavel) - 1, replicado por condicao.

    Simplificacao auditavel: net = Σ receita_venda_YES - qty*n - custos, onde guardar
    os NO ainda vale (n-1)*qty no resolve. Aqui medimos apenas o lucro TRAVADO imediato
    de vender o YES sobrevalorizado (limite inferior do edge short).
    """
    n = n_conditions if n_conditions is not None else len(books_bids)
    if qty <= 0 or n <= 0:
        return {"qty": 0.0, "gross": 0.0, "fees": 0.0, "net": 0.0, "sum_bid": 0.0}
    total_sell = 0.0
    for bids in books_bids:
        r = walk_book_cost(bids, qty)
        if r is None:
            return {"qty": qty, "gross": None, "fees": None, "net": None, "sum_bid": None}
        total_sell += r
    # split custa 1 USDC por par; guardamos os NO (valem (n-1) no resolve), entao o
    # custo "afundado" imediato do conjunto e (n*qty - (n-1)*qty) = qty -> 1 unidade.
    split_sunk = qty
    gross = total_sell - split_sunk
    fees = taker_rate * total_sell + fixed_cost
    net = gross - fees
    sum_bid = total_sell / qty if qty else 0.0
    return {"qty": qty, "gross": gross, "fees": fees, "net": net, "sum_bid": sum_bid}


def combinatorial_edge(sum_s_ask, sum_sprime_bid, taker_rate=0.0, fixed_cost=0.0):
    """Edge de arbitragem COMBINATORIA entre dois mercados dependentes (Def. 3.4).

    Caso simplificado: se a soma do preco "YES" do subconjunto S de M1 (comprado a ask)
    e menor que a soma vendavel do subconjunto dependente S' de M2 (a bid), trava-se um
    hedge. Edge bruto = sum_sprime_bid - sum_s_ask. Retorna net apos custo.
    """
    gross = sum_sprime_bid - sum_s_ask
    notional = sum_s_ask + sum_sprime_bid
    fees = taker_rate * notional + fixed_cost
    return {"gross": gross, "fees": fees, "net": gross - fees}


def cross_venue_edge(price_yes_a, price_no_b, fee_a=0.0, fee_b=0.0, fixed_cost=0.0):
    """Edge de arbitragem CROSS-VENUE (ex.: YES na venue A + NO na venue B).

    Se p_yes_a + p_no_b < 1, qualquer resolucao paga 1 e o custo foi < 1. ESTE NUMERO
    SO E REAL SE AS REGRAS DE RESOLUCAO FOREM ECONOMICAMENTE IDENTICAS (semantic
    non-fungibility e o assassino). `fee_*` modelam a taxa por venue (ex.: Kalshi
    ~7% do lucro). Retorna net por par de 1 USDC de payout.
    """
    cost = price_yes_a + price_no_b
    gross = 1.0 - cost
    fees = fee_a * price_yes_a + fee_b * price_no_b + fixed_cost
    return {"cost": cost, "gross": gross, "fees": fees, "net": gross - fees}


def net_edge_bps(net, notional):
    """Edge liquido em basis points sobre o notional (comparavel entre teses)."""
    if notional <= 0:
        return 0.0
    return 10000.0 * net / notional
