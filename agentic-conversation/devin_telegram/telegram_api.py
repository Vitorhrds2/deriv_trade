import logging

import requests

log = logging.getLogger("telegram")

MAX_MESSAGE_LEN = 4096


class TelegramAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()
        self._offset = 0

    def get_updates(self, timeout: int = 30) -> list[dict]:
        try:
            resp = self.session.get(
                f"{self.base}/getUpdates",
                params={"offset": self._offset, "timeout": timeout},
                timeout=timeout + 10,
            )
            data = resp.json()
        except requests.RequestException as exc:
            log.warning("getUpdates falhou: %s", exc)
            return []
        if not data.get("ok"):
            log.warning("getUpdates erro: %s", data)
            return []
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    def send_message(self, chat_id: str, text: str) -> None:
        for chunk in _split(text):
            try:
                resp = self.session.post(
                    f"{self.base}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                    timeout=30,
                )
                if not resp.json().get("ok"):
                    log.warning("sendMessage erro: %s", resp.text[:300])
            except requests.RequestException as exc:
                log.warning("sendMessage falhou: %s", exc)


def _split(text: str) -> list[str]:
    text = text or "(vazio)"
    return [text[i : i + MAX_MESSAGE_LEN] for i in range(0, len(text), MAX_MESSAGE_LEN)]
