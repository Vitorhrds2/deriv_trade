import logging
import threading
import time

from .devin_api import DevinAPI, DevinAPIError
from .local_agent import LocalAgent, LocalAgentError
from .registry import Agent, Registry
from .telegram_api import TelegramAPI

log = logging.getLogger("watcher")


class Watcher(threading.Thread):
    """Faz polling dos agentes com watch ligado e envia output novo ao chat."""

    def __init__(
        self,
        registry: Registry,
        telegram: TelegramAPI,
        chat_id: str,
        devin: DevinAPI | None,
        local: LocalAgent | None,
        interval: float = 15.0,
    ):
        super().__init__(daemon=True, name="watcher")
        self.registry = registry
        self.telegram = telegram
        self.chat_id = chat_id
        self.devin = devin
        self.local = local
        self.interval = interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            for agent in self.registry.all():
                if not agent.watch:
                    continue
                try:
                    if agent.kind == "cloud":
                        self._poll_cloud(agent)
                    else:
                        self._poll_local(agent)
                except (DevinAPIError, LocalAgentError) as exc:
                    log.warning("watch %s: %s", agent.alias, exc)

    def _poll_cloud(self, agent: Agent) -> None:
        if not self.devin:
            return
        messages = self.devin.get_messages(agent.session_id)
        new = messages[agent.cursor :]
        for msg in new:
            if msg.get("type") == "user_message":
                continue
            text = msg.get("message") or msg.get("text") or str(msg)
            self.telegram.send_message(self.chat_id, f"[{agent.alias}] {text}")
        if new:
            self.registry.set_cursor(agent.alias, len(messages))

    def _poll_local(self, agent: Agent) -> None:
        if not self.local:
            return
        events, cursor = self.local.get_events(since=agent.cursor)
        for event in events:
            text = event.get("message") or str(event)
            self.telegram.send_message(self.chat_id, f"[{agent.alias}] {text}")
        if cursor != agent.cursor:
            self.registry.set_cursor(agent.alias, cursor)
