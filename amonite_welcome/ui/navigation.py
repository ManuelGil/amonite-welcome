"""The table of contents.

Owns the chapter rows and the mapping from a row to a page id. Selection is
reported by page id, so navigation does not depend on translated titles and the
window can key its stack on something stable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from gi.repository import Gtk

from amonite_welcome.content import Page
from amonite_welcome.services import catalog as i18n
from amonite_welcome.ui import a11y, components


class Navigation:
    """Fills a ``Gtk.ListBox`` with chapters and reports selection."""

    def __init__(self, listbox: Gtk.ListBox, on_selected: Callable[[str], None]):
        self._listbox = listbox
        self._on_selected = on_selected
        a11y.name(listbox, i18n.text("ui", "sidebar_label", default="Chapters"))
        listbox.connect("row-selected", self._on_row_selected)

    def populate(self, pages: Sequence[Page]) -> None:
        for position, page in enumerate(pages, start=1):
            self._listbox.append(components.chapter_row(position, page.id, page.title))
        self.select_index(0)

    def select_index(self, index: int) -> None:
        row = self._listbox.get_row_at_index(index)
        if row is not None:
            self._listbox.select_row(row)

    def grab_focus(self) -> None:
        self._listbox.grab_focus()

    def _on_row_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is not None:
            self._on_selected(row.page_id)
