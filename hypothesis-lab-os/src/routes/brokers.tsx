import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { brokers as seedBrokers, fmtMoney, type BrokerConn } from "@/lib/mock-data";
import { MoreHorizontal, Plug, PlugZap, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";

export const Route = createFileRoute("/brokers")({
  head: () => ({ meta: [{ title: "Brokers — TradeLab OS" }] }),
  component: BrokersPage,
});

type BrokerType = BrokerConn["type"];
const availableSeed: { name: string; type: BrokerType }[] = [
  { name: "Interactive Brokers", type: "Equity" },
  { name: "Coinbase Pro",        type: "Crypto" },
  { name: "Tradier",             type: "Equity" },
  { name: "Kraken Futures",      type: "Crypto" },
  { name: "Bybit",               type: "Crypto" },
  { name: "Manifold",            type: "Prediction" },
];

function BrokersPage() {
  const [brokers, setBrokers] = useState<BrokerConn[]>(seedBrokers);
  const [available, setAvailable] = useState(availableSeed);
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<BrokerType>("Crypto");

  const total = brokers.reduce((a, b) => a + b.balance, 0);
  const withLat = brokers.filter((b) => b.latencyMs);
  const avgLat = withLat.length ? Math.round(withLat.reduce((a, b) => a + (b.latencyMs ?? 0), 0) / withLat.length) : 0;

  const toggleStatus = (name: string) => {
    setBrokers((prev) =>
      prev.map((b) => {
        if (b.name !== name) return b;
        const next: BrokerConn["status"] = b.status === "connected" ? "offline" : "connected";
        toast.success(`${name} ${next === "connected" ? "reconectado" : "desconectado"}`);
        return { ...b, status: next, latencyMs: next === "connected" ? b.latencyMs || 90 : 0 };
      })
    );
  };

  const pingBroker = (name: string) => {
    toast.info(`Ping enviado para ${name}`);
    setBrokers((prev) =>
      prev.map((b) =>
        b.name === name
          ? { ...b, latencyMs: 40 + Math.floor(Math.random() * 180), status: "connected" }
          : b
      )
    );
  };

  const removeBroker = (name: string) => {
    setBrokers((prev) => prev.filter((b) => b.name !== name));
    toast.warning(`${name} removido das conexões`);
  };

  const connectAvailable = (a: { name: string; type: BrokerType }) => {
    setAvailable((prev) => prev.filter((x) => x.name !== a.name));
    setBrokers((prev) => [
      ...prev,
      {
        name: a.name,
        type: a.type,
        status: "connected",
        latencyMs: 60 + Math.floor(Math.random() * 80),
        region: "us-east-1",
        balance: Math.round(Math.random() * 20000),
      },
    ]);
    toast.success(`${a.name} conectado`);
  };

  const submitNew = () => {
    if (!newName.trim()) return;
    setBrokers((prev) => [
      ...prev,
      { name: newName, type: newType, status: "connected", latencyMs: 75, region: "us-east-1", balance: 0 },
    ]);
    toast.success(`${newName} adicionado`);
    setNewName("");
    setAddOpen(false);
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › brokers"
        title="Broker Connections"
        description="Conecte exchanges, brokers e mercados preditivos. Roteamento e failover automáticos."
        actions={
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="gap-1.5"><Plus className="h-4 w-4" />Adicionar broker</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Conectar novo broker</DialogTitle>
                <DialogDescription>Credenciais ficam encriptadas no vault do workspace.</DialogDescription>
              </DialogHeader>
              <div className="space-y-3 py-2">
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Nome do broker</label>
                  <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="ex: Deribit" className="mt-1" />
                </div>
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Classe</label>
                  <div className="flex gap-2 mt-1">
                    {(["Crypto", "Equity", "Forex", "Prediction"] as BrokerType[]).map((t) => (
                      <button key={t} onClick={() => setNewType(t)} className={`px-3 py-1.5 rounded-md border text-xs font-mono ${newType === t ? "border-primary/40 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>{t}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">API Key</label>
                  <Input placeholder="••••••••••••••••" className="mt-1 font-mono" />
                </div>
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancelar</Button>
                <Button onClick={submitNew} disabled={!newName.trim()} className="gap-1.5">
                  <PlugZap className="h-4 w-4" />Conectar
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Brokers conectados" value={brokers.filter((b) => b.status === "connected").length} delta={`${brokers.length} totais`} tone="pos" />
        <Stat label="Balance agregado"   value={fmtMoney(total)} />
        <Stat label="Latência média"     value={avgLat ? `${avgLat}ms` : "—"} />
        <Stat label="Failovers (7d)"     value="3" hint="todos resolvidos" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Conexões ativas" subtitle={`${brokers.length} broker${brokers.length === 1 ? "" : "s"}`}>
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Broker</th>
                <th className="text-left px-4 py-2">Classe</th>
                <th className="text-left px-4 py-2">Região</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Latência</th>
                <th className="text-right px-4 py-2">Balance</th>
                <th className="text-right px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <AnimatePresence initial={false}>
                {brokers.map((b) => (
                  <motion.tr key={b.name} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, x: 30 }} className="border-b border-border/40 last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">{b.name}</td>
                    <td className="px-4 py-3"><Mono className="text-muted-foreground">{b.type}</Mono></td>
                    <td className="px-4 py-3"><Mono className="text-muted-foreground">{b.region}</Mono></td>
                    <td className="px-4 py-3"><div className="flex items-center gap-2 text-xs"><Dot tone={b.status === "connected" ? "pos" : b.status === "degraded" ? "warn" : "neg"} className={b.status === "connected" ? "animate-pulse" : ""} /><span className="uppercase font-mono tracking-wider">{b.status}</span></div></td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">{b.latencyMs ? `${b.latencyMs}ms` : "—"}</td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">{fmtMoney(b.balance)}</td>
                    <td className="px-4 py-3 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7"><MoreHorizontal className="h-4 w-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <DropdownMenuLabel className="font-mono text-[10px] uppercase tracking-wider">{b.name}</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => pingBroker(b.name)}><RefreshCw className="h-3.5 w-3.5" />Ping & medir</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => toggleStatus(b.name)}>
                            <PlugZap className="h-3.5 w-3.5" />{b.status === "connected" ? "Desconectar" : "Reconectar"}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => toast.info(`Configuração de ${b.name}`)}>Configurar</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => removeBroker(b.name)} className="text-destructive">
                            <Trash2 className="h-3.5 w-3.5" />Remover
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </motion.tr>
                ))}
              </AnimatePresence>
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title={<><Plug className="h-4 w-4 inline mr-2" />Disponíveis para conectar</>} subtitle={`${available.length} integraç${available.length === 1 ? "ão" : "ões"} prontas`}>
          <ul className="divide-y divide-border/60">
            <AnimatePresence initial={false}>
              {available.map((a) => (
                <motion.li key={a.name} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, x: -20 }} className="px-4 py-3 flex items-center gap-3">
                  <div className="h-9 w-9 rounded-md bg-muted grid place-items-center font-mono text-xs">{a.name.slice(0, 2).toUpperCase()}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">{a.name}</div>
                    <Badge variant="outline" className="text-[10px] font-mono uppercase mt-0.5 border-border text-muted-foreground">{a.type}</Badge>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => connectAvailable(a)}>Conectar</Button>
                </motion.li>
              ))}
            </AnimatePresence>
            {available.length === 0 && (
              <li className="px-4 py-8 text-center text-xs text-muted-foreground">Todas as integrações disponíveis já estão conectadas.</li>
            )}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
