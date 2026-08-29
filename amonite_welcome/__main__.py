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

"""Module entry point for ``python3 -m amonite_welcome`` under meson devenv."""

from __future__ import annotations

import os
import signal
import sys


def _main() -> int:
    pkgdatadir = os.environ.get("AMONITE_WELCOME_PKGDATADIR", "")
    if not pkgdatadir:
        print(
            "amonite-welcome: AMONITE_WELCOME_PKGDATADIR is unset.\n"
            "Run inside ``meson devenv -C builddir``, or use the installed "
            "``amonite-welcome`` launcher.",
            file=sys.stderr,
        )
        return 1

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio

    # Load config alone first - importing app pulls in the window, which
    # requires the GResource to already be registered (same order as the launcher).
    from amonite_welcome import config

    resource = Gio.Resource.load(
        os.path.join(pkgdatadir, f"{config.PROJECT_NAME}.gresource")
    )
    resource._register()

    from amonite_welcome import app

    return app.main(pkgdatadir)


if __name__ == "__main__":
    sys.exit(_main())
