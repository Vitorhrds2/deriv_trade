import { AnimatePresence, motion } from "framer-motion";
import { useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";

export function RouteTransition({ children }: { children: React.ReactNode }) {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  const status = useRouterState({ select: (r) => r.status });
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (status === "pending") {
      setProgress(15);
      const ticks = [40, 65, 82, 92];
      const ids = ticks.map((p, i) =>
        setTimeout(() => setProgress(p), 100 + i * 120)
      );
      return () => ids.forEach(clearTimeout);
    } else {
      setProgress(100);
      const id = setTimeout(() => setProgress(0), 220);
      return () => clearTimeout(id);
    }
  }, [status, pathname]);

  return (
    <>
      {/* Top progress bar */}
      <div className="fixed top-0 left-0 right-0 z-[60] pointer-events-none">
        <div
          className="h-[2px] bg-gradient-to-r from-primary via-accent to-primary shadow-[0_0_12px_var(--primary)] transition-all duration-200 ease-out"
          style={{
            width: `${progress}%`,
            opacity: progress > 0 && progress < 100 ? 1 : progress === 100 ? 0.6 : 0,
          }}
        />
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </>
  );
}
