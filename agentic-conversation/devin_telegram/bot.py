import logging

from .config import Config
from .devin_api import DevinAPI
from .local_agent import LocalAgent
from .queue_manager import QueueManager
from .registry import Registry
from .router import Router
from .telegram_api import TelegramAPI
from .watcher import Watcher

log = logging.getLogger("bot")


class Bot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.telegram = TelegramAPI(cfg.telegram_bot_token)
        self.devin = DevinAPI(cfg.devin_api_key, cfg.devin_api_base) if cfg.devin_api_key else None
        self.local = LocalAgent(cfg.local_devin_url, cfg.relay_token) if cfg.local_devin_url else None
        self.registry = Registry(cfg.state_dir)
        self.queues = QueueManager(cfg.state_dir)
        self.router = Router(self.registry, self.queues, self.devin, self.local)
        self.watcher = Watcher(
            self.registry, self.telegram, cfg.telegram_chat_id,
            self.devin, self.local, cfg.poll_interval,
        )

    def run(self) -> None:
        log.info("Bot iniciado. Chat autorizado: %s", self.cfg.telegram_chat_id)
        self.watcher.start()
        self.telegram.send_message(
            self.cfg.telegram_chat_id,
            "Devin/Telegram bridge online. /help para comandos.",
        )
        while True:
            for update in self.telegram.get_updates():
                self._handle_update(update)

    def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat_id = str(message.get("chat", {}).get("id", ""))
        if chat_id != self.cfg.telegram_chat_id:
            log.warning("Mensagem de chat nao autorizado ignorada: %s", chat_id)
            return
        text = message.get("text", "")
        reply = self.router.handle(text)
        if reply:
            self.telegram.send_message(chat_id, reply)
