"""Accessible semantics, in one vocabulary.

GTK4 makes ``accessible-role`` construct-only: assigning it after a widget
exists does not stay on the instance, and under GTK 4.14 the assignment reaches
every widget of that class, so one late call can turn every heading in the
window into ordinary text. Components therefore pass a role *into* the
constructor, and the only helpers here are the ones GTK does allow at runtime:
the accessible name and the heading level.

Prose uses LABEL rather than PARAGRAPH: GTK 4.14 and AT-SPI keep the visible
string as the accessible name for LABEL, while PARAGRAPH nodes were nameless.
"""

from __future__ import annotations

from gi.repository import Gtk

HEADING = Gtk.AccessibleRole.HEADING
PARAGRAPH = Gtk.AccessibleRole.LABEL
DECORATIVE = Gtk.AccessibleRole.PRESENTATION


def name(widget: Gtk.Widget, text: str) -> None:
    """Expose a human-readable accessible name."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [text])


def describe(widget: Gtk.Widget, text: str) -> None:
    """Expose a secondary accessible description."""
    widget.update_property([Gtk.AccessibleProperty.DESCRIPTION], [text])


def heading_level(widget: Gtk.Widget, level: int) -> None:
    """Give a heading its depth. The role itself comes from construction."""
    widget.update_property([Gtk.AccessibleProperty.LEVEL], [level])
