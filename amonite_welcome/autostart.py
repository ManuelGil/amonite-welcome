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

"""XDG autostart for the first-run handbook.

Default is **enabled** (first boot shows Welcome). The package installs a
system entry under ``/etc/xdg/autostart/``. Users opt out by writing a
per-user override with ``Hidden=true``; opting back in removes that override
(or writes a user entry when no system entry is present).
"""

from __future__ import annotations

from pathlib import Path

from gi.repository import GLib

from amonite_welcome import config
from amonite_welcome import identity as identity_api

_OVERRIDE_PATH = Path(
    GLib.get_user_config_dir(), "autostart", f"{config.PROJECT_NAME}.desktop"
)

# User overrides carry only what XDG needs. Localized Name/GenericName/Comment
# and Keywords live in the installed system entry (identity + desktop files).
_ENABLED_ENTRY_TEMPLATE = """\
[Desktop Entry]
Name={app_name}
GenericName={generic_name}
Comment={comment}
Exec={desktop_id}
Icon={desktop_id}
Terminal=false
Type=Application
Categories=System;
StartupNotify=true
"""

_DISABLED_ENTRY_TEMPLATE = _ENABLED_ENTRY_TEMPLATE + "Hidden=true\n"


def override_path() -> Path:
    """Return the path of the per-user autostart desktop entry."""
    return _OVERRIDE_PATH


def system_entry_path() -> Path | None:
    """Return the first existing system-wide autostart entry, if any."""
    name = f"{config.PROJECT_NAME}.desktop"
    for config_dir in GLib.get_system_config_dirs():
        candidate = Path(config_dir) / "autostart" / name
        if candidate.is_file():
            return candidate
    # Common Debian/Ubuntu location when GLib lists differ in tests.
    fallback = Path("/etc/xdg/autostart") / name
    if fallback.is_file():
        return fallback
    return None


def _entry_is_hidden(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        if line.strip().lower() == "hidden=true":
            return True
    return False


def is_enabled() -> bool:
    """Return True unless the user has explicitly opted out.

    Fresh installations have no user override, so the default is enabled.
    """
    if _OVERRIDE_PATH.is_file():
        return not _entry_is_hidden(_OVERRIDE_PATH)
    return True


def set_enabled(enabled: bool, app_name: str) -> None:
    """Enable or disable showing the window on login.

    Raises OSError if the override file cannot be written or removed.
    """
    if enabled:
        if system_entry_path() is not None:
            # Unmask the system entry.
            if _OVERRIDE_PATH.exists():
                _OVERRIDE_PATH.unlink()
            return
        _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OVERRIDE_PATH.write_text(
            _format_entry(_ENABLED_ENTRY_TEMPLATE, app_name), encoding="utf-8"
        )
        return

    _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDE_PATH.write_text(
        _format_entry(_DISABLED_ENTRY_TEMPLATE, app_name), encoding="utf-8"
    )


def _desktop_field(value: str) -> str:
    """Return a single-line desktop-entry value (no key injection)."""
    # Desktop files are line-oriented; control characters would inject keys.
    return "".join(char for char in value if ord(char) >= 32)


def _format_entry(template: str, app_name: str) -> str:
    generic_name = identity_api.get("generic_name").strip()
    comment = identity_api.get("comment").strip()
    desktop_id = identity_api.get("desktop_id").strip() or config.PROJECT_NAME
    if not generic_name or not comment:
        raise RuntimeError(
            "autostart entry requires bound identity (generic_name, comment)"
        )
    # Exec=/Icon= must remain a simple desktop id, never a path or payload.
    safe_id = _desktop_field(desktop_id)
    if not safe_id or safe_id != desktop_id or "/" in safe_id or safe_id.startswith("-"):
        safe_id = config.PROJECT_NAME
    return template.format(
        app_name=_desktop_field(app_name) or config.PROJECT_NAME,
        generic_name=_desktop_field(generic_name) or config.PROJECT_NAME,
        comment=_desktop_field(comment) or config.PROJECT_NAME,
        desktop_id=safe_id,
    )
