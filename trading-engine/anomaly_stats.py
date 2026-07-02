"""Estatistica pura (sem rede, sem dependencias) para o monitor de anomalias sinteticas.

Toda funcao aqui e deterministica e testavel offline (`test_anomaly_stats.py`).
A logica de decisao do monitor depende destas primitivas; mante-las puras garante
que a regra que "matou o Oraculo" (significancia estatistica antes de capital)
seja auditavel sem precisar de conexao com a Deriv.

Convencoes:
  - probabilidades em [0, 1]; gross_return = payout / ask (>= 1 quando ha retorno).
  - EV por unidade apostada: EV = p_win * gross_return - 1.
"""
import math

# Valores criticos da qui-quadrado para df = 9 (10 digitos - 1).
CHI2_CRIT_DF9 = {
    0.05: 16.919,
    0.01: 21.666,
    0.001: 27.877,
}

# Valores criticos |z| bicaudais usados para alertas de vies/feed.
Z_CRIT = {
    0.05: 1.959964,
    0.01: 2.575829,
    0.001: 3.290527,
}


def wilson_interval(successes, n, z=1.959964):
    """Intervalo de confianca de Wilson para uma proporcao binomial.

    Mais honesto que o normal em amostras pequenas e perto de 0/1 — e foi o teste
    usado no relatorio de edge. Retorna (low, high) em [0, 1].
    """
    if n <= 0:
        return (0.0, 1.0)
    phat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2.0 * n)) / denom
    margin = (z * math.sqrt((phat * (1.0 - phat) + z2 / (4.0 * n)) / n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def chi_square_uniform(counts):
    """Estatistica qui-quadrado de uma contagem de categorias contra a uniforme."""
    total = sum(counts)
    k = len(counts)
    if total == 0 or k == 0:
        return 0.0
    expected = total / k
    return sum((c - expected) ** 2 / expected for c in counts)


def digit_z_scores(counts, p0=0.1):
    """z-score por categoria (digito) vs. probabilidade esperada p0.

    Util para NOMEAR qual digito esta anomalo, nao so dizer que a distribuicao toda
    esta torta. Retorna lista de z na ordem das categorias.
    """
    total = sum(counts)
    if total == 0:
        return [0.0 for _ in counts]
    sd = math.sqrt(p0 * (1.0 - p0) / total)
    if sd == 0:
        return [0.0 for _ in counts]
    return [((c / total) - p0) / sd for c in counts]


def runs_test_z(bits):
    """Teste de corridas (Wald-Wolfowitz) para aleatoriedade de uma serie binaria.

    `bits`: sequencia de 0/1 (ex.: 1 = tick subiu, 0 = desceu). z grande (em modulo)
    indica memoria/anti-memoria — um RNG justo deveria dar |z| pequeno.
    """
    n = len(bits)
    n1 = sum(1 for b in bits if b)
    n0 = n - n1
    if n1 == 0 or n0 == 0 or n < 2:
        return 0.0
    runs = 1 + sum(1 for i in range(1, n) if bits[i] != bits[i - 1])
    mu = 1.0 + (2.0 * n1 * n0) / n
    var = (2.0 * n1 * n0 * (2.0 * n1 * n0 - n)) / (n * n * (n - 1.0))
    if var <= 0:
        return 0.0
    return (runs - mu) / math.sqrt(var)


def autocorr_lag1(values):
    """Autocorrelacao de defasagem 1. ~0 para serie sem memoria."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    num = sum((values[i] - mean) * (values[i + 1] - mean) for i in range(n - 1))
    den = sum((v - mean) ** 2 for v in values)
    return num / den if den else 0.0


def implied_prob(gross_return):
    """Probabilidade implicita no payout: 1 / gross_return."""
    return 1.0 / gross_return if gross_return else 1.0


def ev_per_unit(p_win, gross_return):
    """EV por unidade apostada: p_win * gross_return - 1."""
    return p_win * gross_return - 1.0


def ev_bounds(p_lo, p_hi, gross_return):
    """Limites de EV a partir do IC da probabilidade verdadeira.

    O gross_return e conhecido exatamente (vem do payout). O que e incerto e p_win,
    entao propagamos o IC de Wilson. ev_lo > margem => a casa esta pagando demais
    COM confianca estatistica (mispricing transiente candidato).
    """
    return (ev_per_unit(p_lo, gross_return), ev_per_unit(p_hi, gross_return))


def spike_timing_z(gaps, expected_gap):
    """z-score do gap medio entre spikes vs. a especificacao (modelo geometrico).

    Indices Boom/Crash sobem/caem com um "spike" raro a cada ~N ticks. Modelando
    cada tick como Bernoulli(p=1/N), o gap (ticks entre spikes) e ~geometrico com
    media N e desvio ~N. Para M gaps, SE(media) ~= N / sqrt(M). Usar N como desvio
    e levemente conservador (o desvio real e N*sqrt(1-1/N) < N), o que reduz falso
    positivo. z<0 => spikes mais FREQUENTES que o spec; z>0 => mais RAROS.
    """
    m = len(gaps)
    if m < 2 or expected_gap <= 0:
        return 0.0
    mean_gap = sum(gaps) / m
    se = expected_gap / math.sqrt(m)
    if se == 0:
        return 0.0
    return (mean_gap - expected_gap) / se
