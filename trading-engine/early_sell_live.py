"""Early Sell Optionality -- EXECUTOR AO VIVO (capital real ou demo).

*** RE-REFUTADO em 2026-07-07 -- NAO USAR COM --live ***
A hipotese que este executor implementa foi RE-REFUTADA depois de corrigir um bug de
hindsight bias em early_sell_multi.py/early_sell_test.py (o "edge" media max(bid) sobre
toda a vida do contrato, que e trivialmente >= hold para qualquer preco com ruido --
nao evidencia de mispricing real). Comparacao pareada correta em N=550 (10 simbolos):
diff EV cruza zero em 7/8 thresholds e e SIGNIFICATIVAMENTE NEGATIVO no 8o. Ver
docs/state_of_research.md item 14 e hypotheses-data.ts (HYP-SELL-01, status=refuted).
Por isso a flag --live aborta incondicionalmente logo abaixo ate nova validacao real.

Diferenca fundamental para early_sell_multi.py (script de PESQUISA): aquele script so
OBSERVA (compra, espera o contrato expirar, registra o melhor bid que teria dado para
vender) -- nunca chama "sell" de verdade. Este arquivo EXECUTA: monitora bid_price/
buy_price em tempo real e vende de fato assim que o ratio configurado e atingido.

Deliberadamente AUTOCONTIDO (nao importa de early_sell_multi.py): um bot de dinheiro
real nao deve depender de um script de pesquisa que pode ser editado/experimentado
(ex: alguem muda DEFAULT_MATRIX de early_sell_multi.py para um novo sweep e sem querer
muda tambem o universo de simbolos deste executor). LIVE_MATRIX abaixo e uma copia
congelada dos 10 pares (symbol, contract_type) que PARECIAM validados (N=13-50 cada,
diff_ev CI95 > 0 em TODOS) mas essa metrica tinha o bug de hindsight descrito acima --
ver aviso no topo do arquivo antes de reativar --live.

MODELO DE SEGURANCA (defesa em profundidade, ver tambem risk_guardrails.py):
  1. Por padrao roda em DEMO (use_demo=True). So opera com dinheiro real se a flag
     --live for passada EXPLICITAMENTE na linha de comando.
  2. --live exige AMBOS: env var CONFIRM_REAL_MONEY=YES E env var DERIV_API_TOKEN_REAL
     preenchidos. Falta de qualquer um -> aborta antes de conectar (nao tenta "cair
     para demo" silenciosamente).
  3. Apos conectar, valida via API que a conta conectada e REAL (nao demo) quando
     --live, ou DEMO quando sem --live -- aborta se nao bater (mesmo padrao ja usado
     em early_sell_multi.validate_demo, so que bidirecional aqui).
  4. stake <= max_loss_per_trade e forcado por assert antes de conectar. Para
     Rise/Fall (CALL/PUT), a perda maxima de um trade e o proprio stake (contrato
     binario, sem chamada de margem) -- entao isso basta para garantir o cap por trade.
  5. GuardRail (risk_guardrails.py) impoe cap de perda DIARIA (pausa novas entradas,
     reseta 00:00 UTC) e um circuit breaker de DRAWDOWN CUMULATIVO (para o processo
     inteiro, exige reset manual via `python risk_guardrails.py early_sell --reset-halt`).

CONCORRENCIA: dado o capital tipicamente alocado por estrategia neste estagio (ex:
$10 = 1x stake), so faz sentido manter NO MAXIMO 1 posicao aberta por vez -- por isso
o loop principal e SEQUENCIAL (round-robin pelos 10 pares validados, um trade de cada
vez), diferente de early_sell_multi.py que roda os 10 streams em paralelo (esse sim
adequado para pesquisa, onde o objetivo e acumular amostra rapido, nao gerir risco de
capital real). Para aumentar concorrencia real basta aumentar o capital alocado e
rodar multiplas instancias deste script (uma por posicao desejada), cada uma
respeitando o MESMO GuardRail compartilhado (mesmo strategy_name="early_sell").

Alertas por trade via Telegram (telegram_alerts.py) -- ver .env.example para setup.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)

from deriv_client import DerivClient
from risk_guardrails import GuardRail
from telegram_alerts import send_telegram

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_live_results.jsonl")

# Copia congelada dos 10 pares validados em early_sell_multi.py / early_sell_test.py.
# NAO sincronizar automaticamente com o script de pesquisa -- ver docstring do modulo.
LIVE_MATRIX = [
    ("1HZ10V", "PUT"),
    ("1HZ25V", "CALL"),
    ("1HZ50V", "CALL"),
    ("1HZ75V", "CALL"),
    ("1HZ100V", "CALL"),
    ("R_10", "CALL"),
    ("R_25", "CALL"),
    ("R_50", "CALL"),
    ("R_75", "CALL"),
    ("R_100", "CALL"),
]


async def validate_account(client, api_token, app_id, expect_demo):
    """Confirma via API (nao so pelo que pedimos na conexao) que a conta conectada e
    do tipo esperado. Espelha validate_demo() de early_sell_multi.py, generalizado
    para tambem validar conta REAL quando expect_demo=False."""
    import urllib.request as _u

    def _fetch():
        req = _u.Request("https://api.derivws.com/trading/v1/options/accounts")
        req.add_header("Authorization", f"Bearer {api_token}")
        req.add_header("Deriv-App-ID", str(app_id))
        with _u.urlopen(req) as r:
            return json.loads(r.read().decode())

    accs = (await asyncio.get_running_loop().run_in_executor(None, _fetch)).get("data", [])
    demo_ids = [a["account_id"] for a in accs if a.get("account_type") == "demo"]
    real_ids = [a["account_id"] for a in accs if a.get("account_type") != "demo"]
    connected = client.account_id
    ok = (connected in demo_ids) if expect_demo else (connected in real_ids and connected not in demo_ids)
    kind = "DEMO" if expect_demo else "REAL"
    print(f"Conta conectada: {connected} | demo={demo_ids} | real={real_ids} -> "
          f"{'OK ' + kind if ok else 'NAO ' + kind + '!'}", flush=True)
    return ok


async def poll_open_contract(client, cid, retries=6):
    """proposal_open_contract com retry em WS drop (o contrato sobrevive no lado do
    servidor Deriv independente da nossa conexao)."""
    for attempt in range(retries):
        try:
            poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
            if isinstance(poc, dict) and "error" in poc:
                await asyncio.sleep(2)
                continue
            return poc.get("proposal_open_contract", {})
        except Exception:
            await asyncio.sleep(min(2 * (attempt + 1), 10))
    return {}


async def run_trial_live(client, symbol, contract_type, stake, duration, duration_unit,
                          ratio_threshold, tag):
    """Compra 1 contrato e monitora bid_price/buy_price em tempo real. Vende de fato
    (ordem real, price=0 = aceita o preco de mercado atual, garante execucao) assim que
    o ratio configurado e atingido pela primeira vez (regra non-hindsight, identica em
    espirito a rule_by_ratio de early_sell_multi.py, so que EXECUTADA e nao so medida).
    Se o ratio nunca for atingido, o contrato e deixado expirar naturalmente (hold)."""
    buy_res = None
    for attempt in range(5):
        try:
            buy_res = await client.send_request({
                "buy": 1, "price": stake,
                "parameters": {
                    "amount": stake, "basis": "stake", "contract_type": contract_type,
                    "currency": "USD", "underlying_symbol": symbol,
                    "duration": duration, "duration_unit": duration_unit,
                }
            })
            break
        except Exception as e:
            print(f"  [{tag}] BUY exception (tentativa {attempt + 1}): {e}", flush=True)
            await asyncio.sleep(3)

    if not buy_res or "error" in buy_res:
        msg = buy_res["error"].get("message", "") if buy_res and "error" in buy_res else "sem resposta"
        print(f"  [{tag}] BUY erro: {msg}", flush=True)
        return None

    b = buy_res["buy"]
    cid = b["contract_id"]
    buy_price = float(b.get("buy_price", 0))
    entry_spot = float(b.get("current_spot", 0))
    payout = float(b.get("payout", 0))

    total_secs = duration * 60 if duration_unit == "m" else duration
    sample_interval = max(5, total_secs // 60)
    n_samples = total_secs // sample_interval + 5

    action = "held_to_expiry"
    exit_bid = None
    profit = None

    for _ in range(n_samples):
        c = await poll_open_contract(client, cid)
        if c.get("is_sold"):
            profit = float(c.get("profit", 0) or 0)
            break

        bid_price = float(c.get("bid_price", 0) or 0)
        is_valid_sell = bool(c.get("is_valid_to_sell", False))

        if is_valid_sell and bid_price > 0 and buy_price > 0 and (bid_price / buy_price) >= ratio_threshold:
            sell_res = await client.sell_contract(cid, price=0)
            if sell_res and "error" not in sell_res:
                s = sell_res["sell"]
                sold_for = float(s.get("sold_for", bid_price))
                profit = sold_for - buy_price
                action = "sold_early"
                exit_bid = bid_price
                break
            else:
                msg = sell_res.get("error", {}).get("message", "") if sell_res else "sem resposta"
                print(f"  [{tag}] SELL erro (retry no proximo poll): {msg}", flush=True)

        await asyncio.sleep(sample_interval)

    if profit is None:
        final = await poll_open_contract(client, cid)
        profit = float(final.get("profit", 0) or 0)

    won = profit > 0
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "contract_type": contract_type, "stake": stake,
        "duration": duration, "duration_unit": duration_unit,
        "contract_id": cid, "buy_price": buy_price, "payout": payout,
        "entry_spot": entry_spot, "ratio_threshold": ratio_threshold,
        "action": action, "exit_bid": exit_bid,
        "profit": profit, "won": won,
    }


async def main():
    ap = argparse.ArgumentParser(description="Early Sell Optionality -- EXECUCAO AO VIVO (real ou demo)")
    ap.add_argument("--live", action="store_true",
                     help="Opera com DINHEIRO REAL. Exige CONFIRM_REAL_MONEY=YES e "
                          "DERIV_API_TOKEN_REAL no .env. Sem esta flag, roda em DEMO.")
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--duration", type=int, default=15)
    ap.add_argument("--duration-unit", default="m")
    ap.add_argument("--ratio-threshold", type=float, default=1.3,
                     help="Vende assim que bid_price/buy_price >= ratio. Default 1.3 "
                          "(= regra $13 num stake $10, dentro da faixa $11-18 confirmada "
                          "em N=50 e generalizada em 10 simbolos, N=13 cada, todas CI95>0).")
    ap.add_argument("--cooldown-s", type=float, default=5.0)
    ap.add_argument("--max-loss-per-trade", type=float, default=10.0)
    ap.add_argument("--max-daily-loss", type=float, default=10.0)
    ap.add_argument("--max-cumulative-loss", type=float, default=30.0,
                     help="Circuit breaker permanente (3x o cap diario). Exige "
                          "`python risk_guardrails.py early_sell --reset-halt` manual para religar.")
    ap.add_argument("--max-trials", type=int, default=None,
                     help="None = roda indefinidamente (padrao do ecossistema: tmux + loop infinito)")
    args = ap.parse_args()

    if args.stake > args.max_loss_per_trade:
        print(f"ERRO: stake (${args.stake}) > max_loss_per_trade (${args.max_loss_per_trade}). "
              "Rise/Fall perde no maximo o stake -- ajuste um dos dois. Abortando.", flush=True)
        return

    if args.live:
        print("ERRO: hipotese RE-REFUTADA em 2026-07-07 (bug de hindsight bias corrigido, "
              "diff EV cruza zero/negativo em N=550 -- ver docstring deste arquivo e "
              "docs/state_of_research.md item 14). --live desabilitado ate nova validacao "
              "real com metrica pareada correta. Abortando.", flush=True)
        return
        if os.getenv("CONFIRM_REAL_MONEY", "").strip().upper() != "YES":
            print("ERRO: --live exige CONFIRM_REAL_MONEY=YES no .env. Abortando por seguranca.", flush=True)
            return
        api_token = os.getenv("DERIV_API_TOKEN_REAL")
        if not api_token:
            print("ERRO: --live exige DERIV_API_TOKEN_REAL no .env (token gerado na "
                  "CONTA REAL em app.deriv.com/account/api-token). Abortando.", flush=True)
            return
    else:
        api_token = os.getenv("DERIV_API_TOKEN")

    app_id = os.getenv("DERIV_APP_ID")
    if not api_token or not app_id:
        print("ERRO: token/app_id nao encontrados no .env.", flush=True)
        return

    mode = "LIVE (DINHEIRO REAL)" if args.live else "DEMO"
    print("=" * 90, flush=True)
    print(f"Early Sell Optionality -- EXECUCAO AO VIVO [{mode}]", flush=True)
    print(f"stake=${args.stake} ratio_threshold={args.ratio_threshold} duration={args.duration}{args.duration_unit} "
          f"max_loss/trade=${args.max_loss_per_trade} max_daily=${args.max_daily_loss} "
          f"max_cumulative=${args.max_cumulative_loss}", flush=True)
    print(f"universo ({len(LIVE_MATRIX)} pares, round-robin sequencial): {LIVE_MATRIX}", flush=True)
    print("=" * 90, flush=True)

    client = DerivClient(app_id=app_id, api_token=api_token, use_demo=not args.live)
    await client.connect()
    ok = await validate_account(client, api_token, app_id, expect_demo=not args.live)
    if not ok:
        print(f">>> TRAVA: conta nao e {'DEMO' if not args.live else 'REAL'}. ABORTANDO.", flush=True)
        await client.disconnect()
        return

    guard = GuardRail("early_sell", args.max_loss_per_trade, args.max_daily_loss, args.max_cumulative_loss)
    can, reason = guard.can_trade()
    if not can:
        print(f">>> GuardRail ja bloqueado ao iniciar: {reason}", flush=True)
        send_telegram(f"\u26A0\uFE0F Early Sell [{mode}] nao iniciou -- guardrail bloqueado: {reason}")
        await client.disconnect()
        return

    send_telegram(f"\U0001F7E2 Early Sell Optionality iniciado [{mode}] "
                   f"stake=${args.stake} ratio={args.ratio_threshold} "
                   f"max_daily=${args.max_daily_loss} max_cumulative=${args.max_cumulative_loss}")

    i = 0
    matrix_i = 0
    try:
        while args.max_trials is None or i < args.max_trials:
            can, reason = guard.can_trade()
            if not can:
                print(f">>> PAUSADO: {reason}", flush=True)
                await asyncio.sleep(60)
                continue

            symbol, contract_type = LIVE_MATRIX[matrix_i % len(LIVE_MATRIX)]
            matrix_i += 1
            tag = f"{symbol}:{contract_type}"

            try:
                rec = await run_trial_live(client, symbol, contract_type, args.stake,
                                            args.duration, args.duration_unit,
                                            args.ratio_threshold, tag)
            except Exception as e:
                print(f"  [{tag}] trial exception: {e} -- retry em 5s", flush=True)
                await asyncio.sleep(5)
                continue

            if rec:
                daily_halt, cumulative_halt = guard.record_trade(rec["profit"])
                with open(RESULTS_FILE, "a") as f:
                    f.write(json.dumps(rec) + "\n")

                emoji = "\u2705" if rec["won"] else "\u274C"
                print(f"  [{tag}] #{i} {rec['action']} profit=${rec['profit']:+.4f} "
                      f"dia=${guard.state['daily_pnl']:+.2f} acum=${guard.state['cumulative_pnl']:+.2f}",
                      flush=True)
                send_telegram(
                    f"{emoji} [{mode}] {tag} {rec['action']} profit=${rec['profit']:+.2f} | "
                    f"dia=${guard.state['daily_pnl']:+.2f} | acumulado=${guard.state['cumulative_pnl']:+.2f}"
                )

                if daily_halt:
                    send_telegram(f"\u26A0\uFE0F Cap diario atingido (${guard.state['daily_pnl']:.2f}). "
                                   "Pausando novas entradas ate reset 00:00 UTC.")
                if cumulative_halt:
                    send_telegram(f"\U0001F6D1 CIRCUIT BREAKER: drawdown cumulativo "
                                   f"${guard.state['cumulative_pnl']:.2f}. Bot PARADO. Requer revisao "
                                   "manual (`python risk_guardrails.py early_sell --reset-halt`).")
                    print(">>> CIRCUIT BREAKER CUMULATIVO ATIVADO. Encerrando processo.", flush=True)
                    break
                i += 1
            await asyncio.sleep(args.cooldown_s)
    finally:
        send_telegram(f"\U0001F534 Early Sell Optionality [{mode}] encerrado "
                       f"(trades={i}, dia=${guard.state['daily_pnl']:+.2f}, "
                       f"acumulado=${guard.state['cumulative_pnl']:+.2f})")
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
