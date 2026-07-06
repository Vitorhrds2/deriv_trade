import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    devin_api_key: str = ""
    devin_api_base: str = "https://api.devin.ai/v1"
    local_devin_url: str = ""
    relay_token: str = ""
    state_dir: Path = field(default_factory=lambda: Path("./state"))
    poll_interval: float = 15.0

    @classmethod
    def from_env(cls) -> "Config":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise SystemExit(
                "TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID sao obrigatorios "
                "(veja .env.example)."
            )
        cfg = cls(
            telegram_bot_token=token,
            telegram_chat_id=str(chat_id),
            devin_api_key=os.environ.get("DEVIN_API_KEY", ""),
            devin_api_base=os.environ.get(
                "DEVIN_API_BASE", "https://api.devin.ai/v1"
            ).rstrip("/"),
            local_devin_url=os.environ.get("LOCAL_DEVIN_URL", "").rstrip("/"),
            relay_token=os.environ.get("RELAY_TOKEN", ""),
            state_dir=Path(os.environ.get("STATE_DIR", "./state")),
            poll_interval=float(os.environ.get("POLL_INTERVAL", "15")),
        )
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        return cfg
