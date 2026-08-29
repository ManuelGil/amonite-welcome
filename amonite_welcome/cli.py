"""Options answered before GTK starts.

Each one reports and exits; none of them opens a window or starts a provider,
so they stay safe to run on a user's installation when reporting a problem.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

USAGE = """Usage: {project} [OPTION]

The Amonite first-run handbook. Without options it opens the window.

  --capabilities   report the session, the terminal, and what each capability
                   resolves to on this system, without starting anything
  --version        print the version of this installation
  -h, --help       print this message

Other options are passed to GTK."""


def run(argv: Sequence[str], pkgdatadir: str, project_name: str) -> int | None:
    """Answer a reporting option, or return None to continue into GTK."""
    if "-h" in argv or "--help" in argv:
        print(USAGE.format(project=project_name))
        return 0

    if "--version" in argv:
        from amonite_welcome import config

        print(f"{project_name} {config.VERSION}")
        return 0

    if "--capabilities" in argv:
        os.environ.setdefault("AMONITE_WELCOME_PKGDATADIR", pkgdatadir)
        from amonite_welcome.services import providers

        report = providers.diagnose()
        width = max(len(name) for name, _ in report)
        for name, resolution in report:
            print(f"{name:{width}}  {resolution}")
        return 0

    return None
