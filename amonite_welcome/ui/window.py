"""The application shell.

Header, chapter list, page stack, footer. The window arranges these and owns
the startup preference; it does not build page content, resolve a capability,
or run an action.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gi.repository import Gtk

from amonite_welcome import config
from amonite_welcome.content import Page
from amonite_welcome.services import autostart
from amonite_welcome.services import catalog as i18n
from amonite_welcome.ui import components
from amonite_welcome.ui.activation import ActionActivator
from amonite_welcome.ui.navigation import Navigation
from amonite_welcome.ui.page_view import PageView

# Canonical presentation geometry (logical pixels). GTK owns scaling and
# placement; the application only suggests a size and an accessibility floor.
#
# GTK4 removed gtk_window_set_position() / GTK_WIN_POS_CENTER with no portable
# replacement (Wayland cannot expose global coordinates). Freedesktop EWMH
# (_NET_WM_FULL_PLACEMENT) likewise expects the compositor to place windows.
# Do not add monitor, pointer, or backend heuristics here.
_MIN_WIDTH = 800
_MIN_HEIGHT = 600
_PREFERRED_WIDTH = 940
_PREFERRED_HEIGHT = 660


@Gtk.Template(resource_path=f"{config.RESOURCE_BASE_PATH}/ui/window.ui")
class WelcomeWindow(Gtk.ApplicationWindow):
    __gtype_name__ = "WelcomeWindow"

    header_bar: Gtk.HeaderBar = Gtk.Template.Child()
    sidebar: Gtk.ListBox = Gtk.Template.Child()
    stack: Gtk.Stack = Gtk.Template.Child()
    autostart_button: Gtk.CheckButton = Gtk.Template.Child()
    distro_footer_label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, pages: Sequence[Page], identity: Mapping[str, str], **kwargs):
        super().__init__(**kwargs)
        self.identity = identity
        self.add_css_class("welcome-window")

        self.set_title(f"{identity['distro_name']} {identity['app_name']}")
        self.set_icon_name(config.PROJECT_NAME)
        # Accessibility floor; GTK/compositor may still enlarge beyond this.
        self.set_size_request(_MIN_WIDTH, _MIN_HEIGHT)
        # Preferred initial size only. Placement is compositor policy via present().
        self.set_default_size(_PREFERRED_WIDTH, _PREFERRED_HEIGHT)

        self._build_branding(identity)
        self.distro_footer_label.set_label(identity["release_label"])

        page_view = PageView(ActionActivator(self))
        for page in pages:
            self.stack.add_named(page_view.build(page), page.id)

        self.navigation = Navigation(self.sidebar, self._show_page)
        self.navigation.populate(pages)
        # Initial focus follows visual entry: the chapter list.
        self.navigation.grab_focus()

        self._setup_autostart(identity)

    def _build_branding(self, identity: Mapping[str, str]) -> None:
        """The distribution's name and mark, once, where a title would be."""
        brand = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        mark = Gtk.Image(
            icon_name=config.PROJECT_NAME, accessible_role=Gtk.AccessibleRole.PRESENTATION
        )
        mark.set_pixel_size(20)
        brand.append(mark)
        name = Gtk.Label(label=identity["distro_name"], xalign=0)
        name.add_css_class("brand-name")
        brand.append(name)
        self.header_bar.set_title_widget(brand)

    def _show_page(self, page_id: str) -> None:
        self.stack.set_visible_child_name(page_id)

    # -- startup preference ----------------------------------------------

    def _setup_autostart(self, identity: Mapping[str, str]) -> None:
        self.autostart_button.set_label(
            i18n.text("ui", "autostart_label", default="Show this window on startup")
        )
        # Default is enabled; block the toggled handler while applying state.
        self._autostart_ready = False
        self.autostart_button.set_active(autostart.is_enabled())
        self._autostart_ready = True
        if self.autostart_button.get_active():
            # Materialize a user entry when no system autostart is installed
            # (development prefix); packaged installs rely on /etc/xdg/autostart.
            self._apply_autostart(True)

    @Gtk.Template.Callback()
    def on_autostart_toggled(self, button: Gtk.CheckButton) -> None:
        if not getattr(self, "_autostart_ready", False):
            return
        self._apply_autostart(button.get_active())

    def _apply_autostart(self, enabled: bool) -> None:
        try:
            autostart.set_enabled(enabled, self.identity["app_name"])
        except OSError as error:
            Gtk.AlertDialog(
                message=i18n.text(
                    "dialogs",
                    "autostart_failed",
                    default="Could not change the startup setting",
                ),
                detail=str(error),
                modal=True,
            ).show(self)
