"""Coleta de ticks simultaneos de multiplos simbolos Deriv para teste de cointegracao/correlacao.

R_10, R_25, R_50, R_75, R_100 e variantes 1Hz sao todos indices sinteticos baseados em RNG.
A questao: existe correlacao/cointegracao entre eles que possa ser explorada?

Hipotese: se dois indices (ex: R_50 e R_100) sao correlacionados mas precificados
independentemente, desvios temporarios podem ser explorados apostando na convergencia.

Metodo:
  1. Subscrever ticks de todos os simbolos simultaneamente
  2. Coletar N ticks (default 5000) com timestamps alinhados
  3. Calcular correlacao de returns entre pares
  4. Teste de cointegracao (Engle-Granger)
  5. Se cointegracao encontrada, medir half-life de mean-reversion e potencial edge

Saida: CSV com ticks alinhados + relatorio estatistico.
"""
import argparse
import asyncio
import csv
import os
import sys
import time

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

# Todos os simbolos RNG (2s e 1Hz)
SYMBOLS = ["R_10", "R_25", "R_50", "R_75", "R_100",
           "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V"]

# Estado: {symbol: [{"value": float, "epoch": int, "local_t": float}, ...]}
tick_data = {s: [] for s in SYMBOLS}
tick_epochs_seen = set()


async def main():
    ap = argparse.ArgumentParser(description="Coleta de ticks simultaneos multi-simbolo")
    ap.add_argument("--count", type=int, default=5000, help="Numero de ticks por simbolo")
    ap.add_argument("--output", default="multi_symbol_ticks.csv")
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()

    # Subscrever todos os simbolos
    received = {s: 0 for s in SYMBOLS}

    def make_callback(sym):
        def cb(data):
            t = data.get("tick")
            if t and "quote" in t:
                tick_data[sym].append({
                    "value": float(t["quote"]),
                    "epoch": int(t.get("epoch", 0)),
                    "local_t": time.time(),
                })
                received[sym] += 1
        return cb

    # DerivClient so suporta um callback de tick por vez (self.callbacks["tick"]).
    # Precamos usar um unico callback que despacha por simbolo.
    # Workaround: subscrever sequencialmente mas com um callback global.
    # Vamos coletar via ticks_history em paralelo em vez de subscription.
    print(f">>> Coletando {args.count} ticks de {len(SYMBOLS)} simbolos via ticks_history...")
    print(f">>> Simbolos: {', '.join(SYMBOLS)}")

    try:
        # Coletar historico de ticks de cada simbolo em paralelo
        tasks = []
        for sym in SYMBOLS:
            tasks.append(client.get_ticks_history(sym, count=args.count, end="latest", start=1))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, res in zip(SYMBOLS, results):
            if isinstance(res, Exception):
                print(f"  {sym}: ERRO {res}")
                continue
            hist = res.get("history", {})
            prices = hist.get("prices", [])
            times = hist.get("times", [])
            tick_data[sym] = [{"value": float(p), "epoch": int(t), "local_t": 0.0}
                              for p, t in zip(prices, times)]
            print(f"  {sym}: {len(tick_data[sym])} ticks coletados")

        # Alinhar por epoch (intersecao de timestamps)
        all_epochs = {}
        for sym in SYMBOLS:
            for tick in tick_data[sym]:
                all_epochs.setdefault(tick["epoch"], {})[sym] = tick["value"]

        # Encontrar epochs onde todos simbolos tem dados
        common_epochs = sorted(
            ep for ep, syms in all_epochs.items()
            if len(syms) == len(SYMBOLS)
        )
        print(f"\nEpochs comuns (todos simbolos): {len(common_epochs)} / {len(all_epochs)} total")

        if len(common_epochs) < 50:
            print(">>> Poucos epochs em comum -- tentando alinhamento por proximidade.")
            # Alinhar por proximidade: para cada tick de R_100, encontrar tick mais proximo de cada outro
            base = "R_100"
            base_ticks = tick_data[base]
            aligned = []
            for bt in base_ticks:
                row = {"epoch": bt["epoch"], base: bt["value"]}
                for sym in SYMBOLS:
                    if sym == base:
                        continue
                    # Encontrar tick mais proximo por epoch
                    best = None
                    best_diff = float("inf")
                    for t in tick_data[sym]:
                        diff = abs(t["epoch"] - bt["epoch"])
                        if diff < best_diff:
                            best_diff = diff
                            best = t
                    if best and best_diff <= 2:  # max 2s de diferenca
                        row[sym] = best["value"]
                # So guardar se todos simbolos tem valor
                if all(s in row for s in SYMBOLS):
                    aligned.append(row)
            print(f">>> Alinhamento por proximidade: {len(aligned)} linhas alinhadas")
            common_epochs_data = aligned
        else:
            common_epochs_data = [
                {"epoch": ep, **all_epochs[ep]} for ep in common_epochs
            ]

        if not common_epochs_data:
            print(">>> Nao foi possivel alinhar dados. Abortando.")
            await client.disconnect()
            return

        # Salvar CSV
        fieldnames = ["epoch"] + SYMBOLS
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in common_epochs_data:
                writer.writerow(row)
        print(f"\nDados salvos em {args.output} ({len(common_epochs_data)} linhas)")

        # Analise estatistica
        print("\n" + "=" * 90)
        print("ANALISE DE CORRELACAO E COINTEGRACAO")
        print("=" * 90)

        try:
            import numpy as np
        except ImportError:
            print("numpy nao disponivel -- pulando analise estatistica.")
            await client.disconnect()
            return

        # Matriz de correlacao de returns (log-returns)
        data = {}
        for sym in SYMBOLS:
            vals = [row[sym] for row in common_epochs_data if sym in row]
            if len(vals) < 10:
                continue
            arr = np.array(vals)
            returns = np.diff(np.log(arr))
            data[sym] = returns

        if len(data) < 2:
            print("Dados insuficientes para correlacao.")
            await client.disconnect()
            return

        syms = sorted(data.keys())
        print(f"\nCorrelacao de log-returns ({len(common_epochs_data)} pontos):")
        print(f"{'':12s}", end="")
        for s in syms:
            print(f"{s:>12s}", end="")
        print()
        for s1 in syms:
            print(f"{s1:12s}", end="")
            for s2 in syms:
                if s1 == s2:
                    print(f"{'1.000':>12s}", end="")
                else:
                    r = np.corrcoef(data[s1], data[s2])[0, 1]
                    print(f"{r:>12.3f}", end="")
            print()

        # Cointegracao: regressao linear entre pares + teste de estacionariedade dos residuos
        print("\nTeste de cointegracao (residuos da regressao linear):")
        print(f"{'Par':25s} {'Beta':>8s} {'Corr':>8s} {'ADF_stat':>10s} {'p-value':>10s} {'Veredito':>15s}")
        print("-" * 80)

        try:
            from statsmodels.tsa.stattools import adfuller
            has_statsmodels = True
        except ImportError:
            has_statsmodels = False
            print("  (statsmodels nao disponivel -- usando teste simplificado de razao de variancia)")

        for i, s1 in enumerate(syms):
            for j, s2 in enumerate(syms):
                if j <= i:
                    continue
                r1, r2 = data[s1], data[s2]
                n = min(len(r1), len(r2))
                r1, r2 = r1[:n], r2[:n]
                corr = np.corrcoef(r1, r2)[0, 1]

                # Regressao: r1 = beta * r2 + alpha + epsilon
                beta = np.polyfit(r2, r1, 1)[0]
                residuals = r1 - beta * r2

                if has_statsmodels:
                    adf_stat, p_value, _, _, _ = adfuller(residuals, maxlag=1)
                    cointegrated = p_value < 0.05
                    verdict = "COINTEGRADO" if cointegrated else "nao"
                    print(f"{s1+' / '+s2:25s} {beta:>8.4f} {corr:>8.3f} {adf_stat:>10.4f} {p_value:>10.4f} {verdict:>15s}")
                else:
                    # Teste simplificado: razao de variancia (var(residuals) / var(r1))
                    vr = np.var(residuals) / np.var(r1) if np.var(r1) > 0 else 1
                    print(f"{s1+' / '+s2:25s} {beta:>8.4f} {corr:>8.3f} {'--':>10s} {'--':>10s} {'VR='+f'{vr:.3f}':>15s}")

        # Half-life de mean-reversion para pares mais correlacionados
        if has_statsmodels:
            print("\nHalf-life de mean-reversion (pares mais correlacionados):")
            pairs = []
            for i, s1 in enumerate(syms):
                for j, s2 in enumerate(syms):
                    if j <= i:
                        continue
                    r = np.corrcoef(data[s1], data[s2])[0, 1]
                    pairs.append((abs(r), s1, s2))
            pairs.sort(reverse=True)
            for _, s1, s2 in pairs[:5]:
                r1, r2 = data[s1], data[s2]
                n = min(len(r1), len(r2))
                r1, r2 = r1[:n], r2[:n]
                beta = np.polyfit(r2, r1, 1)[0]
                residuals = r1 - beta * r2
                # OU process: delta_resid = -kappa * resid_lag + epsilon
                delta = np.diff(residuals)
                lag = residuals[:-1]
                kappa = np.polyfit(lag, delta, 1)[0]
                if kappa < 0:
                    hl = -np.log(2) / kappa
                    print(f"  {s1} / {s2}: kappa={-kappa:.4f}, half-life={hl:.1f} ticks")
                else:
                    print(f"  {s1} / {s2}: kappa={kappa:.4f} (sem mean-reversion)")

        print("\n" + "=" * 90)
        print("NOTA: Indices sinteticos R_* e 1HZ* sao gerados por RNG independentes.")
        print("Correlacao esperada ~0. Se correlacao significativa for encontrada,")
        print("pode indicar shared seed ou estrutura comun no RNG da Deriv.")
        print("=" * 90)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
