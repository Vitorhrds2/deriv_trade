import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { getHftStatus, getHftTrades } from "@/lib/hft-api";
import { fmtMoney } from "@/lib/mock-data";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Terminal } from "lucide-react";

export const Route = createFileRoute("/bots")({
  head: () => ({ meta: [{ title: "Bot Orchestrator — TradeLab OS" }] }),
  component: BotsPage,
});

// trading-engine/*.py fora dos 2 arquivos ativos hoje (hft_arbitrage_bot.py, status_api.py):
// variantes de oracle_diff_bot, straddle/forex/scalper exploits, rng_smoothing_exploit etc.
// Contagem real do repo (nao deployados / sem tmux ativo), atualizar se o inventario mudar.
const OTHER_SCRIPTS_COUNT = 60;

function BotsPage() {
  const statusQuery = useQuery({
    queryKey: ["hft-status"],
    queryFn: () => getHftStatus(),
    refetchInterval: 5000,
  });
  const tradesQuery = useQuery({
    queryKey: ["hft-trades"],
    queryFn: () => getHftTrades(),
    refetchInterval: 5000,
  });

  const status = statusQuery.data;
  const trades = tradesQuery.data;
  const isLive = !!status?.connected && status.tmuxSessionAlive && !status.logStale;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › bot orchestrator"
        title="Bot Orchestrator"
        description="Status real do único bot em produção (hft_bot, AWS) via API na EC2. Sem frota multi-broker fake — deploy hoje é manual (scp + tmux)."
        actions={
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => {
              statusQuery.refetch();
              tradesQuery.refetch();
            }}
          >
            <RefreshCw
              className={`h-4 w-4 ${statusQuery.isFetching || tradesQuery.isFetching ? "animate-spin" : ""}`}
            />
            Atualizar
          </Button>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat
          label="Bots em execução"
          value={isLive ? 1 : 0}
          tone={isLive ? "pos" : "neutral"}
          hint="hft_bot · AWS"
        />
        <Stat label="Trades hoje (total)" value={trades?.total.n ?? "—"} hint="ALIGNED + ANTI" />
        <Stat
          label="PnL real acumulado"
          value={trades ? fmtMoney(trades.total.pnlTotal) : "—"}
          tone={trades && trades.total.pnlTotal < 0 ? "neg" : "neutral"}
        />
        <Stat
          label="Scripts não deployados"
          value={OTHER_SCRIPTS_COUNT}
          hint="trading-engine/*.py, histórico"
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          className="col-span-12 xl:col-span-7"
          title="hft_bot"
          subtitle="AWS 18.199.174.178 · tmux `hft_bot` · V6.2 Ultra-Momentum + shadow A/B"
        >
          <div className="p-4 space-y-4">
            <div className="flex items-center gap-2 text-sm">
              <Dot
                tone={!status ? "muted" : isLive ? "pos" : "neg"}
                className={isLive ? "animate-pulse" : ""}
              />
              <span className="font-medium">
                {!status
                  ? "carregando…"
                  : !status.connected
                    ? "API de status inacessível"
                    : isLive
                      ? "rodando"
                      : status.tmuxSessionAlive
                        ? "sessão tmux ativa, sem heartbeat recente"
                        : "parado"}
              </span>
              {status?.error && (
                <span className="text-xs text-muted-foreground">({status.error})</span>
              )}
              {status?.logAgeSeconds != null && (
                <span className="text-xs text-muted-foreground ml-auto">
                  log há {Math.round(status.logAgeSeconds)}s
                </span>
              )}
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  total (n)
                </Mono>
                <div className="mt-1 font-mono">{trades?.total.n ?? "—"}</div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  win rate
                </Mono>
                <div className="mt-1 font-mono">
                  {trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"}
                </div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  pnl total
                </Mono>
                <div
                  className={`mt-1 font-mono ${trades && trades.total.pnlTotal < 0 ? "text-neg" : "text-muted-foreground"}`}
                >
                  {trades ? fmtMoney(trades.total.pnlTotal) : "—"}
                </div>
              </div>
            </div>

            <div>
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                shadow a/b — aligned vs anti
              </Mono>
              <div className="grid grid-cols-2 gap-3 mt-2">
                <div className="rounded border p-3">
                  <div className="text-[11px] text-muted-foreground">ALIGNED</div>
                  <div className="font-mono text-sm mt-1">
                    N={trades?.aligned.n ?? 0} · {trades ? fmtMoney(trades.aligned.pnlTotal) : "—"}
                  </div>
                </div>
                <div className="rounded border p-3">
                  <div className="text-[11px] text-muted-foreground">ANTI</div>
                  <div className="font-mono text-sm mt-1">
                    N={trades?.anti.n ?? 0} · {trades ? fmtMoney(trades.anti.pnlTotal) : "—"}
                  </div>
                </div>
              </div>
              {trades && trades.anti.n === 0 && (
                <p className="text-[11px] text-muted-foreground mt-2">
                  Amostra ANTI ainda vazia — shadow A/B ativado em 2026-07-01; sinal é raro
                  (restrito ao horário de ouro 12-18 UTC).
                </p>
              )}
            </div>
          </div>
        </Panel>

        <Panel
          className="col-span-12 xl:col-span-5"
          title={
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4" />
              Log ao vivo
            </div>
          }
          subtitle="últimas linhas de hft_trades.log (EC2, via status_api)"
        >
          <div className="font-mono text-[11px] max-h-[440px] overflow-auto bg-background/30">
            {!status || status.recentLogLines.length === 0 ? (
              <div className="px-4 py-10 text-center text-xs text-muted-foreground">
                {status?.connected === false
                  ? "API de status inacessível no momento."
                  : "Sem linhas recentes."}
              </div>
            ) : (
              status.recentLogLines
                .slice()
                .reverse()
                .map((line, i) => (
                  <div
                    key={i}
                    className={`px-4 py-1.5 border-b border-border/30 truncate ${
                      line.includes("ERROR")
                        ? "text-destructive"
                        : line.includes("✅")
                          ? "text-success"
                          : "text-foreground/80"
                    }`}
                  >
                    {line}
                  </div>
                ))
            )}
          </div>
        </Panel>

        <Panel
          className="col-span-12"
          title="Outros scripts do repo"
          subtitle="não deployados / sem execução ativa no momento"
        >
          <div className="px-4 py-6 text-sm text-muted-foreground">
            {OTHER_SCRIPTS_COUNT}+ scripts exploratórios em <Mono>trading-engine/</Mono> (variantes
            de <Mono>oracle_diff_bot</Mono>, <Mono>straddle_multiplier_exploit</Mono>,{" "}
            <Mono>forex_imbalance_exploit</Mono>, <Mono>rng_smoothing_exploit</Mono>, etc.) —
            testados em algum momento ou em standby, nenhum com sessão tmux ativa hoje. Deploy é
            manual (scp + tmux); orquestração automática de fleet ainda não existe.
          </div>
        </Panel>
      </div>
    </div>
  );
}
