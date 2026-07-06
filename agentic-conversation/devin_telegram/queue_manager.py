import json
import threading
import time
from pathlib import Path


class QueueManager:
    """Filas de mensagens por agente, persistidas em state/queues.json."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / "queues.json"
        self._lock = threading.Lock()
        self.queues: dict[str, list[dict]] = {}
        if self.path.exists():
            self.queues = json.loads(self.path.read_text())

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.queues, indent=2))

    def enqueue(self, alias: str, message: str) -> int:
        with self._lock:
            queue = self.queues.setdefault(alias, [])
            queue.append({"message": message, "ts": time.time()})
            self._save()
            return len(queue)

    def drain(self, alias: str) -> list[str]:
        with self._lock:
            items = self.queues.pop(alias, [])
            self._save()
            return [item["message"] for item in items]

    def clear(self, alias: str) -> int:
        with self._lock:
            n = len(self.queues.pop(alias, []))
            self._save()
            return n

    def sizes(self) -> dict[str, int]:
        return {alias: len(q) for alias, q in self.queues.items() if q}

    def peek(self, alias: str) -> list[str]:
        return [item["message"] for item in self.queues.get(alias, [])]
