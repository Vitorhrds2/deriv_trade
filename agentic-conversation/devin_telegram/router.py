import logging

from .devin_api import DevinAPI, DevinAPIError
from .local_agent import LocalAgent, LocalAgentError
from .queue_manager import QueueManager
from .registry import Agent, Registry

log = logging.getLogger("router")

HELP = """Comandos:
Agentes
  /new <prompt> - cria sessao Devin Cloud
  /attach <session_id> [alias] - registra sessao existente
  /local [alias] - registra o Devin Local (relay)
  /agents - lista agentes
  /use <alias> - define agente ativo
  /detach <alias> - remove agente
  /sessions - lista sessoes na Devin Cloud
Conversa
  <mensagem> - envia para o agente ativo
  @alias <mensagem> - envia para um agente especifico
  /all <mensagem> - broadcast para todos
Fila
  /queue <alias> <mensagem> - enfileira
  /queues - mostra filas
  /flush <alias> - despacha fila
  /clearqueue <alias> - limpa fila
Output
  /status [alias] - status + ultimas mensagens
  /watch <alias> on|off - streaming de output no chat
  /help - esta ajuda"""


class Router:
    def __init__(
        self,
        registry: Registry,
        queues: QueueManager,
        devin: DevinAPI | None,
        local: LocalAgent | None,
    ):
        self.registry = registry
        self.queues = queues
        self.devin = devin
        self.local = local

    def handle(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        try:
            if text.startswith("/"):
                return self._handle_command(text)
            if text.startswith("@"):
                alias, _, message = text[1:].partition(" ")
                return self._send_to(alias, message.strip())
            if not self.registry.active:
                return "Nenhum agente ativo. Use /new, /attach ou /local. /help para ajuda."
            return self._send_to(self.registry.active, text)
        except (DevinAPIError, LocalAgentError) as exc:
            return f"Erro: {exc}"

    def _handle_command(self, text: str) -> str:
        cmd, _, arg = text.partition(" ")
        cmd = cmd.lower().split("@")[0]
        arg = arg.strip()
        handlers = {
            "/start": lambda: HELP,
            "/help": lambda: HELP,
            "/new": lambda: self._cmd_new(arg),
            "/attach": lambda: self._cmd_attach(arg),
            "/local": lambda: self._cmd_local(arg),
            "/agents": self._cmd_agents,
            "/use": lambda: self._cmd_use(arg),
            "/detach": lambda: self._cmd_detach(arg),
            "/sessions": self._cmd_sessions,
            "/all": lambda: self._cmd_all(arg),
            "/queue": lambda: self._cmd_queue(arg),
            "/queues": self._cmd_queues,
            "/flush": lambda: self._cmd_flush(arg),
            "/clearqueue": lambda: self._cmd_clearqueue(arg),
            "/status": lambda: self._cmd_status(arg),
            "/watch": lambda: self._cmd_watch(arg),
        }
        handler = handlers.get(cmd)
        if not handler:
            return f"Comando desconhecido: {cmd}. /help para ajuda."
        return handler()

    # --- envio ---

    def _send_to(self, alias: str, message: str) -> str:
        if not message:
            return "Mensagem vazia."
        agent = self.registry.get(alias)
        if not agent:
            return f"Agente '{alias}' nao encontrado. /agents para listar."
        if agent.kind == "cloud":
            if not self.devin:
                return "DEVIN_API_KEY nao configurada."
            self.devin.send_message(agent.session_id, message)
        else:
            if not self.local:
                return "LOCAL_DEVIN_URL nao configurada."
            self.local.send_message(message)
        return f"-> [{alias}] enviado."

    # --- comandos ---

    def _cmd_new(self, prompt: str) -> str:
        if not prompt:
            return "Uso: /new <prompt>"
        if not self.devin:
            return "DEVIN_API_KEY nao configurada."
        result = self.devin.create_session(prompt)
        session_id = result.get("session_id", "")
        alias = self.registry.next_alias()
        self.registry.add(
            Agent(alias=alias, kind="cloud", session_id=session_id,
                  url=result.get("url", ""), watch=True)
        )
        return (
            f"Sessao criada: [{alias}] {session_id}\n{result.get('url', '')}\n"
            f"watch ligado; agente ativo: {self.registry.active}"
        )

    def _cmd_attach(self, arg: str) -> str:
        if not arg:
            return "Uso: /attach <session_id> [alias]"
        parts = arg.split()
        session_id = parts[0]
        alias = parts[1] if len(parts) > 1 else self.registry.next_alias()
        if self.registry.get(alias):
            return f"Alias '{alias}' ja existe."
        if not self.devin:
            return "DEVIN_API_KEY nao configurada."
        detail = self.devin.get_session(session_id)
        cursor = len(detail.get("messages", []))
        self.registry.add(
            Agent(alias=alias, kind="cloud", session_id=session_id, cursor=cursor)
        )
        return f"Anexado: [{alias}] {session_id} (status: {detail.get('status_enum', '?')})"

    def _cmd_local(self, arg: str) -> str:
        if not self.local:
            return "LOCAL_DEVIN_URL nao configurada."
        alias = arg.split()[0] if arg else "local"
        if self.registry.get(alias):
            return f"Alias '{alias}' ja existe."
        status = self.local.status()
        self.registry.add(Agent(alias=alias, kind="local", url=self.local.base))
        return f"Devin Local registrado como [{alias}] ({status.get('status', 'ok')})"

    def _cmd_agents(self) -> str:
        agents = self.registry.all()
        if not agents:
            return "Nenhum agente registrado."
        lines = []
        for agent in agents:
            marker = "*" if agent.alias == self.registry.active else " "
            watch = "watch:on" if agent.watch else "watch:off"
            lines.append(f"{marker} {agent.label()} ({watch})")
        return "\n".join(lines) + "\n(* = ativo)"

    def _cmd_use(self, alias: str) -> str:
        if self.registry.set_active(alias):
            return f"Agente ativo: {alias}"
        return f"Agente '{alias}' nao encontrado."

    def _cmd_detach(self, alias: str) -> str:
        if self.registry.remove(alias):
            return f"Removido: {alias}"
        return f"Agente '{alias}' nao encontrado."

    def _cmd_sessions(self) -> str:
        if not self.devin:
            return "DEVIN_API_KEY nao configurada."
        sessions = self.devin.list_sessions()
        if not sessions:
            return "Nenhuma sessao encontrada."
        lines = [
            f"- {s.get('session_id', '?')} [{s.get('status_enum', '?')}] "
            f"{(s.get('title') or '')[:60]}"
            for s in sessions[:20]
        ]
        return "\n".join(lines)

    def _cmd_all(self, message: str) -> str:
        if not message:
            return "Uso: /all <mensagem>"
        results = [self._send_to(a.alias, message) for a in self.registry.all()]
        return "\n".join(results) if results else "Nenhum agente registrado."

    def _cmd_queue(self, arg: str) -> str:
        alias, _, message = arg.partition(" ")
        message = message.strip()
        if not alias or not message:
            return "Uso: /queue <alias> <mensagem>"
        if not self.registry.get(alias):
            return f"Agente '{alias}' nao encontrado."
        size = self.queues.enqueue(alias, message)
        return f"Enfileirado para [{alias}] (fila: {size})."

    def _cmd_queues(self) -> str:
        sizes = self.queues.sizes()
        if not sizes:
            return "Todas as filas estao vazias."
        lines = []
        for alias, size in sizes.items():
            preview = "; ".join(m[:40] for m in self.queues.peek(alias)[:3])
            lines.append(f"[{alias}] {size} msg(s): {preview}")
        return "\n".join(lines)

    def _cmd_flush(self, alias: str) -> str:
        if not alias:
            return "Uso: /flush <alias>"
        messages = self.queues.drain(alias)
        if not messages:
            return f"Fila de '{alias}' vazia."
        results = [self._send_to(alias, m) for m in messages]
        return f"Despachadas {len(messages)} mensagem(ns):\n" + "\n".join(results)

    def _cmd_clearqueue(self, alias: str) -> str:
        n = self.queues.clear(alias)
        return f"Fila de '{alias}' limpa ({n} descartadas)."

    def _cmd_status(self, alias: str) -> str:
        alias = alias or self.registry.active
        if not alias:
            return "Nenhum agente ativo. Uso: /status [alias]"
        agent = self.registry.get(alias)
        if not agent:
            return f"Agente '{alias}' nao encontrado."
        if agent.kind == "local":
            if not self.local:
                return "LOCAL_DEVIN_URL nao configurada."
            status = self.local.status()
            return f"[{alias}] local: {status}"
        if not self.devin:
            return "DEVIN_API_KEY nao configurada."
        detail = self.devin.get_session(agent.session_id)
        messages = detail.get("messages", [])
        lines = [
            f"[{alias}] {agent.session_id}",
            f"status: {detail.get('status_enum', '?')}",
            f"mensagens: {len(messages)}",
        ]
        for msg in messages[-3:]:
            text = (msg.get("message") or "")[:200]
            lines.append(f"  ({msg.get('type', '?')}) {text}")
        return "\n".join(lines)

    def _cmd_watch(self, arg: str) -> str:
        parts = arg.split()
        if len(parts) != 2 or parts[1].lower() not in ("on", "off"):
            return "Uso: /watch <alias> on|off"
        alias, mode = parts[0], parts[1].lower()
        if not self.registry.set_watch(alias, mode == "on"):
            return f"Agente '{alias}' nao encontrado."
        return f"watch {mode} para [{alias}]."
