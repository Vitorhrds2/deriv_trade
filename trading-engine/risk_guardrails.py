"""Guardrails de risco reutilizaveis para bots de CAPITAL REAL.

Tres camadas de protecao, cada uma independente:
  1. max_loss_per_trade: apenas documentacional/assert aqui -- a garantia real vem do
     tipo de contrato (Rise/Fall e binarios em geral tem perda maxima = stake por
     construcao). O chamador deve garantir stake <= max_loss_per_trade antes de operar.
  2. max_daily_loss: pausa NOVAS entradas quando o PnL realizado do dia (UTC) atinge
     o limite. Reseta automaticamente a meia-noite UTC. Nao fecha posicoes ja abertas
     a forca -- apenas bloqueia novas.
  3. max_cumulative_loss: circuit breaker permanente (nao reseta sozinho) quando o PnL
     acumulado (todos os dias) atinge o limite. Exige reset_cumulative_halt() manual
     (humano) para religar -- fail-safe contra um bug/edge que na verdade nao existe.

Estado persistido em JSON (guardrail_state_<strategy_name>.json, no mesmo diretorio
deste arquivo) -- sobrevive a restart do processo/instancia. Escrita atomica (tmp +
os.replace) para nao corromper o arquivo se o processo morrer no meio do write.

Uma instancia == uma estrategia (strategy_name vira o nome do arquivo de estado), entao
o mesmo modulo serve para early_sell_live.py, um futuro d17_live.py, etc., cada um com
seu proprio orcamento e sem interferencia entre si.
"""
import json
import os
import threading
from datetime import datetime, timezone

STATE_DIR = os.path.dirname(os.path.abspath(__file__))


class GuardRail:
    def __init__(self, strategy_name, max_loss_per_trade, max_daily_loss,
                 max_cumulative_loss, state_dir=STATE_DIR):
        self.strategy_name = strategy_name
        self.max_loss_per_trade = max_loss_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_cumulative_loss = max_cumulative_loss
        self.state_path = os.path.join(state_dir, f"guardrail_state_{strategy_name}.json")
        self._lock = threading.Lock()
        self.state = self._load()

    @staticmethod
    def _today():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self):
        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                st = json.load(f)
        else:
            st = {}
        st.setdefault("date", self._today())
        st.setdefault("daily_pnl", 0.0)
        st.setdefault("daily_trades", 0)
        st.setdefault("cumulative_pnl", 0.0)
        st.setdefault("total_trades", 0)
        st.setdefault("halted_cumulative", False)
        st.setdefault("halt_reason", None)
        self.state = st
        self._roll_day_if_needed()
        self._save()
        return self.state

    def _save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, self.state_path)

    def _roll_day_if_needed(self):
        today = self._today()
        if self.state["date"] != today:
            self.state["date"] = today
            self.state["daily_pnl"] = 0.0
            self.state["daily_trades"] = 0

    def can_trade(self):
        """Retorna (bool pode_operar, str motivo_se_nao)."""
        with self._lock:
            self._roll_day_if_needed()
            self._save()
            if self.state["halted_cumulative"]:
                return False, f"HALT CUMULATIVO ATIVO: {self.state['halt_reason']}"
            if self.max_daily_loss > 0 and self.state["daily_pnl"] <= -abs(self.max_daily_loss):
                return False, (f"cap diario atingido (${self.state['daily_pnl']:.2f} <= "
                                f"-${self.max_daily_loss:.2f}), aguardando reset 00:00 UTC")
            return True, None

    def record_trade(self, pnl):
        """Atualiza PnL diario/acumulado apos um trade fechar. Retorna
        (daily_halt_novo, cumulative_halt_novo) -- True apenas no ciclo em que o limite
        e cruzado pela primeira vez (para o chamador so alertar uma vez, nao a cada poll)."""
        with self._lock:
            self._roll_day_if_needed()

            was_daily_halted = (self.max_daily_loss > 0 and
                                 self.state["daily_pnl"] <= -abs(self.max_daily_loss))

            self.state["daily_pnl"] += pnl
            self.state["daily_trades"] += 1
            self.state["cumulative_pnl"] += pnl
            self.state["total_trades"] += 1

            daily_halt_now = (self.max_daily_loss > 0 and
                               self.state["daily_pnl"] <= -abs(self.max_daily_loss))
            cumulative_halt_now = (self.max_cumulative_loss > 0 and
                                    self.state["cumulative_pnl"] <= -abs(self.max_cumulative_loss))

            newly_cumulative = cumulative_halt_now and not self.state["halted_cumulative"]
            if newly_cumulative:
                self.state["halted_cumulative"] = True
                self.state["halt_reason"] = (
                    f"drawdown cumulativo ${self.state['cumulative_pnl']:.2f} <= "
                    f"-${self.max_cumulative_loss:.2f}"
                )

            self._save()
            return (daily_halt_now and not was_daily_halted, newly_cumulative)

    def reset_cumulative_halt(self):
        """Reset MANUAL (humano) do circuit breaker cumulativo. Nao mexe no cap diario
        (esse ja reseta sozinho a meia-noite UTC)."""
        with self._lock:
            self.state["halted_cumulative"] = False
            self.state["halt_reason"] = None
            self._save()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Utilitario de linha de comando para guardrails")
    ap.add_argument("strategy_name")
    ap.add_argument("--reset-halt", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    g = GuardRail(args.strategy_name, max_loss_per_trade=10, max_daily_loss=10, max_cumulative_loss=30)
    if args.reset_halt:
        g.reset_cumulative_halt()
        print(f"Circuit breaker de '{args.strategy_name}' resetado.")
    if args.show or not args.reset_halt:
        print(json.dumps(g.state, indent=2))
