"""
forward_return_tracker.py — helper compartilhado para hipóteses cujos bots só
logavam um signal/contagem de anomalia por ciclo, mas nunca conferiam o que o
preço fez depois. Sem isso, D37 (exchange_outflow_scan.py), D40
(stablecoin_mint_scan.py) e D41 (wash_trading_scan.py) nunca poderiam produzir
um veredito (EV/WR), não importa quanto tempo rodassem — achado do audit de
2026-07-08 (ver docs/state_of_research.md item 37 e
docs/aggressive_hypotheses_report.md UPDATE 2026-07-08).

Padrão de uso (ver os 3 scripts acima para a integração concreta):
    1. A cada ciclo, depois de calcular um sinal, chame `record()` — SEMPRE,
       mesmo com direction=0 (sem sinal), pra ter um grupo de controle.
    2. A cada ciclo, chame `resolve_due()` pra preencher o preço/retorno
       futuro de qualquer leitura passada cujo horizonte já passou.
    3. Periodicamente, chame `report()` pra imprimir um veredito usando o
       mesmo ferramental Wilson/bootstrap (stats_utils.py) do resto do repo.
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


def record(state_file, price, direction, horizons_s, meta=None, max_records=20000):
    """Loga uma leitura. direction: +1 sinal comprado/bullish, -1 sinal
    vendido/bearish, 0 sem sinal (controle). horizons_s: lista de horizontes
    em SEGUNDOS contra os quais esse registro deve ser resolvido depois.
    """
    if price is None:
        return
    records = _load(state_file)
    records.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "price": price,
        "direction": direction,
        "meta": meta or {},
        "horizons_s": horizons_s,
        "resolved": {},
    })
    if len(records) > max_records:
        records = records[-max_records:]
    _save(state_file, records)


def resolve_due(state_file, price_fn):
    """Resolve qualquer registro cujo(s) horizonte(s) já tenham passado.
    price_fn é um callable sem argumentos que retorna o preço atual (ou None
    em caso de falha). Só chama price_fn() uma vez por invocação (cacheado),
    e só se algo estiver de fato vencido.
    """
    records = _load(state_file)
    if not records:
        return
    now = datetime.now(timezone.utc)
    cached_price = None
    dirty = False
    for rec in records:
        ts = datetime.fromisoformat(rec["ts"])
        age_s = (now - ts).total_seconds()
        for h in rec.get("horizons_s", []):
            key = str(h)
            if key in rec["resolved"] or age_s < h:
                continue
            if cached_price is None:
                cached_price = price_fn()
                if cached_price is None:
                    return
            ret_pct = (cached_price - rec["price"]) / rec["price"] * 100 if rec["price"] else None
            rec["resolved"][key] = {"price": cached_price, "return_pct": ret_pct}
            dirty = True
    if dirty:
        _save(state_file, records)


def report(state_file, horizons_s, label_prefix=""):
    """Imprime + retorna um veredito por horizonte: aligned_return (retorno
    bruto * direction) para registros com direction != 0, passado pelo mesmo
    stats_utils.summarize() usado no resto do repo, mais a média do grupo de
    controle (direction==0) para comparação.
    """
    records = _load(state_file)
    out = {}
    for h in horizons_s:
        key = str(h)
        aligned = []
        control = []
        for r in records:
            res = r["resolved"].get(key)
            if not res or res["return_pct"] is None:
                continue
            if r["direction"] == 0:
                control.append(res["return_pct"])
            else:
                aligned.append(res["return_pct"] * r["direction"])
        label = f"{label_prefix} @ {int(h)}s".strip()
        if aligned:
            out[key] = stats_summarize(label, aligned)
        else:
            print(f"\n--- {label} --- N=0 ainda (nenhum sinal resolvido nesse horizonte)")
            out[key] = {"n": 0}
        if control:
            print(f"  [controle, sem sinal] N={len(control)} | retorno médio={sum(control)/len(control):.4f}%")
    return out
