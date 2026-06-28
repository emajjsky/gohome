from __future__ import annotations

from typing import Any, Dict
from urllib import parse, request
import json


class Notifier:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def send(self, title: str, body: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        channel = self.settings.notify_channel
        payload_extra = extra or {}

        if channel == "off":
            return {"sent": False, "channel": "off", "reason": "notification channel is off"}

        if channel == "webhook":
            return self._send_webhook(title, body, payload_extra)
        if channel == "feishu":
            return self._send_feishu(title, body, payload_extra)
        if channel == "bark":
            return self._send_bark(title, body, payload_extra)
        if channel == "telegram":
            return self._send_telegram(title, body, payload_extra)

        return {"sent": False, "channel": channel, "reason": "unsupported notification channel"}

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not url:
            return {"sent": False, "reason": "missing webhook url"}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=8) as response:
                return {
                    "sent": 200 <= response.status < 300,
                    "status": response.status,
                    "body": response.read().decode("utf-8", errors="ignore")[:500],
                }
        except Exception as exc:
            return {"sent": False, "reason": str(exc)}

    def _send_webhook(self, title: str, body: str, extra: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"title": title, "body": body, "extra": extra}
        result = self._post_json(self.settings.generic_webhook_url, payload)
        result["channel"] = "webhook"
        return result

    def _send_feishu(self, title: str, body: str, extra: Dict[str, Any]) -> Dict[str, Any]:
        text = f"{title}\n{body}"
        if extra:
            text += "\n" + json.dumps(extra, ensure_ascii=False)
        payload = {"msg_type": "text", "content": {"text": text}}
        result = self._post_json(self.settings.feishu_webhook, payload)
        result["channel"] = "feishu"
        return result

    def _send_bark(self, title: str, body: str, extra: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"title": title, "body": body, "group": "想家了吗", "extra": extra}
        result = self._post_json(self.settings.bark_url, payload)
        result["channel"] = "bark"
        return result

    def _send_telegram(self, title: str, body: str, extra: Dict[str, Any]) -> Dict[str, Any]:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return {"sent": False, "channel": "telegram", "reason": "missing telegram token or chat id"}

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        text = f"{title}\n{body}"
        if extra:
            text += "\n" + json.dumps(extra, ensure_ascii=False)
        data = parse.urlencode({"chat_id": self.settings.telegram_chat_id, "text": text}).encode("utf-8")
        req = request.Request(url, data=data, method="POST")
        try:
            with request.urlopen(req, timeout=8) as response:
                return {
                    "sent": 200 <= response.status < 300,
                    "channel": "telegram",
                    "status": response.status,
                    "body": response.read().decode("utf-8", errors="ignore")[:500],
                }
        except Exception as exc:
            return {"sent": False, "channel": "telegram", "reason": str(exc)}
