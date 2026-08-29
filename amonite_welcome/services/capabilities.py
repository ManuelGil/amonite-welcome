"""Which handbook actions this system can actually carry out.

The registry (:mod:`services.providers`) answers *what a capability resolves
to*. This module answers *whether the handbook should offer it*. Presentation
asks here and never resolves a provider itself.
"""

from __future__ import annotations

from collections.abc import Iterable

from amonite_welcome.content import Action
from amonite_welcome.services import providers


def is_available(action: Action) -> bool:
    """Whether *action* can be carried out on this system right now."""
    if action.url:
        return True
    return bool(action.command) and providers.available(action.command)


def visible_actions(actions: Iterable[Action]) -> list[Action]:
    """Return the actions this system can actually carry out.

    An action whose capability has no provider here is left out rather than
    offered and refused: the handbook should not point at a tool the system
    does not have. Availability is read while the page is built, so a system
    the user changes later is described by the state it was in when Welcome
    started, and activation resolves again, keeping the localized message for a
    provider that disappears while the window is open.
    """
    return [action for action in actions if is_available(action)]
