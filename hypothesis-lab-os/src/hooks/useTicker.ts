import { useEffect } from "react";
import { useApp } from "@/lib/store";

// Drives a global tick counter (every `ms`), pauseable.
export function useGlobalTicker(ms = 1500) {
  const bumpTick = useApp((s) => s.bumpTick);
  const killed = useApp((s) => s.killed);
  useEffect(() => {
    if (killed) return;
    const id = setInterval(bumpTick, ms);
    return () => clearInterval(id);
  }, [bumpTick, ms, killed]);
}
