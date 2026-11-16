"""``%nexus`` line magic."""

from __future__ import annotations

from typing import Any

from IPython.core.magic import Magics, line_magic, magics_class

from nexus.session import NexusSession

USAGE = "usage: %nexus [status | on | off | verbose on|off]"


@magics_class
class NexusMagics(Magics):
    def __init__(self, shell: Any, session: NexusSession) -> None:
        super().__init__(shell)
        self._session = session

    @line_magic
    def nexus(self, line: str) -> None:
        """Control NEXUS: ``%nexus status``, ``%nexus on|off``, ``%nexus verbose on|off``."""
        words = line.split()
        s = self._session
        if not words or words == ["status"]:
            print(s.status())
        elif words in (["on"], ["off"]):
            s.enabled = words[0] == "on"
            print(s.status())
        elif len(words) == 2 and words[0] == "verbose" and words[1] in ("on", "off"):
            s.verbose = words[1] == "on"
            print(s.status())
        else:
            print(USAGE)
