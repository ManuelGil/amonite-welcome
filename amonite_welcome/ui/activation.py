"""Running what an action stands for.

Everything that touches the system when a row is activated lives here: the
capability registry, the URI launcher, and the dialogs shown when either
refuses. Components build rows; this decides what a row does.
"""

from __future__ import annotations

from gi.repository import Gio, GLib, Gtk

from amonite_welcome.content import Action
from amonite_welcome.services import catalog as i18n
from amonite_welcome.services.identity import is_safe_web_url
from amonite_welcome.services.providers import CapabilityUnavailableError, launch


class ActionActivator:
    """Carries out handbook actions on behalf of a window."""

    def __init__(self, window: Gtk.Window):
        self._window = window

    def activate(self, action: Action) -> None:
        if action.url:
            self._open_url(action.url)
        elif action.command:
            self._run_capability(action.command)

    # -- web links -------------------------------------------------------

    def _open_url(self, url: str) -> None:
        if not is_safe_web_url(url):
            self._error(
                i18n.text("dialogs", "open_url_failed", default="Could not open the web page"),
                i18n.text(
                    "dialogs",
                    "disallowed_url",
                    default="Only http and https links can be opened.",
                ),
            )
            return
        launcher = Gtk.UriLauncher(uri=url)
        launcher.launch(self._window, None, self._on_url_opened)

    def _on_url_opened(self, launcher: Gtk.UriLauncher, result) -> None:
        try:
            launcher.launch_finish(result)
        except GLib.Error as error:
            self._error(
                i18n.text("dialogs", "open_url_failed", default="Could not open the web page"),
                error.message,
            )

    # -- capabilities ----------------------------------------------------

    def _run_capability(self, capability: str) -> None:
        """Resolve *capability* again, then start what it resolves to.

        Resolution happens here and not when the row was built: a provider that
        disappeared while the window was open produces a localized message
        instead of a failed launch.
        """
        unavailable = i18n.text(
            "dialogs", "action_unavailable", default="This action is not available"
        )
        try:
            argv = launch(capability)
        except CapabilityUnavailableError as error:
            self._error(unavailable, str(error))
            return
        except ValueError:
            self._error(
                unavailable,
                i18n.text(
                    "dialogs",
                    "unknown_action",
                    default="The handbook refers to an unknown action.",
                ),
            )
            return
        except Exception:
            self._error(
                unavailable,
                i18n.text(
                    "dialogs",
                    "action_prepare_failed",
                    default="Something went wrong while preparing this action.",
                ),
            )
            return

        try:
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            self._error(
                i18n.text("dialogs", "open_action_failed", default="Could not open this action"),
                error.message,
            )

    # -- reporting -------------------------------------------------------

    def _error(self, message: str, detail: str) -> None:
        Gtk.AlertDialog(message=message, detail=detail, modal=True).show(self._window)
