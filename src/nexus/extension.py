"""IPython extension entry points: ``%load_ext nexus`` / ``%unload_ext nexus``."""

from __future__ import annotations

import logging
import weakref
from typing import Any

from nexus.magics import NexusMagics
from nexus.session import NexusSession

log = logging.getLogger("nexus")

_sessions: weakref.WeakKeyDictionary[Any, NexusSession] = weakref.WeakKeyDictionary()


def get_session(shell: Any) -> NexusSession | None:
    """The session loaded into ``shell``, if any."""
    return _sessions.get(shell)


def load_ipython_extension(ip: Any) -> None:
    if ip in _sessions:
        return
    session = NexusSession(ip)
    ip.register_magics(NexusMagics(ip, session))
    ip.events.register("pre_run_cell", session.pre_run_cell)
    ip.events.register("post_run_cell", session.post_run_cell)
    _sessions[ip] = session


def unload_ipython_extension(ip: Any) -> None:
    session = _sessions.pop(ip, None)
    if session is None:
        return
    for event, callback in (
        ("pre_run_cell", session.pre_run_cell),
        ("post_run_cell", session.post_run_cell),
    ):
        try:
            ip.events.unregister(event, callback)
        except ValueError:
            log.debug("nexus: %s hook was not registered", event)
    ip.magics_manager.magics.get("line", {}).pop("nexus", None)
