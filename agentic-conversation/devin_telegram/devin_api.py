import logging
from typing import Any

import requests

log = logging.getLogger("devin_api")


class DevinAPIError(RuntimeError):
    pass


class DevinAPI:
    """Cliente minimo da Devin Cloud API (https://docs.devin.ai/api-reference)."""

    def __init__(self, api_key: str, base_url: str = "https://api.devin.ai/v1"):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            resp = self.session.request(
                method, f"{self.base}{path}", timeout=60, **kwargs
            )
        except requests.RequestException as exc:
            raise DevinAPIError(f"Falha de rede na Devin API: {exc}") from exc
        if resp.status_code >= 400:
            raise DevinAPIError(
                f"Devin API {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json() if resp.text else {}

    def create_session(self, prompt: str, *, idempotent: bool = False) -> dict:
        """Cria uma sessao. Retorna {'session_id': ..., 'url': ...}."""
        return self._request(
            "POST", "/sessions", json={"prompt": prompt, "idempotent": idempotent}
        )

    def list_sessions(self, limit: int = 20) -> list[dict]:
        data = self._request("GET", "/sessions", params={"limit": limit})
        return data.get("sessions", data if isinstance(data, list) else [])

    def get_session(self, session_id: str) -> dict:
        return self._request("GET", f"/session/{session_id}")

    def send_message(self, session_id: str, message: str) -> dict:
        return self._request(
            "POST", f"/session/{session_id}/message", json={"message": message}
        )

    def get_messages(self, session_id: str) -> list[dict]:
        detail = self.get_session(session_id)
        return detail.get("messages", [])
