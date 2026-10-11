"""ICE servers for voice chat: public STUN plus time-limited TURN credentials.

TURN credentials follow coturn's ``use-auth-secret`` scheme (the "TURN REST
API"): the username is ``<expiry unix time>:<player id>`` and the password is
``base64(HMAC-SHA1(secret, username))``. coturn checks both with the same
shared secret, so nothing has to be stored on either side.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_STUN = ("stun:stun.l.google.com:19302",)


@dataclass
class IceConfig:
    stun_urls: tuple[str, ...] = DEFAULT_STUN
    turn_urls: tuple[str, ...] = ()
    turn_secret: str = ""
    # How long credentials stay valid, in seconds. Calls that are already
    # connected keep working past the expiry; only new allocations fail.
    ttl: int = 12 * 3600
    clock: Callable[[], float] = field(default=time.time)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> IceConfig:
        """Read ``WILDJOKER_STUN_URLS``, ``WILDJOKER_TURN_URLS`` (comma-separated),
        ``WILDJOKER_TURN_SECRET`` and ``WILDJOKER_TURN_TTL``."""
        env = os.environ if env is None else env

        def urls(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            value = env.get(name)
            if value is None:
                return default
            return tuple(u.strip() for u in value.split(",") if u.strip())

        return cls(
            stun_urls=urls("WILDJOKER_STUN_URLS", DEFAULT_STUN),
            turn_urls=urls("WILDJOKER_TURN_URLS", ()),
            turn_secret=env.get("WILDJOKER_TURN_SECRET", ""),
            ttl=int(env.get("WILDJOKER_TURN_TTL", 12 * 3600)),
        )

    @property
    def turn_enabled(self) -> bool:
        return bool(self.turn_urls and self.turn_secret)

    def servers(self, user: str) -> dict[str, Any]:
        """The ``RTCIceServer`` list for ``user``, and how long it is valid."""
        servers: list[dict[str, Any]] = []
        if self.stun_urls:
            servers.append({"urls": list(self.stun_urls)})
        if self.turn_enabled:
            username, credential = turn_credentials(
                self.turn_secret, user, int(self.clock()) + self.ttl
            )
            servers.append(
                {"urls": list(self.turn_urls), "username": username, "credential": credential}
            )
        return {"ice_servers": servers, "ttl": self.ttl}


def turn_credentials(secret: str, user: str, expiry: int) -> tuple[str, str]:
    username = f"{expiry}:{user}"
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return username, base64.b64encode(digest).decode()
