"""
carry_return_tracker.py — tracker para hipóteses delta-neutral (D44) onde o
"forward return" não é retorno direcional de preço, e sim o carry P&L real:
  carry_pnl = basis_reversion + funding_collected - roundtrip_fees

Diferença vs forward_return_tracker.py:
  - Grava funding_rate + basis_pct no momento do sinal (não só preço)
  - No resolve, busca funding_rate ATUAL (não só preço) pra calcular o carry
  - funding_collected = soma das funding rates no período (aproximado: usa
    a funding rate atual * número de períodos de 8h no horizonte)
  - basis_reversion = basis_entry - basis_atual (quanto o basis convergiu)
  - Para SHORT_FUT: carry = basis_reversion + funding_collected - fees
  - Para LONG_FUT: carry = basis_reversion + funding_collected - fees
    (ambos delta-neutral, a direção só afeta o sinal do funding coletado)

Padrão de uso (ver funding_basis_arb_scan.py para a integração concreta):
    1. A cada ciclo, depois de calcular um sinal, chame `record()`.
    2. A cada ciclo, chame `resolve_due()` com um callable que retorna
       (funding_rate, basis_pct) atuais.
    3. Periodicamente, chame `report()` para imprimir o veredito.
"""
import json
import os
from datetime import datetime, timezone

from stats_utils import summarize as stats_summarize


def _load(state_file):
    if not os.path.exists(state_file):
        return []
    try:
        with open(state_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return []


def _save(state_file, records):
    tmp = state_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(records, f, indent=2, default=str)
    os.replace(tmp, state_file)


def record(state_file, signal, funding_rate, basis_pct, price, horizons_s,
           roundtrip_fee_pct=0.12, meta=None, max_records=20000):
    """Loga um sinal delta-neutral. signal: 'LONG_FUT' ou 'SHORT_FUT' ou 'NONE'
    (controle). funding_rate e basis_pct são frações (ex: -0.000382 = -0.0382%).
    roundtrip_fee_pct é em pontos percentuais (ex: 0.12 = 0.12%).
    """
    records = _load(state_file)
    direction = 1 if signal == "LONG_FUT" else (-1 if signal == "SHORT_FUT" else 0)
    records.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "signal": signal,
        "direction": direction,
        "funding_rate": funding_rate,
        "basis_pct": basis_pct,
        "price": price,
        "roundtrip_fee_pct": roundtrip_fee_pct,
        "meta": meta or {},
        "horizons_s": horizons_s,
        "resolved": {},
    })
    if len(records) > max_records:
        records = records[-max_records:]
    _save(state_file, records)


def resolve_due(state_file, market_fn):
    """Resolve registros vencidos. market_fn é um callable sem argumentos que
    retorna (funding_rate_atual, basis_pct_atual) ou None em caso de falha.
    Só chama market_fn() uma vez por invocação (cacheado), e só se algo estiver
    de fato vencido.
    """
    records = _load(state_file)
    if not records:
        return
    now = datetime.now(timezone.utc)
    cached = None
    dirty = False
    for rec in records:
        ts = datetime.fromisoformat(rec["ts"])
        age_s = (now - ts).total_seconds()
        for h in rec.get("horizons_s", []):
            key = str(h)
            if key in rec["resolved"] or age_s < h:
                continue
            if cached is None:
                cached = market_fn()
                if cached is None:
                    return
            cur_funding, cur_basis = cached

            # Basis reversion: quanto o basis convergiu toward 0
            # Para LONG_FUT (basis era negativo): reversion = basis_entry - cur_basis
            #   (se basis subiu toward 0, cur_basis > basis_entry, reversion > 0)
            # Para SHORT_FUT (basis era positivo): reversion = cur_basis - basis_entry
            #   (se basis caiu toward 0, cur_basis < basis_entry, reversion > 0)
            # Mas como direction já codifica isso, podemos usar:
            #   reversion = -direction * (cur_basis - basis_entry)
            #   LONG_FUT (dir=+1, basis<0): reversion = -(cur - entry) = entry - cur > 0 se convergiu
            #   SHORT_FUT (dir=-1, basis>0): reversion = (cur - entry) < 0 se convergiu... wait
            # Mais simples: reversion é sempre |basis_entry| - |cur_basis| se convergiu
            basis_entry = rec["basis_pct"]
            basis_reversion = abs(basis_entry) - abs(cur_basis)

            # Funding coletado: funding_rate * número de períodos de 8h no horizonte
            # Para LONG_FUT: coleta quando funding < 0 (shorts pagam longs)
            # Para SHORT_FUT: coleta quando funding > 0 (longs pagam shorts)
            # Aproximação: usa funding_rate atual como proxy do período médio
            n_periods = h / (8 * 3600)  # número de períodos de 8h
            if rec["direction"] > 0:  # LONG_FUT
                funding_collected = abs(min(cur_funding, 0)) * n_periods * 100  # pct
            elif rec["direction"] < 0:  # SHORT_FUT
                funding_collected = abs(max(cur_funding, 0)) * n_periods * 100  # pct
            else:
                funding_collected = 0

            fees = rec["roundtrip_fee_pct"]
            carry_pnl = basis_reversion + funding_collected - fees

            rec["resolved"][key] = {
                "cur_funding": cur_funding,
                "cur_basis": cur_basis,
                "basis_reversion": basis_reversion,
                "funding_collected_pct": funding_collected,
                "fees_pct": fees,
                "carry_pnl_pct": carry_pnl,
            }
            dirty = True
    if dirty:
        _save(state_file, records)


def report(state_file, horizons_s, label_prefix=""):
    """Imprime + retorna um veredito por horizonte: carry_pnl_pct para registros
    com signal != NONE, passado pelo stats_utils.summarize(), mais a média do
    grupo de controle (signal==NONE) para comparação.
    """
    records = _load(state_file)
    out = {}
    for h in horizons_s:
        key = str(h)
        active = []
        control = []
        for r in records:
            res = r["resolved"].get(key)
            if not res:
                continue
            if r["direction"] == 0:
                control.append(res["carry_pnl_pct"])
            else:
                active.append(res["carry_pnl_pct"])
        label = f"{label_prefix} @ {int(h/3600)}h".strip()
        if active:
            out[key] = stats_summarize(label, active)
        else:
            print(f"\n--- {label} --- N=0 ainda (nenhum sinal resolvido nesse horizonte)")
            out[key] = {"n": 0}
        if control:
            print(f"  [controle, sem sinal] N={len(control)} | carry médio={sum(control)/len(control):.4f}%")
    return out
