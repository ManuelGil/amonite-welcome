"""What the running desktop says about its own appearance.

Read-only: GTK is asked for the colours its theme already publishes, and
os-release for the colour a distribution declares for itself. Nothing is
executed, no path comes from outside, and every source is optional.
"""

from __future__ import annotations

from gi.repository import Gtk

from amonite_welcome.theme.palette import SystemColours, fallback, is_dark

# The colour names every GTK theme has carried since GTK 3, and which Adwaita,
# Yaru, High Contrast and the desktop themes built on them all still define.
# Newer libadwaita names are not assumed: this is the set that is actually
# there to be read.
_BACKGROUND = "theme_base_color"
_SHELL = "theme_bg_color"
_FOREGROUND = "theme_fg_color"
_ACCENT = "theme_selected_bg_color"
_ACCENT_FOREGROUND = "theme_selected_fg_color"
_BORDER = "borders"

_REQUIRED = (_BACKGROUND, _SHELL, _FOREGROUND, _ACCENT)

# ANSI SGR colour numbers a distribution may publish in os-release, mapped to
# the plain 4-bit palette. Used only for an accent, and only when the theme
# offers none.
_ANSI_COLOURS = {
    "31": "#aa0000", "32": "#00aa00", "33": "#aa5500", "34": "#0000aa",
    "35": "#aa00aa", "36": "#00aaaa", "91": "#ff5555", "92": "#55ff55",
    "93": "#ffff55", "94": "#5555ff", "95": "#ff55ff", "96": "#55ffff",
}


def _lookup(context: Gtk.StyleContext, name: str) -> str | None:
    """Return a theme colour as ``#rrggbb``, or None when it is not defined."""
    found, rgba = context.lookup_color(name)
    if not found:
        return None
    return "#" + "".join(
        f"{round(max(0.0, min(1.0, channel)) * 255):02x}"
        for channel in (rgba.red, rgba.green, rgba.blue)
    )


def ansi_accent(os_release: dict[str, str] | None) -> str | None:
    """The accent a distribution declares through ``ANSI_COLOR``, if any."""
    if not os_release:
        return None
    declared = str(os_release.get("ANSI_COLOR", "")).strip()
    for part in declared.split(";"):
        if part in _ANSI_COLOURS:
            return _ANSI_COLOURS[part]
    return None


def read(widget: Gtk.Widget, os_release: dict[str, str] | None = None) -> SystemColours:
    """Collect what this desktop publishes, filling gaps from the fallback.

    ``lookup_color`` is the only way GTK4 exposes a theme's named colours; it
    reads the same cascade the theme itself uses, so a distribution that ships
    its own GTK theme is describing Welcome without knowing Welcome exists.
    """
    context = widget.get_style_context()
    found = {name: _lookup(context, name) for name in _REQUIRED + (_ACCENT_FOREGROUND, _BORDER)}

    if not all(found[name] for name in _REQUIRED):
        base = fallback(_prefers_dark())
        accent = ansi_accent(os_release) or base.accent
        return SystemColours(
            background=base.background,
            shell=base.shell,
            foreground=base.foreground,
            accent=accent,
            accent_foreground=base.accent_foreground,
            border=base.border,
            source="fallback",
        )

    background = found[_BACKGROUND]
    defaults = fallback(is_dark(background))
    return SystemColours(
        background=background,
        shell=found[_SHELL],
        foreground=found[_FOREGROUND],
        accent=found[_ACCENT],
        accent_foreground=found[_ACCENT_FOREGROUND] or defaults.accent_foreground,
        border=found[_BORDER] or defaults.border,
        source=Gtk.Settings.get_default().props.gtk_theme_name or "gtk",
    )


def _prefers_dark() -> bool:
    settings = Gtk.Settings.get_default()
    if settings is None:
        return False
    if settings.props.gtk_application_prefer_dark_theme:
        return True
    return "dark" in (settings.props.gtk_theme_name or "").lower()
