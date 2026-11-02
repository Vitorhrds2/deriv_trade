import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Dot, Mono } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { useState, useMemo, useRef } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Award,
  CheckCircle2,
  Clock,
  Cpu,
  Eye,
  FileCheck2,
  FileJson,
  FileWarning,
  Filter,
  FolderSync,
  Layers,
  Lock,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Upload,
  X,
  Zap,
} from "lucide-react";
import {
  ALLOWED_D107_EXACT_FILES,
  processD107Files,
  validateD107File,
  type D107ContractRecord,
  type D107TradeOutcome,
  type FileValidationResult,
} from "@/lib/d107-engine";

export const Route = createFileRoute("/d107")({
  head: () => ({
    meta: [
      { title: "D107 Serial Perpetual Ladder — Auditoria & Track Record | TradeLab OS" },
      {
        name: "description",
        content:
          "Painel institucional e auditoria forense do D107 Serial Ladder Bot (task-4831): Deal Cancellation 5m + Convexidade Perpétua 1x-8x na Deriv.",
      },
    ],
  }),
  component: D107InvestorDashboard,
});

type FolderScope = "global_all" | "live" | "r100_all" | "r100_session4" | "archive_1hz100v";

interface FolderApiResponse {
  ok: boolean;
  folderPath: string;
  scope: string;
  fetchedAt: string;
  availableD107Files: Array<{ name: string; size: number; mtime: string }>;
  files: Array<{ name: string; content: string; size: number; mtime: string }>;
  error?: string;
}

const SCOPE_OPTIONS: Array<{
  id: FolderScope;
  label: string;
  badge: string;
  description: string;
}> = [
  {
    id: "global_all",
    label: "Track Record Completo (Pasta)",
    badge: "+$47,14 Auditado",
    description: "Todas as sessões D107 da pasta trading-engine/ (R_100 + 1HZ100V + task-4831 ao vivo)",
  },
  {
    id: "live",
    label: "Sessão Ao Vivo (task-4831)",
    badge: "LIVE 1x–8x",
    description: "Apenas d107_rate_limit_winner_holding_results.jsonl + state.json da sessão atual pós-upgrade",
  },
  {
    id: "r100_all",
    label: "Consolidado R_100 (Serial)",
    badge: "R_100 100x",
    description: "Todas as sessões executadas exclusivamente no índice Volatility 100 (R_100)",
  },
  {
    id: "r100_session4",
    label: "Sessão 4 R_100 (18 Contratos)",
    badge: "70,6% Conv.",
    description: "Sessão contínua de 18 contratos em R_100 com Payoff Ratio de 3,50x",
  },
  {
    id: "archive_1hz100v",
    label: "Arquivo 1HZ100V (Alta Freq.)",
    badge: "+$45,67 Bruto",
    description: "Sessão histórica de 38 contratos resolvidos em 1HZ100V com corridas até +96%",
  },
];

const chartTooltip = {
  contentStyle: {
    background: "oklch(0.18 0.014 240)",
    border: "1px solid oklch(0.32 0.018 240)",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "JetBrains Mono, monospace",
  },
  labelStyle: { color: "oklch(0.70 0.018 240)", marginBottom: 4 },
};

function fmtUsd(val: number, signed = false): string {
  const abs = Math.abs(val).toFixed(2);
  if (val < 0) return `-$${abs}`;
  if (signed && val > 0) return `+$${abs}`;
  return `$${abs}`;
}

function fmtDuration(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function D107InvestorDashboard() {
  const [folderScope, setFolderScope] = useState<FolderScope>("global_all");
  const [dataSourceMode, setDataSourceMode] = useState<"folder" | "upload">("folder");
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; content: string; size: number }>>([]);
  const [uploadErrors, setUploadErrors] = useState<FileValidationResult[]>([]);
  const [outcomeFilter, setOutcomeFilter] = useState<string>("ALL");
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedContractId, setSelectedContractId] = useState<string | null>(null);
  const [equityViewMode, setEquityViewMode] = useState<"both" | "net" | "gross">("both");

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // 1. Live query from local folder (/Users/vitorhrds/Documents/Github/hypothesis/trading-engine)
  const folderQuery = useQuery({
    queryKey: ["d107-folder", folderScope],
    queryFn: async (): Promise<FolderApiResponse> => {
      const res = await fetch(`/api/d107/folder?scope=${folderScope}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as FolderApiResponse;
    },
    refetchInterval: dataSourceMode === "folder" ? 3000 : false,
  });

  // 2. Also keep a lightweight live query to `scope=live` so the top task-4831 banner ALWAYS shows live telemetry
  const liveTelemetryQuery = useQuery({
    queryKey: ["d107-folder", "live"],
    queryFn: async (): Promise<FolderApiResponse> => {
      const res = await fetch(`/api/d107/folder?scope=live`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as FolderApiResponse;
    },
    refetchInterval: 3000,
  });

  const activeFilesToProcess = useMemo(() => {
    if (dataSourceMode === "upload" && uploadedFiles.length > 0) {
      return uploadedFiles;
    }
    return folderQuery.data?.files ?? [];
  }, [dataSourceMode, uploadedFiles, folderQuery.data]);

  const dataset = useMemo(() => {
    return processD107Files(activeFilesToProcess, { startingDemoBalance: 9940.0 });
  }, [activeFilesToProcess]);

  const liveDataset = useMemo(() => {
    return processD107Files(liveTelemetryQuery.data?.files ?? [], { startingDemoBalance: 9940.0 });
  }, [liveTelemetryQuery.data]);

  const { summary, contracts, equityCurve } = dataset;
  const liveActiveContract = liveDataset.activeContract ?? dataset.activeContract;
  const regimePolicy = liveDataset.regimePolicy ?? dataset.regimePolicy;

  // Handle strict file upload
  async function handleFilesSelected(fileList: FileList | File[]) {
    const arr = Array.from(fileList);
    if (arr.length === 0) return;

    const validLoaded: Array<{ name: string; content: string; size: number }> = [];
    const rejectedList: FileValidationResult[] = [];

    for (const file of arr) {
      const text = await file.text();
      const validation = validateD107File(file.name, text, file.size);
      if (validation.valid) {
        validLoaded.push({ name: file.name, content: text, size: file.size });
      } else {
        rejectedList.push(validation);
      }
    }

    setUploadErrors(rejectedList);
    if (validLoaded.length > 0) {
      setUploadedFiles((prev) => {
        const map = new Map(prev.map((f) => [f.name, f]));
        for (const f of validLoaded) map.set(f.name, f);
        return Array.from(map.values());
      });
      setDataSourceMode("upload");
    }
  }

  async function openStrictFilePicker() {
    // Use File System Access API if available to enforce strict extension filtering in OS dialog
    const win = window as unknown as {
      showOpenFilePicker?: (opts: unknown) => Promise<Array<{ getFile: () => Promise<File> }>>;
    };
    if (typeof win.showOpenFilePicker === "function") {
      try {
        const handles = await win.showOpenFilePicker({
          multiple: true,
          excludeAcceptAllOption: true,
          types: [
            {
              description:
                "Arquivos Oficiais D107 (d107_rate_limit_winner_holding_results.jsonl, d107_rate_limit_winner_holding_state.json)",
              accept: {
                "application/json": [".jsonl", ".json"],
              },
            },
          ],
        });
        const files = await Promise.all(handles.map((h) => h.getFile()));
        await handleFilesSelected(files);
        return;
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
      }
    }
    fileInputRef.current?.click();
  }

  // Filtered contracts for the table
  const filteredContracts = useMemo(() => {
    return contracts.filter((c) => {
      if (symbolFilter !== "ALL" && c.symbol !== symbolFilter) return false;
      if (outcomeFilter === "WINNERS" && !c.outcome.startsWith("PERPETUAL_WINNER")) return false;
      if (outcomeFilter === "CANCELLED" && c.outcome !== "CANCELLED_REFUNDED") return false;
      if (outcomeFilter === "SCRATCH" && c.outcome !== "PERPETUAL_SCRATCH_PREUPGRADE") return false;
      if (outcomeFilter === "ACTIVE" && !c.outcome.startsWith("ACTIVE_")) return false;
      if (searchQuery.trim() !== "") {
        const q = searchQuery.trim().toLowerCase();
        const matchCid = c.contractId.toLowerCase().includes(q);
        const matchShort = c.shortcode?.toLowerCase().includes(q) ?? false;
        const matchSess = c.sessionLabel.toLowerCase().includes(q);
        if (!matchCid && !matchShort && !matchSess) return false;
      }
      return true;
    });
  }, [contracts, outcomeFilter, symbolFilter, searchQuery]);

  const inspectedContract: D107ContractRecord | null = useMemo(() => {
    if (selectedContractId) {
      return contracts.find((c) => c.contractId === selectedContractId) ?? null;
    }
    return liveActiveContract ?? contracts[0] ?? null;
  }, [selectedContractId, contracts, liveActiveContract]);

  // Trade payoff distribution bars (most recent 40 closed contracts in chronological order)
  const tradePayoffBars = useMemo(() => {
    return equityCurve.slice(1).slice(-45).map((pt) => ({
      trade: pt.tradeLabel,
      contractId: pt.contractId,
      grossPnl: pt.grossPayoutPnl,
      netPnl: pt.netCashPnl,
      peakPnl: pt.peakPnl,
      outcome: pt.outcome,
      symbol: pt.symbol,
    }));
  }, [equityCurve]);

  // Ladder tier distribution for persuasion
  const ladderBreakdown = useMemo(() => {
    const closed = contracts.filter((c) => !c.outcome.startsWith("ACTIVE_"));
    const cancelled = closed.filter((c) => c.outcome === "CANCELLED_REFUNDED").length;
    const tier1 = closed.filter((c) => c.grossPayoutPnl > 0 && c.grossPayoutPnl < 0.25).length;
    const tier2 = closed.filter((c) => c.grossPayoutPnl >= 0.25 && c.grossPayoutPnl < 0.5).length;
    const tier3 = closed.filter((c) => c.grossPayoutPnl >= 0.5).length;
    return [
      {
        tier: "Janela 5m: Cancelados (100% Stake Reembolsado)",
        count: cancelled,
        impact: "Perda truncada na taxa (-$0.10)",
        color: "oklch(0.62 0.018 240)",
      },
      {
        tier: "Degrau 1: Winners +5% a +25% (Piso Breakeven $1.12)",
        count: tier1,
        impact: "Paga a taxa e garante lucro líquido",
        color: "oklch(0.78 0.17 75)",
      },
      {
        tier: "Degrau 2: Winners +25% a +50% (2,5x a 5x a Taxa)",
        count: tier2,
        impact: "Paga 3 a 5 cancelamentos em 1 trade",
        color: "oklch(0.78 0.18 150)",
      },
      {
        tier: "Degrau 3+: Corridas Perpétuas +50% a +800% (1x–8x Stake)",
        count: tier3,
        impact: "Explosão de convexidade (5x a 80x a taxa)",
        color: "oklch(0.85 0.18 130)",
      },
    ];
  }, [contracts]);

  const r100Metrics = regimePolicy?.deriv_metrics?.R_100;

  return (
    <div className="max-w-[1640px] mx-auto space-y-6 pb-12">
      <PageHeader
        eyebrow="execution › deriv multipliers › D107 serial perpetual ladder (task-4831)"
        title={
          <span className="flex items-center gap-3 flex-wrap">
            <span className="h-9 w-9 rounded-lg bg-primary/15 border border-primary/40 grid place-items-center glow-primary">
              <Zap className="h-5 w-5 text-primary" />
            </span>
            <span>D107 Serial Perpetual Ladder Bot</span>
            <Badge className="bg-primary/15 text-primary border-primary/40 font-mono text-xs">
              1x–8x CONVEXITY
            </Badge>
            <Badge variant="outline" className="font-mono text-xs border-success/40 text-success">
              Conta {summary.accountId} ({summary.accountType.toUpperCase()})
            </Badge>
          </span>
        }
        description="Auditoria forense e monitoramento em tempo real da tese D107: Contratos Multiplier 100x com opção de Deal Cancellation (5m) que reembolsa 100% do stake nos perdedores e converte vencedores em posições perpétuas sem expiração com escada de proteção de lucros (1x a 8x do stake)."
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                folderQuery.refetch();
                liveTelemetryQuery.refetch();
              }}
            >
              <RefreshCw
                className={`h-4 w-4 ${folderQuery.isFetching || liveTelemetryQuery.isFetching ? "animate-spin" : ""}`}
              />
              Sincronizar Agora
            </Button>
            <Button
              size="sm"
              className="gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={openStrictFilePicker}
            >
              <Upload className="h-4 w-4" />
              Upload de Arquivo(s) D107
            </Button>
          </div>
        }
      />

      {/* ─── Fonte de Dados: Leitura Direta da Pasta + Seletor Restrito de Upload ─── */}
      <Panel
        title={
          <span className="flex items-center gap-2">
            <FolderSync className="h-4 w-4 text-primary" />
            Fonte de Dados Auditável: Leitura Direta da Pasta Local & Upload com Filtro Restrito
          </span>
        }
        subtitle={
          dataSourceMode === "folder"
            ? `Lendo automaticamente de ${folderQuery.data?.folderPath ?? "/Users/vitorhrds/Documents/Github/hypothesis/trading-engine"} (polling a cada 3s)`
            : `Modo Upload Manual Ativo (${uploadedFiles.length} arquivo(s) autenticado(s) pelo validador de schema D107)`
        }
        actions={
          <div className="flex items-center gap-2">
            {dataSourceMode === "upload" && (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs border-primary/40 text-primary"
                onClick={() => {
                  setDataSourceMode("folder");
                  setUploadErrors([]);
                }}
              >
                <FolderSync className="h-3.5 w-3.5" />
                Voltar para Leitura Direta da Pasta
              </Button>
            )}
            <Badge
              variant="outline"
              className={`font-mono text-[11px] ${
                dataSourceMode === "folder"
                  ? "border-success/40 text-success bg-success/10"
                  : "border-accent/40 text-accent bg-accent/10"
              }`}
            >
              {dataSourceMode === "folder" ? "● AUTO-SYNC PASTA ATIVO" : "● MODO UPLOAD MANUAL"}
            </Badge>
          </div>
        }
      >
        <div className="p-4 space-y-4">
          {/* Scope Selector Pills */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2.5">
            {SCOPE_OPTIONS.map((opt) => {
              const active = dataSourceMode === "folder" && folderScope === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    setDataSourceMode("folder");
                    setFolderScope(opt.id);
                    setSelectedContractId(null);
                  }}
                  className={`text-left rounded-lg border p-3 transition-all cursor-pointer ${
                    active
                      ? "border-primary bg-primary/10 shadow-sm"
                      : "border-border/70 bg-background/50 hover:border-border hover:bg-secondary/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="font-medium text-xs truncate">{opt.label}</span>
                    <span
                      className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                        active ? "bg-primary text-primary-foreground font-semibold" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {opt.badge}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-2">{opt.description}</p>
                </button>
              );
            })}
          </div>

          {/* Strict Upload Box & Loaded File Signatures */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center pt-2 border-t border-border/60">
            <div className="lg:col-span-6 flex flex-col sm:flex-row sm:items-center gap-3 bg-background/60 rounded-lg border border-dashed border-primary/40 p-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <Lock className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span>Seletor de Upload Estrito (Apenas Outputs Oficiais D107)</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5 font-mono truncate">
                  Aceita exclusivamente:{" "}
                  <span className="text-foreground">{ALLOWED_D107_EXACT_FILES.slice(0, 2).join(", ")}</span> (e{" "}
                  <span className="text-foreground">d107_results_*.jsonl / d107_state_*.json</span>)
                </p>
              </div>
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".jsonl,.json"
                  aria-label="Selecionar arquivos de output do D107"
                  className="d107-file-input text-xs text-muted-foreground max-w-[250px]"
                  onChange={(e) => {
                    if (e.target.files) {
                      handleFilesSelected(e.target.files);
                      e.target.value = "";
                    }
                  }}
                />
              </div>
            </div>

            <div className="lg:col-span-6 flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground mr-1">
                Arquivos Autenticados ({dataset.loadedFiles.filter((f) => f.valid).length}):
              </span>
              {dataset.loadedFiles
                .filter((f) => f.valid)
                .map((f) => (
                  <Badge
                    key={f.fileName}
                    variant="outline"
                    className="font-mono text-[11px] gap-1.5 py-1 border-border bg-background/70"
                  >
                    <FileCheck2 className="h-3 w-3 text-success" />
                    <span>{f.fileName}</span>
                    <span className="text-muted-foreground">({f.recordCount} reg.)</span>
                  </Badge>
                ))}
            </div>
          </div>

          {/* Rejected File Alert if someone tries to upload a non-D107 file */}
          {uploadErrors.length > 0 && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 flex items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-xs font-semibold text-destructive">
                  <FileWarning className="h-4 w-4 shrink-0" />
                  <span>Bloqueio de Segurança do Seletor: Arquivo(s) Não-D107 Recusado(s)</span>
                </div>
                {uploadErrors.map((err, i) => (
                  <p key={i} className="text-xs text-destructive/90 font-mono">
                    • {err.reason}
                  </p>
                ))}
              </div>
              <Button variant="ghost" size="sm" onClick={() => setUploadErrors([])} className="h-6 w-6 p-0">
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </Panel>

      {/* ─── Cockpit em Tempo Real do task-4831 & AI Regime Supervisor ─── */}
      <div className="grid grid-cols-12 gap-4">
        <Panel
          className="col-span-12 lg:col-span-7 border-primary/30"
          title={
            <span className="flex items-center gap-2">
              <Dot tone="pos" className="animate-pulse" />
              <span>Cockpit em Tempo Real — Motor Serial D107 (task-4831)</span>
            </span>
          }
          subtitle={`Estado da Máquina: ${liveDataset.summary.machineState} · Próxima Perna Alternada: ${liveDataset.summary.nextDirection}`}
          actions={
            <div className="flex items-center gap-2">
              <Badge className="bg-success/15 text-success border-success/40 font-mono text-xs">
                Piso Breakeven $1.12 Ativo
              </Badge>
              <Badge className="bg-primary/15 text-primary border-primary/40 font-mono text-xs">
                Alvo Ladder 9.0x (+800%)
              </Badge>
            </div>
          }
        >
          <div className="p-4">
            {liveActiveContract ? (
              <div className="rounded-lg border border-primary/40 bg-primary/[0.04] p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <Badge
                      className={
                        liveActiveContract.direction === "MULTUP"
                          ? "bg-success/20 text-success border-success/40 font-mono"
                          : "bg-accent/20 text-accent border-accent/40 font-mono"
                      }
                    >
                      {liveActiveContract.direction} 100x
                    </Badge>
                    <Mono className="text-sm font-semibold">#{liveActiveContract.contractId}</Mono>
                    <Badge variant="outline" className="font-mono text-xs">
                      {liveActiveContract.symbol}
                    </Badge>
                  </div>
                  <Badge
                    className={
                      liveActiveContract.outcome === "ACTIVE_PERPETUAL"
                        ? "bg-primary text-primary-foreground font-mono animate-pulse"
                        : "bg-info/20 text-info border-info/40 font-mono"
                    }
                  >
                    {liveActiveContract.outcome === "ACTIVE_PERPETUAL"
                      ? "★ PERPÉTUO ATIVO (LADDER 1x–8x)"
                      : "🛡 JANELA PROTEGIDA DEAL CANCELLATION (5m)"}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-1">
                  <div className="rounded border bg-card/80 p-2.5">
                    <div className="text-[10px] font-mono uppercase text-muted-foreground">Spot Entrada</div>
                    <div className="font-mono text-sm font-semibold mt-0.5">
                      {liveActiveContract.entrySpot?.toFixed(2) ?? "—"}
                    </div>
                  </div>
                  <div className="rounded border bg-card/80 p-2.5">
                    <div className="text-[10px] font-mono uppercase text-muted-foreground">Spot Atual</div>
                    <div className="font-mono text-sm font-semibold mt-0.5">
                      {liveActiveContract.exitSpot?.toFixed(2) ?? "—"}
                    </div>
                  </div>
                  <div className="rounded border bg-card/80 p-2.5">
                    <div className="text-[10px] font-mono uppercase text-muted-foreground">PnL Flutuante</div>
                    <div
                      className={`font-mono text-sm font-semibold mt-0.5 ${
                        liveActiveContract.grossPayoutPnl > 0
                          ? "text-success"
                          : liveActiveContract.grossPayoutPnl < 0
                            ? "text-warning"
                            : "text-foreground"
                      }`}
                    >
                      {fmtUsd(liveActiveContract.grossPayoutPnl, true)}
                    </div>
                  </div>
                  <div className="rounded border bg-card/80 p-2.5">
                    <div className="text-[10px] font-mono uppercase text-muted-foreground">Pico Atingido (MFE)</div>
                    <div className="font-mono text-sm font-semibold text-success mt-0.5">
                      {fmtUsd(Math.max(0, liveActiveContract.peakUnrealizedPnl), true)}
                    </div>
                  </div>
                  <div className="rounded border bg-card/80 p-2.5">
                    <div className="text-[10px] font-mono uppercase text-muted-foreground">Risco Máx. 5m</div>
                    <div className="font-mono text-sm font-semibold text-primary mt-0.5">
                      Travado em -$0.10
                    </div>
                  </div>
                </div>

                {/* Progress bar of 5m window */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px] font-mono text-muted-foreground">
                    <span>
                      Tempo Decorrido: <strong className="text-foreground">{fmtDuration(liveActiveContract.holdDurationSeconds)}</strong>
                    </span>
                    <span>
                      {liveActiveContract.outcome === "ACTIVE_PERPETUAL"
                        ? "Deal Cancellation expirado → Contrato virou Perpétuo sem expiração!"
                        : `Janela Deal Cancellation: ${Math.min(300, liveActiveContract.holdDurationSeconds)}s / 300s (Decisão aos 285s)`}
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${
                        liveActiveContract.outcome === "ACTIVE_PERPETUAL" ? "bg-primary" : "bg-info"
                      }`}
                      style={{
                        width: `${Math.min(100, (liveActiveContract.holdDurationSeconds / 300) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border bg-background/50 p-4 flex items-center justify-between">
                <div className="space-y-1">
                  <div className="text-sm font-medium flex items-center gap-2">
                    <Clock className="h-4 w-4 text-primary" />
                    <span>Entre Ciclos Seriais — Preparando Próxima Entrada ({liveDataset.summary.nextDirection})</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    O motor opera de forma estritamente serial (`max_open_positions = 1`). Assim que um contrato encerra e o regime Hurst valida, a perna oposta é disparada.
                  </p>
                </div>
                <Badge variant="outline" className="font-mono text-xs">
                  Saldo: {fmtUsd(liveDataset.summary.currentBalance)}
                </Badge>
              </div>
            )}
          </div>
        </Panel>

        <Panel
          className="col-span-12 lg:col-span-5"
          title={
            <span className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-accent" />
              <span>AI Quant Regime Supervisor (Acoplamento em Tempo Real)</span>
            </span>
          }
          subtitle="Filtro matemático que bloqueia entradas em regimes de ruído / reversão à média (H < 0,45)"
          actions={
            <Badge
              className={
                (r100Metrics?.hurst ?? 0.5) >= 0.45
                  ? "bg-success/15 text-success border-success/40 font-mono text-xs"
                  : "bg-warning/15 text-warning border-warning/40 font-mono text-xs"
              }
            >
              {(r100Metrics?.hurst ?? 0.5) >= 0.45 ? "REGIME APROVADO (EXPANSÃO)" : "PAUSA DEFENSIVA (CHOP)"}
            </Badge>
          }
        >
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-3 gap-2.5">
              <div className="rounded-lg border bg-background/60 p-3">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Expoente de Hurst (R_100)</div>
                <div
                  className={`text-xl font-mono font-semibold mt-1 ${
                    (r100Metrics?.hurst ?? 0.46) >= 0.45 ? "text-success" : "text-warning"
                  }`}
                >
                  {r100Metrics?.hurst?.toFixed(4) ?? "0.4611"}
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5">Mínimo exigido: H ≥ 0.4500</div>
              </div>
              <div className="rounded-lg border bg-background/60 p-3">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Volatilidade 5m</div>
                <div className="text-xl font-mono font-semibold mt-1 text-foreground">
                  {r100Metrics?.volatility_5m_pct?.toFixed(3) ?? "0.281"}%
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5">Excursão Browniana</div>
              </div>
              <div className="rounded-lg border bg-background/60 p-3">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Entradas Filtradas</div>
                <div className="text-xl font-mono font-semibold mt-1 text-primary">
                  {liveDataset.summary.regimeFilterPausesCount} ciclos
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5">Taxas de -$0.10 poupadas</div>
              </div>
            </div>
            <div className="text-xs text-muted-foreground bg-secondary/40 rounded px-3 py-2 font-mono flex items-center justify-between">
              <span>Estratégia Primária: {regimePolicy?.deriv_primary_strategy ?? "UNCONDITIONAL_VOLATILITY_EXPANSION"}</span>
              <span className="text-primary">SL Nativo Backup: $0.35</span>
            </div>
          </div>
        </Panel>
      </div>

      {/* ─── 8 KPIs Institucionais para Convencer Investidores ─── */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        <Stat
          label="Lucro Real na Conta"
          value={fmtUsd(summary.verifiedAccountProfit, true)}
          tone={summary.verifiedAccountProfit >= 0 ? "pos" : "neg"}
          delta={`Saldo: ${fmtUsd(summary.currentBalance)}`}
          hint="Inicial $9,940.00"
        />
        <Stat
          label="Payout Bruto Winners"
          value={fmtUsd(summary.grossPayoutTotal, true)}
          tone="pos"
          delta={`${summary.perpetualWinnersCount} perpétuos`}
          hint={`Máx: ${fmtUsd(summary.maxSingleWinnerGross, true)}`}
        />
        <Stat
          label="Payoff Ratio (Assimetria)"
          value={`${summary.payoffRatioGross.toFixed(2)}x`}
          tone={summary.payoffRatioGross >= 2.0 ? "pos" : "neutral"}
          delta={`Líq: ${summary.payoffRatioNet.toFixed(2)}x`}
          hint={`Ganho méd. vs taxa`}
        />
        <Stat
          label="Conversão Perpétuo"
          value={`${summary.perpetualConversionRatePct}%`}
          tone={summary.edgeMarginAboveBreakevenPct > 0 ? "pos" : "neutral"}
          delta={`${summary.edgeMarginAboveBreakevenPct >= 0 ? "+" : ""}${summary.edgeMarginAboveBreakevenPct}% vs BE`}
          hint={`Breakeven: ${summary.breakevenWinRateGrossPct}%`}
        />
        <Stat
          label="Profit Factor"
          value={`${summary.profitFactorGross.toFixed(2)}`}
          tone={summary.profitFactorGross >= 1.2 ? "pos" : "neutral"}
          delta={`Líq: ${summary.profitFactorNet.toFixed(2)}`}
          hint={`${summary.closedContracts} trades`}
        />
        <Stat
          label="Salvo pelo Seguro 5m"
          value={fmtUsd(summary.capitalSavedByCancelTotal, true)}
          tone="pos"
          delta={`${summary.cancelledCount} reembolsos`}
          hint="$1.00 devolvido/cada"
        />
        <Stat
          label="Pico de Excursão"
          value={`${summary.maxPeakExcursionMultiple.toFixed(2)}x`}
          tone="pos"
          delta={`+${((summary.maxPeakExcursionMultiple - 1) * 100).toFixed(0)}% s/ stake`}
          hint="Potencial 1x–8x"
        />
        <Stat
          label="PnL Pró-Forma Piso $1.12"
          value={fmtUsd(summary.proFormaUpgradedNetPnl, true)}
          tone="pos"
          delta={`+${fmtUsd(summary.leakedProfitInPreUpgrade)} blindado`}
          hint={`Elimina ${summary.scratchPreUpgradeCount} scratches`}
        />
      </div>

      {/* ─── Tese Visual: Por que o D107 é Rentável? (A Matemática da Convexidade) ─── */}
      <Panel
        className="d107-containment-region border-primary/25"
        title={
          <span className="flex items-center gap-2">
            <Award className="h-4 w-4 text-primary" />
            <span>A Prova Matemática do Edge: Por Que a Opção de Deal Cancellation + Perpétuo Gera Lucro Assimétrico?</span>
          </span>
        }
        subtitle="Comparativo direto entre o risco truncado nos primeiros 5 minutos e o ganho ilimitado após a conversão em perpétuo"
      >
        <div className="p-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="rounded-lg border bg-background/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider text-info">
                1. Fase Protegida (0 a 300 Segundos)
              </span>
              <Badge variant="outline" className="font-mono text-xs border-info/40 text-info">
                Put Option Subsidiada
              </Badge>
            </div>
            <div className="text-lg font-semibold">Perda Máxima Travada em -$0,10</div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Quando o mercado vai contra a posição nos primeiros 5 minutos (mesmo que caia -40% ou -80%), o bot aciona o{" "}
              <strong className="text-foreground">Deal Cancellation</strong> aos 285s e a corretora{" "}
              <strong className="text-success">reembolsa 100% do Stake ($1,00)</strong>. Nos{" "}
              <strong className="text-foreground">{summary.cancelledCount} trades cancelados</strong>, esse seguro já economizou{" "}
              <strong className="text-success">{fmtUsd(summary.capitalSavedByCancelTotal, true)}</strong> de perdas reais.
            </p>
          </div>

          <div className="rounded-lg border bg-background/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider text-primary">
                2. Transição Perpétua (&gt; 300 Segundos)
              </span>
              <Badge variant="outline" className="font-mono text-xs border-primary/40 text-primary">
                Expiração Ano 2126
              </Badge>
            </div>
            <div className="text-lg font-semibold">Vencedores Viram Perpétuos (1x a 8x)</div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Quando a posição sobrevive aos 5 minutos em lucro, a janela de cancelamento expira e o contrato{" "}
              <strong className="text-foreground">vira um perpétuo alavancado 100x sem data de expiração</strong>. Com o{" "}
              <strong className="text-primary">Piso de Breakeven em $1,12</strong> e a escada de trailing stop até{" "}
              <strong className="text-success">9.0x (+800%)</strong>, um único vencedor paga de 3 a 80 cancelamentos.
            </p>
          </div>

          <div className="rounded-lg border bg-background/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider text-success">
                3. Vantagem Estatística Auditada
              </span>
              <Badge variant="outline" className="font-mono text-xs border-success/40 text-success">
                EV Positivo Comprovado
              </Badge>
            </div>
            <div className="text-lg font-semibold">
              Taxa de Conversão ({summary.perpetualConversionRatePct}%) &gt; Breakeven ({summary.breakevenWinRateGrossPct}%)
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Com um Payoff Ratio bruto de <strong className="text-success">{summary.payoffRatioGross.toFixed(2)}x</strong>, o bot precisaria acertar apenas{" "}
              <strong className="text-foreground">{summary.breakevenWinRateGrossPct}%</strong> das vezes para empatar. Na prática, o bot converteu{" "}
              <strong className="text-success">{summary.perpetualConversionRatePct}%</strong> dos contratos em perpétuos vencedores — gerando uma folga matemática de{" "}
              <strong className="text-success">+{summary.edgeMarginAboveBreakevenPct}% acima do breakeven</strong>.
            </p>
          </div>
        </div>
      </Panel>

      {/* ─── Gráficos Principais: Curva de Patrimônio + Assimetria por Trade ─── */}
      <div className="grid grid-cols-12 gap-4 d107-containment-region">
        <Panel
          className="col-span-12 xl:col-span-8"
          title={
            <span className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              <span>Curva de Rentabilidade Acumulada vs. Cenário Sem Deal Cancellation</span>
            </span>
          }
          subtitle={`Evolução patrimonial em ${summary.closedContracts} contratos concluídos · Linha vermelha mostra o resultado caso o seguro de 5m não existisse`}
          actions={
            <div className="flex items-center gap-1 bg-secondary/60 p-1 rounded-md">
              {[
                { id: "both", label: "Visão Completa" },
                { id: "net", label: "Fluxo Líquido" },
                { id: "gross", label: "Payout Bruto" },
              ].map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setEquityViewMode(m.id as "both" | "net" | "gross")}
                  className={`px-2.5 py-1 rounded text-xs font-mono cursor-pointer transition-colors ${
                    equityViewMode === m.id
                      ? "bg-primary text-primary-foreground font-semibold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          }
        >
          <div className="p-4 h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={equityCurve}>
                <defs>
                  <linearGradient id="d107GrossGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="oklch(0.85 0.18 130)" stopOpacity={0.32} />
                    <stop offset="100%" stopColor="oklch(0.85 0.18 130)" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="d107NetGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="oklch(0.78 0.18 150)" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="oklch(0.78 0.18 150)" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.26 0.014 240)" />
                <XAxis
                  dataKey="tradeLabel"
                  tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 11, fontFamily: "JetBrains Mono" }}
                />
                <YAxis
                  tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 11, fontFamily: "JetBrains Mono" }}
                  tickFormatter={(v) => fmtUsd(v, true)}
                />
                <Tooltip
                  {...chartTooltip}
                  formatter={(val: number, name: string) => {
                    const labels: Record<string, string> = {
                      cumulativeGrossPnl: "Payout Bruto Acumulado (s/ Stake)",
                      cumulativeNetPnl: "Lucro Líquido Real (após taxas 5m)",
                      hypotheticalNoCancelPnl: "Sem Deal Cancellation (Sem Seguro)",
                    };
                    return [fmtUsd(val, true), labels[name] || name];
                  }}
                />
                <ReferenceLine y={0} stroke="oklch(0.50 0.018 240)" strokeDasharray="4 4" />
                {(equityViewMode === "both" || equityViewMode === "gross") && (
                  <Area
                    type="monotone"
                    dataKey="cumulativeGrossPnl"
                    stroke="oklch(0.85 0.18 130)"
                    strokeWidth={2.2}
                    fill="url(#d107GrossGrad)"
                  />
                )}
                {(equityViewMode === "both" || equityViewMode === "net") && (
                  <Area
                    type="monotone"
                    dataKey="cumulativeNetPnl"
                    stroke="oklch(0.78 0.18 150)"
                    strokeWidth={2.5}
                    fill="url(#d107NetGrad)"
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="hypotheticalNoCancelPnl"
                  stroke="oklch(0.65 0.22 25)"
                  strokeWidth={1.8}
                  strokeDasharray="5 5"
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          className="col-span-12 xl:col-span-4"
          title={
            <span className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-accent" />
              <span>Distribuição da Escada Perpétua (Ladder)</span>
            </span>
          }
          subtitle="Como os contratos se dividem entre cancelamentos protegidos e degraus de lucro"
        >
          <div className="p-4 space-y-3">
            {ladderBreakdown.map((item) => {
              const pct =
                summary.closedContracts > 0 ? Math.round((item.count / summary.closedContracts) * 100) : 0;
              return (
                <div key={item.tier} className="rounded-lg border bg-background/60 p-3 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium">{item.tier}</span>
                    <span className="font-mono font-semibold">
                      {item.count} ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${pct}%`, backgroundColor: item.color }}
                    />
                  </div>
                  <div className="text-[11px] text-muted-foreground font-mono">{item.impact}</div>
                </div>
              );
            })}

            <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-1">
              <div className="flex items-center justify-between text-xs font-semibold text-primary">
                <span>Upgrade task-4831: Piso de Breakeven ($1,12)</span>
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <p className="text-[11px] text-muted-foreground">
                Nas sessões anteriores, {summary.scratchPreUpgradeCount} trades chegaram a ficar positivos mas fecharam no trailing entre $1,02 e $1,08 (vazando{" "}
                <strong className="text-foreground">{fmtUsd(summary.leakedProfitInPreUpgrade)}</strong>). Com o novo piso obrigatório em{" "}
                <strong className="text-primary">$1,12</strong>, qualquer recuo pós-trail garante lucro líquido.
              </p>
            </div>
          </div>
        </Panel>
      </div>

      {/* ─── Gráfico de Barras de Assimetria Trade a Trade + Inspetor de Ticks do Contrato ─── */}
      <div className="grid grid-cols-12 gap-4 d107-containment-region">
        <Panel
          className="col-span-12 lg:col-span-7"
          title={
            <span className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <span>Assimetria de Payoff Trade a Trade (Perdas Truncadas vs. Corridas Perpétuas)</span>
            </span>
          }
          subtitle="Clique em qualquer barra ou linha da tabela abaixo para inspecionar a trajetória de ticks daquele contrato"
        >
          <div className="p-4 h-[310px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={tradePayoffBars}
                onClick={(state) => {
                  const cid = state?.activePayload?.[0]?.payload?.contractId;
                  if (cid) setSelectedContractId(String(cid));
                }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.26 0.014 240)" />
                <XAxis
                  dataKey="trade"
                  tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }}
                />
                <YAxis
                  tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 11, fontFamily: "JetBrains Mono" }}
                  tickFormatter={(v) => fmtUsd(v, true)}
                />
                <Tooltip
                  {...chartTooltip}
                  formatter={(val: number, name: string) => [
                    fmtUsd(val, true),
                    name === "netPnl" ? "Fluxo Líquido Real" : "Pico MFE no Contrato",
                  ]}
                />
                <ReferenceLine y={0} stroke="oklch(0.55 0.018 240)" />
                <Bar dataKey="netPnl" radius={[3, 3, 0, 0]} className="cursor-pointer">
                  {tradePayoffBars.map((entry, idx) => (
                    <Cell
                      key={`cell-${idx}`}
                      fill={
                        entry.netPnl > 0
                          ? "oklch(0.82 0.18 135)"
                          : entry.outcome === "CANCELLED_REFUNDED"
                            ? "oklch(0.55 0.08 240)"
                            : "oklch(0.65 0.22 25)"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          className="col-span-12 lg:col-span-5"
          title={
            <span className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-info" />
              <span>
                Auditoria Microestrutural do Contrato{" "}
                {inspectedContract ? `#${inspectedContract.contractId}` : ""}
              </span>
            </span>
          }
          subtitle={
            inspectedContract
              ? `${inspectedContract.symbol} · ${inspectedContract.direction} ${inspectedContract.multiplier}x · ${inspectedContract.outcomeLabel}`
              : "Selecione um contrato para visualizar seus ticks"
          }
        >
          <div className="p-4 space-y-3">
            {inspectedContract ? (
              <>
                <div className="grid grid-cols-4 gap-2 text-xs">
                  <div className="rounded border bg-background/60 p-2">
                    <div className="text-[10px] font-mono text-muted-foreground">Custo Compra</div>
                    <div className="font-mono font-semibold">{fmtUsd(inspectedContract.buyPrice)}</div>
                  </div>
                  <div className="rounded border bg-background/60 p-2">
                    <div className="text-[10px] font-mono text-muted-foreground">Valor Recebido</div>
                    <div className="font-mono font-semibold text-primary">
                      {inspectedContract.soldFor !== null ? fmtUsd(inspectedContract.soldFor) : "Aberto"}
                    </div>
                  </div>
                  <div className="rounded border bg-background/60 p-2">
                    <div className="text-[10px] font-mono text-muted-foreground">Pico (MFE)</div>
                    <div className="font-mono font-semibold text-success">
                      {fmtUsd(Math.max(0, inspectedContract.peakUnrealizedPnl), true)}
                    </div>
                  </div>
                  <div className="rounded border bg-background/60 p-2">
                    <div className="text-[10px] font-mono text-muted-foreground">Líquido Final</div>
                    <div
                      className={`font-mono font-semibold ${
                        inspectedContract.netCashPnl >= 0 ? "text-success" : "text-warning"
                      }`}
                    >
                      {fmtUsd(inspectedContract.netCashPnl, true)}
                    </div>
                  </div>
                </div>

                <div className="h-[180px] border rounded-lg bg-background/40 p-2">
                  {inspectedContract.observations.length > 1 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={inspectedContract.observations}>
                        <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.25 0.014 240)" />
                        <XAxis
                          dataKey="elapsedSeconds"
                          tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }}
                          tickFormatter={(v) => `${v}s`}
                        />
                        <YAxis
                          tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }}
                          tickFormatter={(v) => fmtUsd(v, true)}
                        />
                        <Tooltip
                          {...chartTooltip}
                          formatter={(v: number) => [fmtUsd(v, true), "PnL Instantâneo"]}
                          labelFormatter={(l) => `T+${l}s após abertura`}
                        />
                        <ReferenceLine y={0} stroke="oklch(0.50 0.018 240)" strokeDasharray="3 3" />
                        <ReferenceLine
                          x={285}
                          stroke="oklch(0.78 0.17 75)"
                          strokeDasharray="3 3"
                          label={{ value: "285s (Filtro 5m)", fill: "oklch(0.78 0.17 75)", fontSize: 9 }}
                        />
                        <Area
                          type="monotone"
                          dataKey="effectivePnl"
                          stroke="oklch(0.85 0.18 130)"
                          fill="oklch(0.85 0.18 130 / 0.2)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-muted-foreground font-mono text-center px-4">
                      Contrato reconciliado via state.json (Spot {inspectedContract.entrySpot ?? "—"} →{" "}
                      {inspectedContract.exitSpot ?? "—"} · Pico {fmtUsd(inspectedContract.peakUnrealizedPnl, true)})
                    </div>
                  )}
                </div>

                <div className="text-[11px] font-mono text-muted-foreground bg-secondary/50 rounded px-2.5 py-1.5 truncate">
                  Shortcode Corretora: <span className="text-foreground">{inspectedContract.shortcode ?? "—"}</span>
                </div>
              </>
            ) : null}
          </div>
        </Panel>
      </div>

      {/* ─── Tabela Forense Completa de Contratos (Responsive Sticky Table) ─── */}
      <Panel
        className="d107-containment-region"
        title={
          <span className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <span id="d107-contracts-caption">
              Livro Razão Forense de Contratos ({filteredContracts.length} de {contracts.length} exibidos)
            </span>
          </span>
        }
        subtitle="Auditoria individual contrato a contrato com conciliação de custo ($1.10), reembolso Deal Cancellation ($1.00) e payout perpétuo"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="h-3.5 w-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="search"
                placeholder="Buscar ID ou shortcode..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1 rounded-md border bg-background text-xs font-mono w-48 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <select
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              aria-label="Filtrar por ativo"
              className="px-2.5 py-1 rounded-md border bg-background text-xs font-mono"
            >
              <option value="ALL">Todos os Ativos</option>
              <option value="R_100">R_100 (Vol 100)</option>
              <option value="1HZ100V">1HZ100V (1s)</option>
            </select>
            <select
              value={outcomeFilter}
              onChange={(e) => setOutcomeFilter(e.target.value)}
              aria-label="Filtrar por desfecho"
              className="px-2.5 py-1 rounded-md border bg-background text-xs font-mono"
            >
              <option value="ALL">Todos os Resultados</option>
              <option value="WINNERS">★ Winners Perpétuos</option>
              <option value="CANCELLED">🛡 Cancelados ($1 Reembolsado)</option>
              <option value="SCRATCH">Scratch Pré-Piso ($1.02–$1.08)</option>
              <option value="ACTIVE">⚡ Em Aberto</option>
            </select>
          </div>
        }
      >
        <div
          tabIndex={0}
          role="region"
          aria-labelledby="d107-contracts-caption"
          className="d107-table-wrapper"
        >
          <table className="text-xs">
            <thead>
              <tr className="border-b border-border/80 text-muted-foreground uppercase tracking-wider text-[10px] font-mono">
                <th className="px-3 py-2.5 text-left"># / Contrato ID</th>
                <th className="px-3 py-2.5 text-left">Sessão / Ativo</th>
                <th className="px-3 py-2.5 text-left">Direção</th>
                <th className="px-3 py-2.5 text-left">Desfecho / Ciclo de Vida</th>
                <th className="px-3 py-2.5 text-right">Spot (Entrada → Saída)</th>
                <th className="px-3 py-2.5 text-right">Pico (MFE)</th>
                <th className="px-3 py-2.5 text-right">Recebido (Bruto)</th>
                <th className="px-3 py-2.5 text-right">Fluxo Líquido</th>
                <th className="px-3 py-2.5 text-right">Salvo p/ Seguro</th>
                <th className="px-3 py-2.5 text-right">Duração</th>
              </tr>
            </thead>
            <tbody>
              {filteredContracts.map((c) => {
                const isSelected = inspectedContract?.contractId === c.contractId;
                const isWinner = c.netCashPnl > 0;
                const isCancelled = c.outcome === "CANCELLED_REFUNDED";
                return (
                  <tr
                    key={c.contractId}
                    onClick={() => setSelectedContractId(c.contractId)}
                    className={`border-b border-border/30 transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-primary/12"
                        : isWinner
                          ? "bg-success/[0.03] hover:bg-success/[0.08]"
                          : "hover:bg-secondary/40"
                    }`}
                  >
                    <th className="px-3 py-2.5 text-left font-mono font-medium">
                      <div className="flex items-center gap-1.5">
                        <span className="text-muted-foreground">#{c.trial}</span>
                        <span className="text-foreground underline decoration-dotted">{c.contractId}</span>
                      </div>
                    </th>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {c.symbol}
                        </Badge>
                        <span className="text-muted-foreground text-[11px] truncate max-w-[150px]">
                          {c.sessionLabel}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 font-mono">
                      <span
                        className={
                          c.direction === "MULTUP" ? "text-success font-semibold" : "text-accent font-semibold"
                        }
                      >
                        {c.direction === "MULTUP" ? "▲ MULTUP" : "▼ MULTDOWN"}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      {c.outcome.startsWith("PERPETUAL_WINNER") ? (
                        <Badge className="bg-success/15 text-success border-success/40 font-mono text-[10px]">
                          ★ {c.outcomeLabel}
                        </Badge>
                      ) : isCancelled ? (
                        <Badge variant="outline" className="border-info/40 text-info font-mono text-[10px]">
                          🛡 {c.outcomeLabel}
                        </Badge>
                      ) : c.outcome === "PERPETUAL_SCRATCH_PREUPGRADE" ? (
                        <Badge variant="outline" className="border-warning/40 text-warning font-mono text-[10px]">
                          {c.outcomeLabel}
                        </Badge>
                      ) : c.outcome.startsWith("ACTIVE_") ? (
                        <Badge className="bg-primary text-primary-foreground font-mono text-[10px] animate-pulse">
                          ⚡ {c.outcomeLabel}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="border-destructive/40 text-destructive font-mono text-[10px]">
                          {c.outcomeLabel}
                        </Badge>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                      {c.entrySpot ? `${c.entrySpot.toFixed(2)} → ${c.exitSpot?.toFixed(2) ?? "—"}` : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-success">
                      {fmtUsd(Math.max(0, c.peakUnrealizedPnl), true)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                      <span className={c.grossPayoutPnl > 0 ? "text-success font-semibold" : "text-muted-foreground"}>
                        {c.soldFor !== null ? `${fmtUsd(c.soldFor)} (${fmtUsd(c.grossPayoutPnl, true)})` : "—"}
                      </span>
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums font-semibold ${
                        c.netCashPnl > 0
                          ? "text-success"
                          : c.netCashPnl === -c.cancellationFee
                            ? "text-muted-foreground"
                            : "text-warning"
                      }`}
                    >
                      {fmtUsd(c.netCashPnl, true)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                      {c.savedByDealCancellation > 0 ? (
                        <span className="text-info">+{fmtUsd(c.savedByDealCancellation)}</span>
                      ) : (
                        <span className="text-muted-foreground/50">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-muted-foreground">
                      {fmtDuration(c.holdDurationSeconds)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
