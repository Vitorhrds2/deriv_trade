import logging

import requests

log = logging.getLogger("local_agent")


class LocalAgentError(RuntimeError):
    pass


class LocalAgent:
    """Adapter para o Devin Local (Macbook) atraves do local_relay.py.

    O relay expoe:
      POST /message         {"message": ...}  -> grava na inbox local
      GET  /events?since=N  -> {"events": [...], "cursor": M}  outputs novos
      GET  /status          -> {"status": ..., "pending": N}
    """

    def __init__(self, base_url: str, token: str = ""):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self.session.request(
                method, f"{self.base}{path}", timeout=30, **kwargs
            )
        except requests.RequestException as exc:
            raise LocalAgentError(f"Relay local inacessivel: {exc}") from exc
        if resp.status_code >= 400:
            raise LocalAgentError(f"Relay {resp.status_code}: {resp.text[:200]}")
        return resp.json() if resp.text else {}

    def send_message(self, message: str) -> dict:
        return self._request("POST", "/message", json={"message": message})

    def get_events(self, since: int = 0) -> tuple[list[dict], int]:
        data = self._request("GET", "/events", params={"since": since})
        return data.get("events", []), data.get("cursor", since)

    def status(self) -> dict:
        return self._request("GET", "/status")
