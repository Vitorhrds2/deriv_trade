"""Teste de MEMORIA dos spikes Boom/Crash (finaliza o TODO do boom_crash_analyzer).

Pergunta: o intervalo entre spikes e memoryless (geometrico/Poisson) ou tem MEMORIA
(hazard sobe com o tempo -> spike "atrasado" fica mais provavel -> edge de timing)?

Tese a defender (T2): apos um 'dry run' longo, P(spike no proximo tick) > taxa base.
Se a hazard for ~constante, a tese morre (falacia do apostador num processo sem memoria).

Le os gaps de boom_distances.txt (offline). So stdlib.
"""
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "boom_distances.txt")
SYMBOL_N = 500  # BOOM500 -> 1 spike a cada ~500 ticks (spec)


def load_gaps(path):
    gaps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                gaps.append(int(float(line)))
    return [g for g in gaps if g >= 0]


def conditional_survival(gaps, m):
    """P(gap > 2m | gap > m). Exponencial (memoryless) -> ~0.5 (pois m=mediana)."""
    past_m = [g for g in gaps if g > m]
    if not past_m:
        return None
    past_2m = [g for g in past_m if g > 2 * m]
    return len(past_2m) / len(past_m)


def hazard_by_age(gaps, binsize):
    """h(a) = P(spike em [a, a+bin) | sobreviveu ate a). Memoryless -> ~constante."""
    maxg = max(gaps)
    rows = []
    a = 0
    while a <= maxg:
        at_risk = sum(1 for g in gaps if g >= a)
        events = sum(1 for g in gaps if a <= g < a + binsize)
        if at_risk >= 8:  # so reporta bins com amostra
            rows.append((a, a + binsize, at_risk, events, events / at_risk))
        a += binsize
    return rows


def main():
    if not os.path.exists(PATH):
        print(f"!! {PATH} nao encontrado. Rode boom_crash_analyzer.py antes.")
        return
    gaps = load_gaps(PATH)
    n = len(gaps)
    mean = st.mean(gaps)
    med = st.median(gaps)
    sd = st.pstdev(gaps)
    cv = sd / mean if mean else float("nan")

    print("=" * 70)
    print(f"BOOM/CRASH spike-gap memory test  (n={n} gaps, simbolo ~BOOM{SYMBOL_N})")
    print("=" * 70)
    print(f"  media   = {mean:8.1f} ticks   (spec ~{SYMBOL_N})")
    print(f"  mediana = {med:8.1f}")
    print(f"  desvio  = {sd:8.1f}")
    print(f"  CV (sd/media) = {cv:5.3f}   [geometrico/exponencial ~1.00;"
          f" <0.7 = regular/previsivel; >1.3 = clusterizado]")
    print(f"  min/max = {min(gaps)} / {max(gaps)}")

    # Taxa base implicita
    p_base = 1.0 / mean
    print(f"\n  Taxa base de spike ~ 1/{mean:.0f} = {p_base*100:.3f}% por tick")

    # Teste 1: sobrevivencia condicional
    cs = conditional_survival(gaps, med)
    print("\n-- Teste 1: sobrevivencia condicional  P(gap>2*mediana | gap>mediana) --")
    print(f"   observado = {cs*100:.1f}%   | memoryless(exponencial) ~ 50%")
    if cs is not None:
        if cs < 0.40:
            print("   -> ABAIXO de 50%: hazard CRESCE (spike fica 'atrasado') -> MEMORIA (pro-tese)")
        elif cs > 0.60:
            print("   -> ACIMA de 50%: hazard CAI (spikes clusterizam) -> anti-timing")
        else:
            print("   -> ~50%: consistente com MEMORYLESS (sem edge de timing)")

    # Teste 2: hazard por idade
    binsize = max(50, int(round(mean / 6)))
    print(f"\n-- Teste 2: hazard rate por idade (bin={binsize} ticks) --")
    print(f"   {'idade':>12} {'em_risco':>9} {'spikes':>7} {'hazard':>8}")
    rows = hazard_by_age(gaps, binsize)
    for lo, hi, at_risk, ev, h in rows:
        bar = "#" * int(round(h * 60))
        print(f"   [{lo:5d},{hi:5d}) {at_risk:9d} {ev:7d} {h*100:7.2f}%  {bar}")
    # tendencia: media das hazards do terco inicial vs terco final
    if len(rows) >= 3:
        k = max(1, len(rows) // 3)
        h_first = st.mean(r[4] for r in rows[:k])
        h_last = st.mean(r[4] for r in rows[-k:])
        print(f"\n   hazard media (idade baixa) = {h_first*100:.2f}%")
        print(f"   hazard media (idade alta)  = {h_last*100:.2f}%")
        ratio = h_last / h_first if h_first else float("nan")
        print(f"   razao alta/baixa = {ratio:.2f}x")

    # Veredito
    print("\n" + "=" * 70)
    print("VEREDITO")
    print("=" * 70)
    memoryless = (cs is not None and 0.40 <= cs <= 0.60) and (0.75 <= cv <= 1.30)
    if memoryless:
        print("  Consistente com MEMORYLESS (geometrico). 'Spike atrasado' = falacia do")
        print("  apostador. Sem edge de timing: P(spike)~taxa base independ. da idade.")
        print("  => Tese T2 (timing de Boom/Crash) REFUTADA neste dado. Custo do drift")
        print("     pago enquanto espera mata qualquer entrada 'overdue'.")
    else:
        print("  Desvio do memoryless detectado (ver CV e hazard). POSSIVEL edge de timing")
        print("  -> proximo passo: validar com amostra MAIOR e fresca, depois EV vs custo")
        print("     (spike e enorme; se a hazard concentra, multiplier posicionado pode pagar).")
    print("=" * 70)
    print("AVISO: boom_distances.txt pode estar duplicado/antigo; reconfirmar com coleta")
    print("fresca (boom_crash_analyzer.py com calibracao de SPIKE_MULT) antes de capital.")


if __name__ == "__main__":
    main()
