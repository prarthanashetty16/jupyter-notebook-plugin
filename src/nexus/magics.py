"""``%nexus`` line magic: status, explain, suggestions, apply (text only; never runs or edits a cell)."""

from __future__ import annotations

import logging
from typing import Any

from IPython.core.magic import Magics, line_magic, magics_class

from nexus.session import NexusSession

log = logging.getLogger("nexus")
USAGE = "usage: %nexus [status | on | off | verbose on|off | explain | suggestions | apply <n> | rule enable|disable <name>]"


@magics_class
class NexusMagics(Magics):
    def __init__(self, shell: Any, session: NexusSession) -> None:
        super().__init__(shell)
        self._session = session

    @line_magic
    def nexus(self, line: str) -> None:
        """Control NEXUS: ``%nexus status``, ``on|off``, ``verbose on|off``, ``explain``,
        ``suggestions``, ``apply <n>`` (prints the modified source; nothing is executed),
        ``rule enable|disable <name>`` (opt in to a rule that is off by default)."""
        words = line.split()
        s = self._session
        try:
            if not words or words == ["status"]:
                print(s.status())
            elif words in (["on"], ["off"]):
                s.enabled = words[0] == "on"
                print(s.status())
            elif len(words) == 2 and words[0] == "verbose" and words[1] in ("on", "off"):
                s.verbose = words[1] == "on"
                print(s.status())
            elif words == ["explain"]:
                print(s.explain())
            elif words == ["suggestions"]:
                print(s.show_suggestions(self.shell.user_ns))
            elif len(words) == 3 and words[0] == "rule" and words[1] in ("enable", "disable"):
                print(s.set_rule(words[2], words[1] == "enable"))
            elif len(words) == 2 and words[0] == "apply" and words[1].isdigit():
                print(s.apply(int(words[1])))
            else:
                print(USAGE)
        except Exception:
            log.debug("nexus: magic failed", exc_info=True)
            print("[nexus] could not complete that command")
