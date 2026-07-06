import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Agent:
    alias: str
    kind: str  # "cloud" | "local"
    session_id: str = ""  # sessoes cloud
    url: str = ""  # url da sessao (cloud) ou do relay (local)
    watch: bool = False
    cursor: int = 0  # cursor de eventos (local) / n. de mensagens vistas (cloud)

    def label(self) -> str:
        target = self.session_id or self.url or "-"
        return f"{self.alias} [{self.kind}] {target}"


class Registry:
    """Registro persistente de agentes (state/registry.json)."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / "registry.json"
        self._lock = threading.Lock()
        self.agents: dict[str, Agent] = {}
        self.active: str = ""
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text())
        self.active = data.get("active", "")
        self.agents = {
            alias: Agent(**info) for alias, info in data.get("agents", {}).items()
        }

    def _save(self) -> None:
        payload = {
            "active": self.active,
            "agents": {alias: asdict(a) for alias, a in self.agents.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2))

    def add(self, agent: Agent) -> None:
        with self._lock:
            self.agents[agent.alias] = agent
            if not self.active:
                self.active = agent.alias
            self._save()

    def remove(self, alias: str) -> bool:
        with self._lock:
            if alias not in self.agents:
                return False
            del self.agents[alias]
            if self.active == alias:
                self.active = next(iter(self.agents), "")
            self._save()
            return True

    def get(self, alias: str) -> Agent | None:
        return self.agents.get(alias)

    def set_active(self, alias: str) -> bool:
        with self._lock:
            if alias not in self.agents:
                return False
            self.active = alias
            self._save()
            return True

    def set_watch(self, alias: str, watch: bool) -> bool:
        with self._lock:
            agent = self.agents.get(alias)
            if not agent:
                return False
            agent.watch = watch
            self._save()
            return True

    def set_cursor(self, alias: str, cursor: int) -> None:
        with self._lock:
            agent = self.agents.get(alias)
            if agent:
                agent.cursor = cursor
                self._save()

    def all(self) -> list[Agent]:
        return list(self.agents.values())

    def next_alias(self, prefix: str = "devin") -> str:
        n = 1
        while f"{prefix}-{n}" in self.agents:
            n += 1
        return f"{prefix}-{n}"
