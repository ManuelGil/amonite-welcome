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

"""The main window: a sidebar of chapters and a stack of prose pages."""

from collections.abc import Mapping

from gi.repository import Gio, GLib, Gtk

from amonite_welcome import autostart, config, system_info
from amonite_welcome import strings as i18n
from amonite_welcome.actions import CapabilityUnavailableError, launch
from amonite_welcome.pages import Action, Page, Section
from amonite_welcome.system_info import Fact

# Comfortable reading measure (~60–75 characters).
_PROSE_WIDTH_CHARS = 68

# Canonical presentation geometry (logical pixels). GTK owns scaling and
# placement; the application only suggests size and an accessibility floor.
#
# GTK4 removed gtk_window_set_position() / GTK_WIN_POS_CENTER with no portable
# replacement (Wayland cannot expose global coordinates). Freedesktop EWMH
# (_NET_WM_FULL_PLACEMENT) likewise expects the compositor to place windows.
# Do not add monitor, pointer, or backend heuristics here.
_MIN_WIDTH = 800
_MIN_HEIGHT = 600
_PREFERRED_WIDTH = 960
_PREFERRED_HEIGHT = 700


def _set_accessible_label(widget: Gtk.Widget, label: str) -> None:
    """Expose a human-readable accessible name via GTK."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


def _set_heading(widget: Gtk.Widget, level: int) -> None:
    """Mark a label as a heading for assistive technologies."""
    widget.set_accessible_role(Gtk.AccessibleRole.HEADING)
    widget.update_property([Gtk.AccessibleProperty.LEVEL], [level])


def _set_paragraph(widget: Gtk.Widget) -> None:
    """Expose prose as a labelled paragraph, not a heading."""
    # Prefer LABEL over PARAGRAPH: GTK 4.14+AT-SPI keeps the visible
    # string as the accessible name for LABEL; PARAGRAPH nodes were nameless.
    widget.set_accessible_role(Gtk.AccessibleRole.LABEL)


def _mark_decorative(widget: Gtk.Widget) -> None:
    """Hide decorative imagery from the accessibility tree."""
    widget.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)


@Gtk.Template(resource_path=f"{config.RESOURCE_BASE_PATH}/ui/window.ui")
class WelcomeWindow(Gtk.ApplicationWindow):
    __gtype_name__ = "WelcomeWindow"

    header_bar: Gtk.HeaderBar = Gtk.Template.Child()
    sidebar: Gtk.ListBox = Gtk.Template.Child()
    stack: Gtk.Stack = Gtk.Template.Child()
    autostart_button: Gtk.CheckButton = Gtk.Template.Child()
    distro_footer_label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, pages: list[Page], identity: Mapping[str, str], **kwargs):
        super().__init__(**kwargs)
        self.identity = identity

        self.set_title(f"{identity['distro_name']} {identity['app_name']}")
        self.set_icon_name(config.PROJECT_NAME)
        # Accessibility floor; GTK/compositor may still enlarge beyond this.
        self.set_size_request(_MIN_WIDTH, _MIN_HEIGHT)
        # Preferred initial size only. Placement is compositor policy via present().
        self.set_default_size(_PREFERRED_WIDTH, _PREFERRED_HEIGHT)
        self._build_header_branding(identity)
        self.distro_footer_label.set_label(identity["release_label"])
        _set_accessible_label(
            self.sidebar,
            i18n.text("ui", "sidebar_label", default="Chapters"),
        )

        for page in pages:
            self.sidebar.append(self._build_sidebar_row(page))
            self.stack.add_named(self._build_page(page), page.title)
        first_row = self.sidebar.get_row_at_index(0)
        self.sidebar.select_row(first_row)
        # Initial focus follows visual entry: chapter list.
        self.sidebar.grab_focus()

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
            try:
                autostart.set_enabled(True, identity["app_name"])
            except OSError as error:
                self._show_error(
                    i18n.text(
                        "dialogs",
                        "autostart_failed",
                        default="Could not change the startup setting",
                    ),
                    str(error),
                )

    def _build_header_branding(self, identity: Mapping[str, str]) -> None:
        brand = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        brand.add_css_class("welcome-header-brand")

        # Application identity icon from the Freedesktop hicolor theme (PNG).
        logo = Gtk.Image(icon_name=config.PROJECT_NAME)
        logo.set_pixel_size(24)
        _mark_decorative(logo)
        brand.append(logo)

        distro = Gtk.Label(label=identity["distro_name"], xalign=0)
        distro.add_css_class("brand-label")
        brand.append(distro)

        self.header_bar.pack_start(brand)

    @Gtk.Template.Callback()
    def on_sidebar_row_selected(self, _sidebar, row: Gtk.ListBoxRow | None) -> None:
        if row is not None:
            self.stack.set_visible_child_name(row.page_title)

    @Gtk.Template.Callback()
    def on_autostart_toggled(self, button: Gtk.CheckButton) -> None:
        if not getattr(self, "_autostart_ready", False):
            return
        try:
            autostart.set_enabled(button.get_active(), self.identity["app_name"])
        except OSError as error:
            self._show_error(
                i18n.text(
                    "dialogs",
                    "autostart_failed",
                    default="Could not change the startup setting",
                ),
                str(error),
            )

    def _build_sidebar_row(self, page: Page) -> Gtk.ListBoxRow:
        box = Gtk.Box(spacing=10)
        icon = Gtk.Image(icon_name=page.icon)
        icon.set_pixel_size(16)
        _mark_decorative(icon)
        box.append(icon)
        title = Gtk.Label(label=page.title, xalign=0, wrap=True, hexpand=True)
        title.set_accessible_role(Gtk.AccessibleRole.LABEL)
        box.append(title)

        row = Gtk.ListBoxRow(child=box)
        row.page_title = page.title
        _set_accessible_label(row, page.title)
        return row

    def _build_page(self, page: Page) -> Gtk.Widget:
        # Reading column is centered in the content pane so the composition
        # feels balanced regardless of where the compositor places the window.
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.add_css_class("page-content")
        content.set_halign(Gtk.Align.CENTER)
        content.set_hexpand(False)
        content.set_valign(Gtk.Align.START)
        content.append(self._build_page_header(page))

        for section in page.sections:
            widget = self._build_section(section)
            if widget is not None:
                content.append(widget)

        action_rows = [
            self._build_action_row(action)
            for action in page.actions
            if action.command or action.url
        ]
        if action_rows:
            actions = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            actions.set_activate_on_single_click(True)
            actions.add_css_class("action-list")
            actions.set_hexpand(True)
            _set_accessible_label(
                actions,
                i18n.text("ui", "actions_label", default="Actions"),
            )
            actions.connect("row-activated", self._on_action_activated)
            for row in action_rows:
                actions.append(row)
            content.append(actions)

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        shell.add_css_class("page-shell")
        shell.set_hexpand(True)
        shell.append(content)

        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.set_child(shell)
        return scrolled

    def _build_page_header(self, page: Page) -> Gtk.Widget:
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        title = Gtk.Label(label=page.title, xalign=0)
        title.add_css_class("page-title")
        _set_heading(title, 1)
        header.append(title)

        if page.description:
            description = Gtk.Label(
                label=page.description, xalign=0, wrap=True, max_width_chars=_PROSE_WIDTH_CHARS
            )
            description.add_css_class("page-description")
            description.add_css_class("dim-label")
            _set_paragraph(description)
            header.append(description)

        return header

    def _build_section(self, section: Section) -> Gtk.Widget | None:
        if section.data:
            facts = system_info.DATA_READERS[section.data]()
            return self._build_facts(section.heading, facts) if facts else None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        heading = Gtk.Label(
            label=section.heading, xalign=0, wrap=True, max_width_chars=_PROSE_WIDTH_CHARS
        )
        heading.add_css_class("section-heading")
        _set_heading(heading, 2)
        box.append(heading)

        body = Gtk.Label(
            label=section.body, xalign=0, wrap=True, max_width_chars=_PROSE_WIDTH_CHARS
        )
        body.add_css_class("section-body")
        _set_paragraph(body)
        box.append(body)

        return box

    def _build_facts(self, heading: str, facts: list[Fact]) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        heading_label = Gtk.Label(label=heading, xalign=0)
        heading_label.add_css_class("section-heading")
        _set_heading(heading_label, 2)
        box.append(heading_label)

        grid = Gtk.Grid(column_spacing=28, row_spacing=8)
        grid.add_css_class("facts-list")
        for row, (label, value) in enumerate(facts):
            label_widget = Gtk.Label(label=label, xalign=0)
            label_widget.add_css_class("dim-label")
            # Visual key only; the value carries the paired accessible name.
            # PyGObject's LABELLED_BY relation currently warns under GTK 4.14.
            _mark_decorative(label_widget)
            grid.attach(label_widget, 0, row, 1, 1)

            value_widget = Gtk.Label(
                label=value, xalign=0, wrap=True, max_width_chars=_PROSE_WIDTH_CHARS
            )
            _set_accessible_label(value_widget, f"{label}: {value}")
            grid.attach(value_widget, 1, row, 1, 1)
        box.append(grid)

        return box

    def _build_action_row(self, action: Action) -> Gtk.ListBoxRow:
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        title = Gtk.Label(label=action.label, xalign=0)
        title.set_accessible_role(Gtk.AccessibleRole.LABEL)
        labels.append(title)
        if action.description:
            description = Gtk.Label(
                label=action.description, xalign=0, wrap=True, max_width_chars=_PROSE_WIDTH_CHARS
            )
            description.add_css_class("dim-label")
            _set_paragraph(description)
            labels.append(description)

        row = Gtk.ListBoxRow(child=labels)
        row.action = action
        _set_accessible_label(row, action.label)
        if action.description:
            row.update_property(
                [Gtk.AccessibleProperty.DESCRIPTION],
                [action.description],
            )
        return row

    def _on_action_activated(self, _list_box, row: Gtk.ListBoxRow) -> None:
        action: Action = row.action
        if action.url:
            self._open_url(action.url)
        elif action.command:
            self._run_action(action.command)

    def _open_url(self, url: str) -> None:
        from amonite_welcome.identity import is_safe_web_url

        if not is_safe_web_url(url):
            self._show_error(
                i18n.text("dialogs", "open_url_failed", default="Could not open the web page"),
                i18n.text(
                    "dialogs",
                    "disallowed_url",
                    default="Only http and https links can be opened.",
                ),
            )
            return
        launcher = Gtk.UriLauncher(uri=url)
        launcher.launch(self, None, self._on_url_opened)

    def _on_url_opened(self, launcher: Gtk.UriLauncher, result) -> None:
        try:
            launcher.launch_finish(result)
        except GLib.Error as error:
            self._show_error(
                i18n.text("dialogs", "open_url_failed", default="Could not open the web page"),
                error.message,
            )

    def _run_action(self, capability: str) -> None:
        unavailable = i18n.text(
            "dialogs", "action_unavailable", default="This action is not available"
        )
        try:
            argv = launch(capability)
        except CapabilityUnavailableError as error:
            self._show_error(unavailable, str(error))
            return
        except ValueError:
            self._show_error(
                unavailable,
                i18n.text(
                    "dialogs",
                    "unknown_action",
                    default="The handbook refers to an unknown action.",
                ),
            )
            return
        except Exception:
            self._show_error(
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
            self._show_error(
                i18n.text(
                    "dialogs",
                    "open_action_failed",
                    default="Could not open this action",
                ),
                error.message,
            )

    def _show_error(self, message: str, detail: str) -> None:
        dialog = Gtk.AlertDialog(message=message, detail=detail, modal=True)
        dialog.show(self)
