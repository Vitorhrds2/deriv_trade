import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { getHftStatus } from "@/lib/hft-api";
import { useQuery } from "@tanstack/react-query";
import { Plug } from "lucide-react";

export const Route = createFileRoute("/brokers")({
  head: () => ({ meta: [{ title: "Brokers — TradeLab OS" }] }),
  component: BrokersPage,
});

type RealConn = { name: string; role: string; note: string };

const REAL_FEEDS: RealConn[] = [
  {
    name: "Binance",
    role: "Feed de preço (read-only)",
    note: "38.74% do peso no índice sintético",
  },
  {
    name: "Coinbase",
    role: "Feed de preço (read-only)",
    note: "53.38% do peso no índice sintético",
  },
  { name: "Kraken", role: "Feed de preço (read-only)", note: "2.66% do peso no índice sintético" },
];

function BrokersPage() {
  const statusQuery = useQuery({
    queryKey: ["hft-status"],
    queryFn: () => getHftStatus(),
    refetchInterval: 5000,
  });
  const status = statusQuery.data;
  const isLive = !!status?.connected && status.tmuxSessionAlive && !status.logStale;
  // As 3 feeds so alimentam o indice sintetico que o hft_bot consome -- nao ha healthcheck
  // por-exchange exposto pela API hoje, entao o status delas e inferido do estado geral do
  // bot (se o bot esta vivo e sem heartbeat travado, as 3 conexoes downstream estao de pe).
  const feedsConnected = isLive;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › brokers"
        title="Broker Connections"
        description="1 corretora real (Deriv) + 3 feeds de preço read-only usados pelo hft_bot. Sem multi-broker fake — outras integrações ainda não existem."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Corretoras" value={1} hint="Deriv (conta demo)" />
        <Stat label="Feeds de preço" value={REAL_FEEDS.length} hint="Binance, Coinbase, Kraken" />
        <Stat
          label="Status agregado"
          value={statusQuery.isLoading ? "…" : isLive ? "conectado" : "instável/parado"}
          tone={statusQuery.isLoading ? "neutral" : isLive ? "pos" : "neg"}
        />
        <Stat label="Outras integrações" value={0} hint="não implementadas" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          className="col-span-12 xl:col-span-7"
          title="Conexões reais"
          subtitle="Deriv + feeds do hft_bot"
        >
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Conexão</th>
                <th className="text-left px-4 py-2">Papel</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Nota</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              <tr className="border-b border-border/40 hover:bg-muted/30">
                <td className="px-4 py-3 font-medium font-sans">Deriv</td>
                <td className="px-4 py-3">
                  <Mono className="text-muted-foreground">Corretora (execução)</Mono>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Dot
                      tone={statusQuery.isLoading ? "muted" : isLive ? "pos" : "neg"}
                      className={isLive ? "animate-pulse" : ""}
                    />
                    <span className="uppercase font-mono tracking-wider">
                      {statusQuery.isLoading ? "…" : isLive ? "conectado" : "instável"}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  Conta demo DOT92172514 · Multiplier x800
                </td>
              </tr>
              {REAL_FEEDS.map((f) => (
                <tr
                  key={f.name}
                  className="border-b border-border/40 last:border-0 hover:bg-muted/30"
                >
                  <td className="px-4 py-3 font-medium font-sans">{f.name}</td>
                  <td className="px-4 py-3">
                    <Mono className="text-muted-foreground">{f.role}</Mono>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Dot
                        tone={statusQuery.isLoading ? "muted" : feedsConnected ? "pos" : "neg"}
                        className={feedsConnected ? "animate-pulse" : ""}
                      />
                      <span className="uppercase font-mono tracking-wider">
                        {statusQuery.isLoading
                          ? "…"
                          : feedsConnected
                            ? "conectado"
                            : "inferido: caído"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{f.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel
          className="col-span-12 xl:col-span-5"
          title={
            <>
              <Plug className="h-4 w-4 inline mr-2" />
              Outras integrações
            </>
          }
          subtitle="nenhuma implementada ainda"
        >
          <div className="px-4 py-8 text-sm text-muted-foreground">
            O ecossistema hoje é 100% Deriv. Exchanges como Binance/Coinbase/Kraken entram só como
            feed de preço (sem custódia, sem execução, sem saldo). Cotação de novos brokers/mercados
            preditivos (Polymarket, Kalshi, etc.) é uma direção possível de expansão, mas não existe
            integração real nenhuma além da Deriv no momento.
          </div>
        </Panel>
      </div>
    </div>
  );
}
