import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useApp } from "@/lib/store";
import { toast } from "sonner";

export function KillSwitchDialog() {
  const open = useApp((s) => s.killOpen);
  const setOpen = useApp((s) => s.setKillOpen);
  const kill = useApp((s) => s.kill);
  const pushNotif = useApp((s) => s.pushNotif);

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="text-destructive">Acionar Kill Switch</AlertDialogTitle>
          <AlertDialogDescription>
            Isto altera apenas o estado local do dashboard (badge "halted" no topo, tape
            pausado). <span className="font-mono text-foreground">status_api.py</span> na EC2 é
            somente leitura — não existe API de controle remoto do <span className="font-mono text-foreground">hft_bot</span> ainda.
            Para parar o bot de verdade hoje, é necessário SSH manual na EC2 (<span className="font-mono text-foreground">tmux kill-session -t hft_bot</span>).
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => {
              kill();
              pushNotif({
                kind: "error",
                title: "Kill switch acionado (dashboard)",
                desc: "Estado local marcado como halted. hft_bot na EC2 não foi afetado.",
              });
              toast.error("Kill switch acionado (dashboard apenas)", {
                description: "hft_bot continua rodando na EC2 — sem API de controle remoto ainda.",
              });
            }}
          >
            Confirmar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
