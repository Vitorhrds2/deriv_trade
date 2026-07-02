"""Analise exploratoria: a Jupiter (que agrega liquidez da Polymarket) atrasa em relacao ao
preco nativo da Polymarket no mesmo mercado BTC Up/Down? Se sim, e por quanto -- isso e a base
de uma eventual lag-arb (ver o preco mudar na Polymarket, negociar na Jupiter antes dela alcancar).

Relevante porque a Polymarket bloqueia colocacao de ordem via API no Brasil (geoblock confirmado),
mas a Jupiter (Solana, sem geoblock) e uma via de execucao alternativa para a MESMA liquidez.

Usa apenas as linhas onde polymarket_ok E jupiter_ok sao true (mercado casado com sucesso).
Amostra pequena esperada (a Jupiter nem sempre tem o mesmo slug listado) -- tratar como
exploratorio, nao como veredito definitivo.
"""
import json
import statistics
from collections import defaultdict

LOG_FILE = "multi_venue_compare_log.jsonl"

rows = []
with open(LOG_FILE) as f:
    for line in f:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("polymarket_ok") and d.get("jupiter_ok"):
            rows.append(d)

print(f"Total de linhas no log: {sum(1 for _ in open(LOG_FILE))}")
print(f"Linhas com Polymarket E Jupiter validos simultaneamente: {len(rows)}\n")

by_slug = defaultdict(list)
for r in rows:
    by_slug[r["slug"]].append(r)

print(f"Janelas (slugs) distintas com match: {len(by_slug)}")
for slug, pts in sorted(by_slug.items()):
    print(f"  {slug}: {len(pts)} pontos")

# Diferenca simultanea (mesmo timestamp de amostragem) entre os dois precos de "UP".
diffs = [r["polymarket_up_price"] - r["jupiter_up_price"] for r in rows]
abs_diffs = [abs(d) for d in diffs]

print("\n--- Diferenca simultanea Polymarket_up - Jupiter_up (mesmo instante) ---")
if diffs:
    print(f"Media: {statistics.mean(diffs):+.4f} | Media abs: {statistics.mean(abs_diffs):.4f}")
    print(f"Desvio padrao: {statistics.pstdev(diffs):.4f} | Max abs: {max(abs_diffs):.4f}")
    n_idêntico = sum(1 for d in abs_diffs if d < 1e-9)
    print(f"Pontos IDENTICOS (diff=0): {n_idêntico}/{len(rows)} ({n_idêntico/len(rows)*100:.1f}%)")
else:
    print("Sem overlap suficiente.")

# Analise de lag por janela: desloca jupiter_up_price em k passos (amostragem ~3.3s/passo) e
# ve em qual k a correlacao com polymarket_up_price(t) e maxima -- k>0 sugeriria Jupiter
# "atrasado" (repete o valor que a Polymarket tinha k passos atras).
print("\n--- Analise de lag por janela (correlacao Polymarket(t) vs Jupiter(t+k)) ---")
for slug, pts in sorted(by_slug.items()):
    if len(pts) < 10:
        print(f"  {slug}: n={len(pts)} (pequeno demais pra lag, pulando)")
        continue
    pts = sorted(pts, key=lambda r: r["ts"])
    poly = [r["polymarket_up_price"] for r in pts]
    jup = [r["jupiter_up_price"] for r in pts]

    best_k, best_corr = 0, -2.0
    results = {}
    for k in range(-5, 6):
        if k >= 0:
            a, b = poly[: len(poly) - k or None], jup[k:]
        else:
            a, b = poly[-k:], jup[: len(jup) + k]
        if len(a) < 5 or len(set(a)) < 2 or len(set(b)) < 2:
            continue
        try:
            corr = statistics.correlation(a, b)
        except statistics.StatisticsError:
            continue
        results[k] = corr
        if corr > best_corr:
            best_corr, best_k = corr, k

    print(f"  {slug} (n={len(pts)}): melhor lag k={best_k} (corr={best_corr:.3f}) | todos: "
          + ", ".join(f"k={k}:{c:.2f}" for k, c in sorted(results.items())))

print("\n(k>0 => Jupiter(t+k) casa melhor com Polymarket(t), ou seja Jupiter parece atrasado "
      "~k*intervalo_de_amostragem em relacao a Polymarket. k=0 => sem lag detectavel nesta amostra.)")
