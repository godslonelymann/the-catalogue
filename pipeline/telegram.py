"""Minimal Telegram Bot API client (standard library only)."""
import json
import logging
import time
import urllib.error
import urllib.request

from .config import CONFIG

log = logging.getLogger(__name__)


class TelegramError(Exception):
    def __init__(self, code, description):
        super().__init__(f"Telegram error {code}: {description}")
        self.code = code
        self.description = description

    @property
    def user_blocked_bot(self):
        # 403: "bot was blocked by the user" / "user is deactivated"
        return self.code == 403


class Telegram:
    def __init__(self, token=None):
        self.token = token if token is not None else CONFIG.telegram_token

    @property
    def enabled(self):
        return bool(self.token)

    def call(self, method, http_timeout=30, **params):
        # The URL holds the token, so it is never logged.
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=http_timeout) as r:
                    return json.loads(r.read())["result"]
            except urllib.error.HTTPError as e:
                body = json.loads(e.read() or b"{}")
                retry = body.get("parameters", {}).get("retry_after")
                if e.code == 429 and retry and attempt < 2:
                    time.sleep(retry)
                    continue
                raise TelegramError(e.code, body.get("description", "")) from None
        raise TelegramError(429, "rate limited")

    def send_message(self, chat_id, text):
        """Send an HTML message. Returns the Telegram message_id."""
        if not self.enabled:
            log.info("[telegram disabled] to %s:\n%s", chat_id, text)
            return None
        result = self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                           link_preview_options={"is_disabled": True})
        return result["message_id"]
