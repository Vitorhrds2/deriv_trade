"""Orquestrador multi-venue: compara Binance (verdade), Polymarket NATIVA (CLOB direto) e
Jupiter Prediction API (agregador) pro MESMO mercado BTC Up/Down (5m/15m), usando o registry
de venues (venues/registry.py) pra instanciar tudo -- primeira vez que o registry e exercitado
de verdade neste repo (ate aqui, todo script importava as classes direto).

Pergunta que este script responde: **Jupiter e um substituto viavel da Polymarket nativa** pra
fins de hipotese tipo PA5 (staleness/lead-lag do livro perto do settlement)? Mede:
  1. Staleness de cada fonte (quantos valores DISTINTOS ela retorna na janela -- uma fonte
     "presa"/cacheada repete o mesmo preco por varios ciclos).
  2. Divergencia de preco entre Polymarket nativa e Jupiter pro MESMO market/token.
  3. Disponibilidade (taxa de sucesso) de cada fonte.

NAO reimplementa a metodologia estatistica completa do PA5 (lead-lag via cross-correlation,
bootstrap CI, A/B paper) -- isso vive em polymarket_arb_stats.py, branch feat/polymarket-arb
(Carlos), fora desta branch de proposito. Este e um comparador de FONTES DE DADOS pra decidir
se vale a pena estender aquela metodologia pra Jupiter no futuro, nao um novo teste de
hipotese de trading em si.

Descoberta da janela ativa reproduz next_window() do Carlos (ver git show
origin/feat/polymarket-arb:trading-engine/polymarket_lag_probe.py) -- construcao DETERMINISTICA
do slug (sufixo = epoch unix do inicio da janela, alinhado ao grid do horizonte), nao listagem
por data (que ele documentou devolver janelas futuras/antigas erradas). O mesmo slug e usado pra
achar o market equivalente na Jupiter (confirmado ao vivo em 2026-07-02 que ela agrega esses
markets com o MESMO slug em metadata.slug).

Uso:
    PYTHONPATH=. .venv/bin/python3 -u multi_venue_compare.py --total-hours 2 --interval-s 3
"""
import argparse
import asyncio
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from venues import get_venue, list_venues

GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "multi-venue-orchestrator/1.0 (research; read-only)"}

# Achado empirico (2026-07-02): a 1a janela testada so casou com a Jupiter pq foi olhada
# 8min38s DEPOIS dela ja ter aberto na Polymarket (deu tempo da Jupiter indexar); toda janela
# seguinte e olhada ~no instante em que abre (next_window() e chamado assim que a anterior
# fecha) e a busca original so tentava UMA VEZ -- ou seja, praticamente garantido nao achar
# nada exceto por sorte de timing. Retry periodico cobre o lag de indexacao do lado da Jupiter.
JUP_RETRY_INTERVAL_S = 30.0


def _get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_horizon_min(substr: str):
    """Extrai o horizonte em minutos do substr (...-5m / ...-15m)."""
    for part in substr.split("-"):
        if part.endswith("m") and part[:-1].isdigit():
            return int(part[:-1])
    return None


def resolve_market_meta(slug: str, timeout: int = 10):
    """Tokens CLOB + endDate pro slug -- equivalente a resolve_market() do Carlos
    (polymarket_lag_probe.py, feat/polymarket-arb), sem depender daquele branch."""
    data = _get(f"{GAMMA}/markets?slug={urllib.parse.quote(slug)}", timeout=timeout)
    rows = data if isinstance(data, list) else data.get("data", [])
    if not rows:
        raise RuntimeError(f"mercado nao encontrado: {slug}")
    m = rows[0]
    raw = m.get("clobTokenIds") or "[]"
    tokens = json.loads(raw) if isinstance(raw, str) else raw
    end = datetime.fromisoformat(m["endDate"].replace("Z", "+00:00"))
    return tokens, end


def next_window(substr: str, after_ts: float, min_lead_s: float, timeout: int = 15, tries: int = 6):
    """Constroi deterministicamente o slug da janela iminente em vez de listar/filtrar por
    data (a listagem pode devolver janelas futuras/antigas, nao a iminente -- descoberta
    documentada pelo Carlos em feat/polymarket-arb::next_window, reproduzida aqui).

    O sufixo do slug e o epoch unix do INICIO da janela, alinhado ao grid do horizonte (5m ->
    multiplos de 300s; 15m -> 900s). Calcula o epoch esperado e confirma via Gamma (as janelas
    sao criadas com antecedencia, entao tenta algumas subsequentes se a imediata ainda nao
    existir)."""
    horizon = _parse_horizon_min(substr)
    if not horizon:
        raise ValueError(f"nao consegui extrair horizonte (Nm) de '{substr}'")
    step = horizon * 60
    deadline = after_ts + min_lead_s
    begin0 = (int(deadline) // step) * step
    last_err = None
    for k in range(tries):
        begin_epoch = begin0 + k * step
        if begin_epoch + step <= deadline:
            continue
        slug = f"{substr}-{begin_epoch}"
        try:
            tokens, end = resolve_market_meta(slug, timeout=timeout)
            return slug, tokens, end
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"nenhuma janela '{substr}' resolvida em {tries} tentativas: {last_err}")


def find_jupiter_market_for_slug(jupiter_venue, slug: str, category: str = "crypto", provider: str = "polymarket",
                                  page_size: int = 20, max_pages: int = 10):
    """Acha o market da Jupiter cujo metadata.slug bate com o slug nativo da Polymarket.
    Pagina (confirmado ao vivo: default do /events e so ~10 itens, e ha centenas no total pra
    crypto/polymarket -- o slug atual pode estar em qualquer pagina, achado empirico: janelas
    btc-updown-15m apareceram espalhadas dentro dos primeiros ~50 itens numa amostra)."""
    for page in range(max_pages):
        start = page * page_size
        try:
            events = jupiter_venue.list_events(category=category, provider=provider, start=start, limit=page_size)
        except Exception:
            continue
        if not events:
            break
        for ev in events:
            if ev.get("metadata", {}).get("slug") == slug:
                markets = ev.get("markets", [])
                return markets[0] if markets else None
    return None


async def _noop_on_update(_update) -> None:
    return None


def summarize(rows: list) -> dict:
    def distinct_ratio(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return None, 0
        return round(len(set(vals)) / len(vals), 3), len(vals)

    def success_rate(ok_key):
        vals = [r[ok_key] for r in rows if ok_key in r]
        return round(sum(vals) / len(vals), 3) if vals else None

    poly_diversity, poly_n = distinct_ratio("polymarket_up_price")
    jup_diversity, jup_n = distinct_ratio("jupiter_up_price")

    diffs = [
        abs(r["polymarket_up_price"] - r["jupiter_up_price"])
        for r in rows
        if r.get("polymarket_up_price") is not None and r.get("jupiter_up_price") is not None
    ]

    return {
        "n_cycles": len(rows),
        "binance_success_rate": success_rate("binance_ok"),
        "polymarket_success_rate": success_rate("polymarket_ok"),
        "jupiter_success_rate": success_rate("jupiter_ok"),
        "polymarket_price_diversity_ratio": poly_diversity,  # 1.0 = todo ciclo deu preco novo; perto de 0 = stale/cacheado
        "polymarket_n_ok": poly_n,
        "jupiter_price_diversity_ratio": jup_diversity,
        "jupiter_n_ok": jup_n,
        "n_comparable_poly_vs_jupiter": len(diffs),
        "mean_abs_diff_poly_vs_jupiter": round(sum(diffs) / len(diffs), 5) if diffs else None,
        "max_abs_diff_poly_vs_jupiter": round(max(diffs), 5) if diffs else None,
        "updated_at": now_iso(),
    }


async def run_window(args, binance, polymarket, jupiter, all_rows: list, out_fh) -> None:
    """Descobre a janela Up/Down iminente e faz polling das 3 fontes ate ela fechar (ou o
    duration-s da janela, o que vier primeiro). Acrescenta as linhas em `all_rows` (acumulado
    entre janelas) e escreve cada linha em `out_fh` (arquivo ja aberto, compartilhado entre
    chamadas -- nao reabre a cada janela)."""
    slug, tokens, end_dt = next_window(args.substr, time.time(), args.min_lead_s)
    print(f"Janela ativa: {slug} (fecha em {end_dt.isoformat()})", flush=True)

    up_token = tokens[0]

    jup_market_id = None
    jup_attempts = 0
    jup_last_try_ts = 0.0

    def try_find_jupiter():
        nonlocal jup_market_id, jup_attempts, jup_last_try_ts
        jup_attempts += 1
        jup_last_try_ts = time.time()
        jup_market = find_jupiter_market_for_slug(jupiter, slug)
        jup_market_id = jup_market.get("marketId") if jup_market else None

    try_find_jupiter()
    if jup_market_id is None:
        print(f"AVISO: slug '{slug}' nao encontrado nos eventos da Jupiter agora -- "
              f"tentando de novo a cada {JUP_RETRY_INTERVAL_S:.0f}s durante a janela "
              f"(lag de indexacao conhecido do lado da Jupiter).", flush=True)
    else:
        print(f"Market Jupiter equivalente: marketId={jup_market_id}", flush=True)

    end_time = min(time.time() + args.duration_s, end_dt.timestamp())
    while time.time() < end_time:
        if jup_market_id is None and (time.time() - jup_last_try_ts) >= JUP_RETRY_INTERVAL_S:
            try_find_jupiter()
            if jup_market_id is not None:
                print(f"Market Jupiter equivalente encontrado apos {jup_attempts} tentativas: "
                      f"marketId={jup_market_id}", flush=True)

        row = {"ts": now_iso(), "slug": slug}

        try:
            row["binance_price"] = await binance.get_price("BTCUSDT")
            row["binance_ok"] = True
        except Exception as e:
            row["binance_ok"] = False
            row["binance_error"] = str(e)[:150]

        try:
            row["polymarket_up_price"] = await polymarket.get_price(up_token)
            row["polymarket_ok"] = True
        except Exception as e:
            row["polymarket_ok"] = False
            row["polymarket_error"] = str(e)[:150]

        if jup_market_id is not None:
            try:
                row["jupiter_up_price"] = await jupiter.get_price(jup_market_id)
                row["jupiter_ok"] = True
            except Exception as e:
                row["jupiter_ok"] = False
                row["jupiter_error"] = str(e)[:150]

        all_rows.append(row)
        out_fh.write(json.dumps(row) + "\n")
        out_fh.flush()
        print(
            f"[{row['ts']}] binance={row.get('binance_price')} "
            f"poly_up={row.get('polymarket_up_price')} jup_up={row.get('jupiter_up_price')}",
            flush=True,
        )

        summary = summarize(all_rows)
        with open(args.summary, "w") as sf:
            json.dump(summary, sf, indent=2)

        await asyncio.sleep(args.interval_s)


async def run(args) -> list:
    print("Venues registradas:", sorted(list_venues().keys()), flush=True)

    binance = get_venue("binance")()
    polymarket = get_venue("polymarket")()
    jupiter = get_venue("jupiter_prediction")()

    if not jupiter.api_key:
        print("SEM JUPITER_API_KEY carregada -- abortando", flush=True)
        return []

    binance_task = asyncio.create_task(binance.stream(["BTCUSDT"], _noop_on_update))
    await asyncio.sleep(2.0)  # da tempo do primeiro tick da WS chegar antes do 1o get_price

    all_rows = []
    session_end = time.time() + args.total_hours * 3600
    try:
        with open(args.out, "a") as f:
            while time.time() < session_end:
                try:
                    await run_window(args, binance, polymarket, jupiter, all_rows, f)
                except Exception as e:
                    print(f"AVISO: janela abortada por erro ({e}); tentando a proxima em 5s", flush=True)
                    await asyncio.sleep(5.0)
    finally:
        binance_task.cancel()
        try:
            await binance_task
        except (asyncio.CancelledError, Exception):
            pass

    return all_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--substr", default="btc-updown-15m", help="substring do slug (determina o horizonte, ex.: -15m ou -5m)")
    parser.add_argument("--min-lead-s", type=float, default=60.0, help="tempo minimo de folga antes do fechamento da janela escolhida")
    parser.add_argument("--duration-s", type=float, default=950.0, help="teto de duracao POR JANELA (o fechamento natural da janela geralmente manda antes)")
    parser.add_argument("--total-hours", type=float, default=1.0, help="duracao total da sessao, encadeando janelas consecutivas")
    parser.add_argument("--interval-s", type=float, default=3.0)
    parser.add_argument("--out", default="multi_venue_compare_log.jsonl")
    parser.add_argument("--summary", default="multi_venue_compare_summary.json")
    args = parser.parse_args()

    rows = asyncio.run(run(args))
    if rows:
        print("\n=== RESUMO ===", flush=True)
        print(json.dumps(summarize(rows), indent=2), flush=True)


if __name__ == "__main__":
    main()
