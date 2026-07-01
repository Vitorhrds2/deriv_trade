import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { getHftStatus } from "@/lib/hft-api";
import { useApp } from "@/lib/store";

// Roda uma vez no root layout (qualquer página) e empurra notificações REAIS
// (não fabricadas) no sino do TopBar quando o hft_bot muda de estado ao vivo
// <-> offline/stale. Usa a mesma queryKey ["hft-status"] das páginas, então
// não gera requisições extras (React Query deduplica pelo cache).
export function useHftAlerts() {
  const pushNotif = useApp((s) => s.pushNotif);
  const prevLive = useRef<boolean | null>(null);

  const { data: status } = useQuery({
    queryKey: ["hft-status"],
    queryFn: () => getHftStatus(),
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (!status || !status.connected) return;
    const isLive = status.tmuxSessionAlive && !status.logStale;

    if (prevLive.current === null) {
      prevLive.current = isLive;
      return;
    }
    if (prevLive.current && !isLive) {
      pushNotif({
        kind: "error",
        title: "hft_bot offline",
        desc: status.lastErrorLine ?? "tmux caiu ou o log parou de atualizar.",
      });
    } else if (!prevLive.current && isLive) {
      pushNotif({
        kind: "success",
        title: "hft_bot voltou ao ar",
        desc: "heartbeat e sessão tmux normalizados.",
      });
    }
    prevLive.current = isLive;
  }, [status, pushNotif]);
}
