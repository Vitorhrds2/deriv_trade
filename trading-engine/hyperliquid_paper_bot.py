#!/usr/bin/env python3
"""
D55c -- Hyperliquid LINK funding arb PAPER TRADING (OOS temporal real)

D55a walk-forward validou LINK com net +96.3bps IC95%[+71.6,+121.6] em 90d
historicos. Mas o walk-forward usou os MESMOS 90d do screening inicial --
robustez interna, nao OOS temporal de verdade. Este bot resolve isso:

Estrategia (direcao fixa, decidida no screening D55a):
  - SHORT Hyperliquid LINK-PERP
  - LONG Binance LINKUSDT-PERP
  - Posicao delta-neutral (mesmo notional nas duas pernas)
  - Mantem a posicao por N ciclos de funding (8h Binance, 1h HL)
  - Coleta funding em ambos os venues
  - Trackeia mark-to-mark P&L + funding coletado - custo de entrada

Paper trading: NAO executa ordens reais. A cada ciclo de funding da Binance
(a cada 8h), busca:
  1. Funding rate real da Binance (LINKUSDT)
  2. Funding rate real da Hyperliquid (LINK, acumulado nas 8h anteriores)
  3. Preco mark de ambos os venues
  Computa o P&L do ciclo = funding_coletado + variacao_mark * direcao

Custo de entrada: FUNDING_ARB_ROUNDTRIP_BPS (19bps), debitado uma vez no inicio.
Custo de saida: outros 19bps (debitado no fim, se sair).

Stats: Wilson no WR de ciclos positivos + bootstrap no EV/ciclo, mesmo
padrao do repo (stats_utils.summarize).

Usage:
  python3 hyperliquid_paper_bot.py                    # paper trade continuo
  python3 hyperliquid_paper_bot.py --position-usd 1000  # tamanho da posicao
  python3 hyperliquid_paper_bot.py --cycles 30         # sair apos 30 ciclos
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from stats_utils import summarize

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
UA = {"User-Agent": "hyperliquid-paper-bot/1.0 (research; paper-only)"}

HL_TAKER_BPS = 4.5
BINANCE_TAKER_BPS = 5.0
ROUNDTRIP_BPS = 2 * (HL_TAKER_BPS + BINANCE_TAKER_BPS)  # 19bps abre+fecha
ENTRY_COST_BPS = ROUNDTRIP_BPS / 2
EXIT_COST_BPS = ROUNDTRIP_BPS / 2

SYMBOL_HL = "LINK"
SYMBOL_BN = "LINKUSDT"

STATE_FILE = "d55_paper_state.json"
LOG_FILE = "d55_paper_bot.log"

DEFAULT_POSITION_USD = 1000
DEFAULT_MAX_CYCLES = 0  # 0 = infinito
STATE_VERSION = 2


def _post(body, timeout=10):
    req = urllib.request.Request(
        HL_INFO_URL, data=json.dumps(body).encode(),
        headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def hl_meta_and_ctxs():
    meta, ctxs = _post({"type": "metaAndAssetCtxs"})
    universe = meta["universe"]
    for u, c in zip(universe, ctxs):
        if u["name"] == SYMBOL_HL:
            return {
                "funding": float(c.get("funding", 0) or 0),
                "oraclePx": float(c.get("oraclePx", 0) or 0),
                "markPx": float(c.get("markPx", 0) or 0),
                "midPx": float(c.get("midPx") or 0) or 0,
            }
    return None


def hl_funding_history(start_ms, end_ms=None):
    if end_ms is None:
        end_ms = int(time.time() * 1000)
    out = []
    cursor = start_ms
    while cursor < end_ms:
        data = _post({"type": "fundingHistory", "coin": SYMBOL_HL,
                      "startTime": cursor, "endTime": end_ms})
        if not data:
            break
        batch = [{"time": int(d["time"]), "rate": float(d["fundingRate"])} for d in data]
        out.extend(batch)
        last_t = batch[-1]["time"]
        if last_t <= cursor:
            break
        cursor = last_t + 1
        if len(data) < 500:
            break
    return out


def binance_funding_history(start_ms):
    url = (f"{BINANCE_FAPI}/fundingRate?symbol={SYMBOL_BN}"
           f"&startTime={start_ms}&limit=1000")
    data = _get(url)
    return sorted(
        [{"time": int(d["fundingTime"]), "rate": float(d["fundingRate"])} for d in data],
        key=lambda event: event["time"],
    )


def binance_mark_price():
    data = _get(f"{BINANCE_FAPI}/premiumIndex?symbol={SYMBOL_BN}")
    if isinstance(data, list):
        data = data[0]
    return {
        "markPrice": float(data["markPrice"]),
        "fundingRate": float(data.get("lastFundingRate", 0)),
        "nextFundingTime": int(data.get("nextFundingTime", 0)),
    }


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_FILE)


def log(msg):
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def init_position(position_usd):
    """Inicializa posicao paper: short HL + long Binance, mesmo notional."""
    hl = hl_meta_and_ctxs()
    bn = binance_mark_price()
    if not hl or not bn:
        raise RuntimeError("Nao foi possivel buscar precos iniciais")

    entry_cost_bps = ENTRY_COST_BPS
    entry_cost_usd = position_usd * entry_cost_bps / 10000
    entry_ts = datetime.now(timezone.utc)

    state = {
        "state_version": STATE_VERSION,
        "symbol_hl": SYMBOL_HL,
        "symbol_bn": SYMBOL_BN,
        "direction_hl": "SHORT",
        "direction_bn": "LONG",
        "position_usd": position_usd,
        "entry_hl_mark": hl["markPx"],
        "entry_bn_mark": bn["markPrice"],
        "entry_ts": entry_ts.isoformat(),
        "last_bn_funding_time_ms": int(entry_ts.timestamp() * 1000),
        "entry_cost_bps": entry_cost_bps,
        "entry_cost_usd": entry_cost_usd,
        "cycles": [],
        "total_funding_hl_bps": 0,
        "total_funding_bn_bps": 0,
        "total_mark_pnl_bps": 0,
        "total_net_pnl_bps": -entry_cost_bps,  # ja debita custo de entrada
        "total_net_pnl_usd": -entry_cost_usd,
        "status": "open",
    }
    save_state(state)
    log(f"POSICAO ABERTA: SHORT HL {SYMBOL_HL} @ {hl['markPx']:.4f} | "
        f"LONG BN {SYMBOL_BN} @ {bn['markPrice']:.4f} | "
        f"notional=${position_usd} | custo entrada={entry_cost_bps}bps (${entry_cost_usd:.4f})")
    return state


def settle_cycle(state, bn_funding, hl_funding_accum_bps, hl_mark, bn_mark, funding_time_ms):
    """Registra P&L de um ciclo de funding (8h Binance)."""
    # Funding coletado:
    # - SHORT HL: se funding HL > 0, longs pagam shorts -> coletamos +funding
    #   se funding HL < 0, shorts pagam longs -> pagamos |funding|
    # - LONG BN: se funding BN > 0, longs pagam shorts -> pagamos |funding|
    #   se funding BN < 0, shorts pagam longs -> coletamos +|funding|
    hl_funding_bps = hl_funding_accum_bps  # acumulado nas 8h
    bn_funding_bps = bn_funding * 10000

    # SHORT HL: coleta quando funding > 0
    hl_collect_bps = hl_funding_bps  # positivo = coleta, negativo = paga
    # LONG BN: coleta quando funding < 0
    bn_collect_bps = -bn_funding_bps  # inverte sinal: funding negativo = coleta

    funding_pnl_bps = hl_collect_bps + bn_collect_bps

    # Mark-to-market P&L (variacao do preco desde o ciclo anterior):
    # SHORT HL: lucra quando preco cai -> pnl = (entry - current) / entry
    # LONG BN: lucra quando preco sobe -> pnl = (current - entry) / entry
    # Como delta-neutral, o mark P&L deveria ser ~0 (mesmo ativo, direcoes opostas)
    # Mas pode haver divergencia de preco entre venues
    prev_hl = state["cycles"][-1]["hl_mark"] if state["cycles"] else state["entry_hl_mark"]
    prev_bn = state["cycles"][-1]["bn_mark"] if state["cycles"] else state["entry_bn_mark"]

    hl_mark_pnl_bps = (prev_hl - hl_mark) / prev_hl * 10000  # SHORT: cai = lucro
    bn_mark_pnl_bps = (bn_mark - prev_bn) / prev_bn * 10000  # LONG: sobe = lucro
    mark_pnl_bps = hl_mark_pnl_bps + bn_mark_pnl_bps

    cycle_pnl_bps = funding_pnl_bps + mark_pnl_bps
    cycle_pnl_usd = state["position_usd"] * cycle_pnl_bps / 10000

    cycle = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "funding_time_ms": funding_time_ms,
        "hl_funding_bps": hl_funding_bps,
        "bn_funding_bps": bn_funding_bps,
        "hl_collect_bps": hl_collect_bps,
        "bn_collect_bps": bn_collect_bps,
        "funding_pnl_bps": funding_pnl_bps,
        "hl_mark": hl_mark,
        "bn_mark": bn_mark,
        "hl_mark_pnl_bps": hl_mark_pnl_bps,
        "bn_mark_pnl_bps": bn_mark_pnl_bps,
        "mark_pnl_bps": mark_pnl_bps,
        "cycle_pnl_bps": cycle_pnl_bps,
        "cycle_pnl_usd": cycle_pnl_usd,
    }
    state["cycles"].append(cycle)
    state["total_funding_hl_bps"] += hl_collect_bps
    state["total_funding_bn_bps"] += bn_collect_bps
    state["total_mark_pnl_bps"] += mark_pnl_bps
    state["total_net_pnl_bps"] += cycle_pnl_bps
    state["total_net_pnl_usd"] += cycle_pnl_usd

    n = len(state["cycles"])
    wins = sum(1 for c in state["cycles"] if c["cycle_pnl_bps"] > 0)
    wr = wins / n * 100 if n else 0

    log(f"CYCLE {n}: HL_fund={hl_funding_bps:+.3f}bps BN_fund={bn_funding_bps:+.3f}bps "
        f"| funding_pnl={funding_pnl_bps:+.3f}bps mark_pnl={mark_pnl_bps:+.3f}bps "
        f"| cycle_net={cycle_pnl_bps:+.3f}bps (${cycle_pnl_usd:+.4f}) "
        f"| TOTAL net={state['total_net_pnl_bps']:+.2f}bps (${state['total_net_pnl_usd']:+.4f}) "
        f"WR={wr:.1f}% ({wins}/{n})")
    return cycle


def run_bot(position_usd=DEFAULT_POSITION_USD, max_cycles=DEFAULT_MAX_CYCLES):
    log("=" * 80)
    log(f"D55c -- Hyperliquid LINK funding arb PAPER TRADING (OOS)")
    log(f"  Strategy: SHORT HL {SYMBOL_HL} + LONG BN {SYMBOL_BN} (delta-neutral)")
    log(f"  Position: ${position_usd} | Roundtrip cost: {ROUNDTRIP_BPS}bps")
    log(f"  Max cycles: {max_cycles if max_cycles else 'infinite'}")
    log("=" * 80)

    state = load_state()
    if state and state.get("status") == "open" and state.get("state_version") != STATE_VERSION:
        archive_file = f"{STATE_FILE}.legacy_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        with open(archive_file, "w") as f:
            json.dump(state, f, indent=2, default=str)
        log(f"Estado legado arquivado em {archive_file}; iniciando coorte v{STATE_VERSION}.")
        state = init_position(position_usd)
    elif not state or state.get("status") != "open":
        state = init_position(position_usd)
    else:
        log(f"Posicao existente encontrada: {len(state['cycles'])} ciclos, "
            f"net={state['total_net_pnl_bps']:+.2f}bps")

    entry_ts = datetime.fromisoformat(state["entry_ts"])
    last_bn_funding_time = int(state.get("last_bn_funding_time_ms", entry_ts.timestamp() * 1000))

    while True:
        if max_cycles and len(state["cycles"]) >= max_cycles:
            # Sair: debita custo de saida
            exit_cost_bps = EXIT_COST_BPS
            state["total_net_pnl_bps"] -= exit_cost_bps
            state["total_net_pnl_usd"] -= state["position_usd"] * exit_cost_bps / 10000
            state["status"] = "closed"

            # Veredito final
            cycle_pnls = [c["cycle_pnl_bps"] for c in state["cycles"]]
            log("=" * 80)
            log(f"POSICAO FECHADA apos {len(state['cycles'])} ciclos")
            summarize(f"D55c LINK paper ({len(state['cycles'])} ciclos, "
                      f"apos {ROUNDTRIP_BPS}bps roundtrip)", cycle_pnls)
            log(f"Total net: {state['total_net_pnl_bps']:+.2f}bps "
                f"(${state['total_net_pnl_usd']:+.4f})")
            log("=" * 80)
            save_state(state)
            break

        try:
            bn = binance_mark_price()
            next_funding_ms = bn["nextFundingTime"]

            if next_funding_ms <= 0:
                log("Binance nextFundingTime invalido, esperando...")
                time.sleep(300)
                continue

            now_ms = time.time() * 1000
            bn_hist = [event for event in binance_funding_history(last_bn_funding_time + 1)
                       if event["time"] > last_bn_funding_time]
            if not bn_hist and now_ms < next_funding_ms:
                # Ainda nao chegou o proximo funding da Binance
                sleep_s = (next_funding_ms - now_ms) / 1000 + 30  # +30s margem
                log(f"Aguardando proximo funding Binance em {sleep_s/60:.1f}min "
                    f"(next={datetime.fromtimestamp(next_funding_ms/1000, tz=timezone.utc).isoformat()})")
                time.sleep(min(sleep_s, 3600))  # max 1h sleep
                continue

            # Funding da Binance acabou de acontecer -- coletar dados
            # Buscar funding history da Binance desde o ultimo ciclo
            if not bn_hist:
                log("Sem funding history da Binance, tentando novamente...")
                time.sleep(60)
                continue

            # Ultimo funding rate da Binance
            latest_bn_funding = bn_hist[0]
            bn_funding_rate = latest_bn_funding["rate"]
            cycle_start_ms = last_bn_funding_time + 1
            funding_time_ms = latest_bn_funding["time"]

            # Buscar funding history da HL desde a abertura/settlement anterior.
            hl_hist = hl_funding_history(
                cycle_start_ms,
                int(funding_time_ms + 60 * 1000)
            )
            if not hl_hist:
                log("Sem funding history da Hyperliquid, tentando novamente...")
                time.sleep(60)
                continue
            hl_funding_accum = sum(h["rate"] for h in hl_hist)
            hl_funding_accum_bps = hl_funding_accum * 10000

            # Precos mark atuais
            hl = hl_meta_and_ctxs()
            hl_mark = hl["markPx"] if hl else 0
            bn_mark = bn["markPrice"]

            if hl_mark == 0:
                log("HL mark price invalido, pulando ciclo")
                time.sleep(60)
                continue

            # Settle ciclo
            settle_cycle(state, bn_funding_rate, hl_funding_accum_bps, hl_mark, bn_mark, funding_time_ms)
            last_bn_funding_time = funding_time_ms
            state["last_bn_funding_time_ms"] = last_bn_funding_time
            save_state(state)

            # Report a cada 5 ciclos
            n = len(state["cycles"])
            if n % 5 == 0 and n >= 5:
                cycle_pnls = [c["cycle_pnl_bps"] for c in state["cycles"]]
                log("-" * 60)
                summarize(f"D55c LINK paper (N={n}, parcial)", cycle_pnls)
                log("-" * 60)

        except Exception as e:
            log(f"ERRO: {e}")

        # Esperar antes do proximo ciclo (funding da Binance e a cada 8h)
        time.sleep(300)


if __name__ == "__main__":
    import sys
    position_usd = DEFAULT_POSITION_USD
    max_cycles = DEFAULT_MAX_CYCLES
    for i, arg in enumerate(sys.argv):
        if arg == "--position-usd" and i + 1 < len(sys.argv):
            position_usd = int(sys.argv[i + 1])
        elif arg == "--cycles" and i + 1 < len(sys.argv):
            max_cycles = int(sys.argv[i + 1])
    run_bot(position_usd=position_usd, max_cycles=max_cycles)
