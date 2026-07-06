import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between border-b border-border/70 pb-5 mb-6">
      <div>
        {eyebrow && (
          <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground mb-2">
            {eyebrow}
          </div>
        )}
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  delta,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: ReactNode;
  delta?: string;
  tone?: "pos" | "neg" | "neutral";
  hint?: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-4 relative overflow-hidden">
      <div className="absolute top-0 right-0 h-16 w-16 bg-primary/[0.04] blur-2xl" />
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold font-mono">{value}</div>
      <div className="mt-1 flex items-center justify-between text-xs">
        {delta && (
          <span
            className={cn(
              "font-mono",
              tone === "pos" && "text-success",
              tone === "neg" && "text-destructive",
              tone === "neutral" && "text-muted-foreground"
            )}
          >
            {delta}
          </span>
        )}
        {hint && <span className="text-muted-foreground">{hint}</span>}
      </div>
    </div>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border bg-card", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 px-4 py-3 border-b border-border/70">
          <div>
            {title && <div className="text-sm font-medium">{title}</div>}
            {subtitle && <div className="text-xs text-muted-foreground mt-0.5">{subtitle}</div>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Dot({ tone = "muted", className }: { tone?: "pos" | "neg" | "warn" | "muted" | "info"; className?: string }) {
  const map: Record<string, string> = {
    pos: "bg-success",
    neg: "bg-destructive",
    warn: "bg-warning",
    muted: "bg-muted-foreground/60",
    info: "bg-info",
  };
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", map[tone], className)} />;
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-xs", className)}>{children}</span>;
}

// Banner honesto para páginas que mostram um preview de UI/UX de uma feature ainda sem
// backend real (ex.: strategy builder, event feed). O ecossistema real hoje é hft_bot +
// unlock_bot (únicos com API de status dedicada) + 11 bots de validação de hipótese rodando
// em tmux na mesma EC2 sem UI própria (ver /paper, docs/state_of_research.md) + um catálogo
// de hipóteses fechadas testadas manualmente via scripts (ver /simulations).
export function ConceptBanner({ children }: { children: ReactNode }) {
  return (
    <div className="mb-6 rounded-lg border border-dashed border-warning/40 bg-warning/5 px-4 py-3 flex items-start gap-2.5 text-xs text-muted-foreground">
      <span className="mt-0.5 shrink-0 rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warning">
        preview
      </span>
      <span>{children}</span>
    </div>
  );
}
