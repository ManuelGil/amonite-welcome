# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Application entry point."""

import os
import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, Gtk

from amonite_welcome import config
from amonite_welcome import identity as identity_api
from amonite_welcome import strings as i18n
from amonite_welcome.identity import IdentityError, load_identity
from amonite_welcome.pages import PagesError, load_pages_for_locale
from amonite_welcome.strings import StringsError, load_strings_for_locale


class WelcomeApplication(Gtk.Application):
    def __init__(self, pkgdatadir: str):
        super().__init__(
            application_id=config.APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.pkgdatadir = pkgdatadir

    def do_startup(self):
        Gtk.Application.do_startup(self)

        css = Gtk.CssProvider()
        css.load_from_resource(f"{config.RESOURCE_BASE_PATH}/style.css")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            # Imported lazily so ``python3 -m amonite_welcome.main`` can register
            # the GResource before Gtk.Template validates window.ui.
            from amonite_welcome.window import WelcomeWindow

            try:
                identity = load_identity(self.pkgdatadir)
                i18n.bind(load_strings_for_locale(self.pkgdatadir))
                identity_api.bind(identity)
                pages = load_pages_for_locale(self.pkgdatadir, identity)
            except (IdentityError, PagesError, StringsError) as error:
                self._report_startup_error(str(error))
                return
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
    app = WelcomeApplication(pkgdatadir)
    return app.run(sys.argv)


if __name__ == "__main__":
    from amonite_welcome.__main__ import _main

    raise SystemExit(_main())
