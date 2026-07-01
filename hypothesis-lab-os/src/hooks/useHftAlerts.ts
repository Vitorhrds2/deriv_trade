import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { getHftStatus, isHftLive } from "@/lib/hft-api";
import { useApp } from "@/lib/store";

// Roda uma vez no root layout (qualquer página) e empurra notificações REAIS
// (não fabricadas) no sino do TopBar quando o hft_bot muda de estado ao vivo
// <-> offline (sessão tmux morre/volta). Não usa log_stale sozinho -- o bot so
// loga em eventos, entao o log ficar quieto fora do golden hour e normal (ver
// isHftLive em hft-api.ts). Usa a mesma queryKey ["hft-status"] das páginas,
// então não gera requisições extras (React Query deduplica pelo cache).
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
    const isLive = isHftLive(status);

    if (prevLive.current === null) {
      prevLive.current = isLive;
      return;
    }
    if (prevLive.current && !isLive) {
      pushNotif({
        kind: "error",
        title: "hft_bot offline",
        desc: status.lastErrorLine ?? "sessão tmux caiu.",
      });
    } else if (!prevLive.current && isLive) {
      pushNotif({
        kind: "success",
        title: "hft_bot voltou ao ar",
        desc: "sessão tmux normalizada.",
      });
    }
    prevLive.current = isLive;
  }, [status, pushNotif]);
}
