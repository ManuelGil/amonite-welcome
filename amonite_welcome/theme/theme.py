"""Installing the visual system.

One CSS provider, composed in a fixed order:

    colours derived from the desktop  ->  component rules  ->  distribution override

Welcome does not decide what the system looks like. It reads what the desktop
publishes, makes it readable, and hands the result to the stylesheet as
semantic names. A distribution that wants something else drops a single file,
``<pkgdatadir>/theme/distro.css``, which is appended last and can redefine any
of those names without touching a component or a line of Python.
"""

from __future__ import annotations

import os

from gi.repository import Gdk, Gio, Gtk

from amonite_welcome import config
from amonite_welcome.theme import palette, system

_COMPONENTS = "theme/components.css"
_OVERRIDE_NAME = os.path.join("theme", "distro.css")


def _components_css() -> str:
    path = f"{config.RESOURCE_BASE_PATH}/{_COMPONENTS}"
    data = Gio.resources_lookup_data(path, Gio.ResourceLookupFlags.NONE)
    return data.get_data().decode("utf-8")


class Theme:
    """Keeps one display's stylesheet in step with the desktop."""

    def __init__(self, pkgdatadir: str, os_release: dict[str, str] | None = None):
        self._provider = Gtk.CssProvider()
        self._os_release = os_release or {}
        self._override = self._find_override(pkgdatadir)
        self._settings = Gtk.Settings.get_default()
        self._probe = Gtk.Window()
        self.tokens: dict[str, str] = {}
        self.source = ""

    @staticmethod
    def _find_override(pkgdatadir: str) -> str:
        # A fixed name under the package data directory: nothing outside the
        # installation can name this file.
        if not pkgdatadir:
            return ""
        path = os.path.join(pkgdatadir, _OVERRIDE_NAME)
        return path if os.path.isfile(path) else ""

    @property
    def override_path(self) -> str:
        """The distribution override in use, or empty when there is none."""
        return self._override

    def resolve(self) -> dict[str, str]:
        """Read the desktop and derive the palette Welcome will draw with."""
        colours = system.read(self._probe, self._os_release)
        self.source = colours.source
        self.tokens = palette.derive(colours)
        return self.tokens

    def stylesheet(self) -> str:
        sheets = [palette.stylesheet(self.resolve()), _components_css()]
        if self._override:
            try:
                with open(self._override, encoding="utf-8") as handle:
                    sheets.append(handle.read())
            except OSError:
                # A broken override must never keep the window from opening.
                self._override = ""
        return "\n".join(sheets)

    def install(self, display: Gdk.Display | None = None) -> None:
        """Add the stylesheet to *display* and follow appearance changes."""
        display = display or Gdk.Display.get_default()
        if display is None:
            return
        self._load()
        Gtk.StyleContext.add_provider_for_display(
            display, self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        if self._settings is not None:
            for property_name in (
                "notify::gtk-application-prefer-dark-theme",
                "notify::gtk-theme-name",
            ):
                self._settings.connect(property_name, lambda *_: self._load())

    def _load(self) -> None:
        self._provider.load_from_string(self.stylesheet())
