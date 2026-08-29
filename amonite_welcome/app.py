"""Application lifecycle: load, theme, present.

Everything that happens once per run and nothing that happens per page.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from amonite_welcome import config
from amonite_welcome.content import PagesError, load_pages_for_locale
from amonite_welcome.services import catalog as i18n
from amonite_welcome.services import identity as identity_api
from amonite_welcome.services.catalog import StringsError, load_strings_for_locale
from amonite_welcome.services.identity import (
    IdentityError,
    load_identity,
    read_os_release,
)
from amonite_welcome.theme import Theme


class WelcomeApplication(Gtk.Application):
    def __init__(self, pkgdatadir: str):
        super().__init__(
            application_id=config.APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.pkgdatadir = pkgdatadir
        self._theme: Theme | None = None

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            # Imported lazily so ``python3 -m amonite_welcome`` can register the
            # GResource before Gtk.Template validates window.ui.
            from amonite_welcome.ui.window import WelcomeWindow

            try:
                identity = load_identity(self.pkgdatadir)
                i18n.bind(load_strings_for_locale(self.pkgdatadir))
                identity_api.bind(identity)
                pages = load_pages_for_locale(self.pkgdatadir, identity)
            except (IdentityError, PagesError, StringsError) as error:
                self._report_startup_error(str(error))
                return

            # The desktop decides the palette; os-release is only consulted
            # when the theme publishes no accent of its own.
            self._theme = Theme(self.pkgdatadir, dict(read_os_release()))
            self._theme.install()
            window = WelcomeWindow(pages, identity, application=self)
        # Canonical GTK4 show path. Placement (including any centering) is
        # decided by GTK and the compositor; no portable centering API exists.
        window.present()

    def _report_startup_error(self, detail: str) -> None:
        print(f"{config.PROJECT_NAME}: {detail}", file=sys.stderr)
        dialog = Gtk.AlertDialog(
            message=i18n.text("dialogs", "startup_failed", default="Welcome cannot start"),
            detail=detail,
            modal=True,
        )
        self.hold()
        dialog.choose(None, None, lambda d, result: self.release())


def main(pkgdatadir: str) -> int:
    return WelcomeApplication(pkgdatadir).run(sys.argv)
