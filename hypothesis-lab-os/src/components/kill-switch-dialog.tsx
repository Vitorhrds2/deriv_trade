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
            Todas as posições live serão sinalizadas para fechamento e todos os bots em
            ambiente <span className="font-mono text-foreground">live</span> serão pausados imediatamente.
            Ambiente paper permanece inalterado.
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
                title: "Kill switch acionado",
                desc: "2 bots live pausados, 4 posições em flatten.",
              });
              toast.error("Kill switch acionado", {
                description: "Bots live pausados, posições em flatten.",
              });
            }}
          >
            Confirmar shutdown
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
