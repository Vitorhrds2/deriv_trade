import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getHftStatus, getHftTrades, isHftLive } from "@/lib/hft-api";
import { fmtMoney } from "@/lib/format";
import { getActiveResearchBots, hypStatusBadgeClass } from "@/lib/hypotheses-data";
import { useApp } from "@/lib/store";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Terminal } from "lucide-react";

export const Route = createFileRoute("/bots")({
  head: () => ({ meta: [{ title: "Bot Orchestrator — TradeLab OS" }] }),
  component: BotsPage,
});

// trading-engine/*.py fora dos scripts com sessao tmux ativa hoje na EC2 (hft_arbitrage_bot.py,
// status_api.py, unlock_short_bot.py, e os bots de validacao listados abaixo via
// getActiveResearchBots()). Contagem real do repo verificada em 2026-07-06 (scripts historicos,
// testados uma vez ou em standby), atualizar se o inventario mudar:
// find trading-engine -maxdepth 1 -name "*.py" -type f | wc -l
const OTHER_SCRIPTS_COUNT = 167;

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
  const isLive = status ? isHftLive(status) : false;
  const activeBots = getActiveResearchBots();
  const selectHyp = useApp((s) => s.selectHyp);

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › bot orchestrator"
        title="Bot Orchestrator"
        description={`Status real do hft_bot (AWS) via API dedicada na EC2 — detalhe completo abaixo. Há mais ${activeBots.length} bots de validação de hipótese rodando na mesma instância, listados abaixo. Deploy é manual (scp + tmux) para todos.`}
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
          label="hft_bot"
          value={isLive ? "rodando" : "parado"}
          tone={isLive ? "pos" : "neutral"}
          hint={`+${activeBots.length} outros bots na mesma EC2, ver abaixo`}
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

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
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
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  downtime golden hour (hoje)
                </Mono>
                <div
                  className={`mt-1 font-mono ${status && status.goldenHourDowntime.secondsToday > 0 ? "text-warning" : "text-muted-foreground"}`}
                >
                  {status ? `${Math.round(status.goldenHourDowntime.secondsToday)}s` : "—"}
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
          title={
            <div className="flex items-center gap-2">
              Bot Fleet — hipóteses em validação ativa
              <Mono className="text-muted-foreground">({activeBots.length} rodando)</Mono>
            </div>
          }
          subtitle="sessão tmux ativa na mesma EC2 agora, sem API de status dedicada ainda — clique para ver o veredito completo"
        >
          <div className="divide-y divide-border/60">
            {activeBots.map((h) => (
              <Link
                key={h.id}
                to="/hypotheses"
                onClick={() => selectHyp(h.id)}
                className="px-4 py-3 flex items-start gap-3 hover:bg-muted/30 transition-colors group"
              >
                <Dot tone="warn" className="mt-1.5 animate-pulse shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Mono className="text-muted-foreground text-[11px]">{h.id}</Mono>
                    <span className="text-sm font-medium group-hover:text-primary transition-colors">
                      {h.title}
                    </span>
                    <Badge variant="outline" className={`${hypStatusBadgeClass(h.status)} text-[10px] font-mono uppercase ml-auto shrink-0`}>
                      {h.status}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 flex items-center gap-2">
                    <Terminal className="h-3 w-3 shrink-0" />
                    <Mono className="truncate">{h.author}</Mono>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1.5 line-clamp-1">{h.verdict}</p>
                </div>
              </Link>
            ))}
            {activeBots.length === 0 && (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                Nenhum bot em validação ativa no momento.
              </div>
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
            testados uma vez (veredito fechado, ver <Link to="/hypotheses" className="underline hover:text-primary">Hypothesis Engine</Link>) ou em standby, sem sessão tmux ativa
            hoje. Deploy é manual (scp + tmux); orquestração automática de fleet ainda não existe.
          </div>
        </Panel>
      </div>
    </div>
  );
}
