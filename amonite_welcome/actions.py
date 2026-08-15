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

"""Generic capability resolver backed by ``providers.yaml``.

Handbook YAML names capabilities. Provider lists and launch kinds live in the
registry. This module does not hardcode distribution applications.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REGISTRY_NAME = "providers.yaml"
from amonite_welcome import strings as i18n

_DEFAULT_UNAVAILABLE = "This action is not available on this system."

# Terminal argv construction styles referenced from providers.yaml.
# Executable names themselves must not appear here.
_ARGV_STYLES = {
    "debian-e": lambda terminal, command: [
        terminal,
        "-e",
        f"sh -c {command!r}",
    ],
    "gnome": lambda terminal, command: [terminal, "--", "sh", "-c", command],
    "konsole": lambda terminal, command: [terminal, "-e", "sh", "-c", command],
    "plain": lambda terminal, command: [terminal, "sh", "-c", command],
}


class CapabilityUnavailableError(Exception):
    """Raised when no provider can satisfy a capability."""

    def __init__(self, capability: str, message: str):
        super().__init__(message)
        self.capability = capability


ActionUnavailableError = CapabilityUnavailableError


class RegistryError(Exception):
    """Raised when providers.yaml is missing or invalid."""


def _which(executable: str) -> str | None:
    return shutil.which(executable)


def _find_registry_path() -> Path:
    env = os.environ.get("AMONITE_WELCOME_PKGDATADIR", "").strip()
    if env:
        path = Path(env) / _REGISTRY_NAME
        if path.is_file():
            return path

    # Installed layout: <pkgdatadir>/amonite_welcome/actions.py
    installed = Path(__file__).resolve().parent.parent / _REGISTRY_NAME
    if installed.is_file():
        return installed

    # Uninstalled Meson tree: builddir/data next to builddir/amonite_welcome
    build_data = Path(__file__).resolve().parent.parent / "data" / _REGISTRY_NAME
    if build_data.is_file():
        return build_data

    # Source checkout during tests: repo/data/providers.yaml
    source = Path(__file__).resolve().parents[1] / "data" / _REGISTRY_NAME
    if source.is_file():
        return source

    raise RegistryError(
        f"capability registry not found ({_REGISTRY_NAME}); "
        "install the package or set AMONITE_WELCOME_PKGDATADIR"
    )


@lru_cache(maxsize=1)
def _load_registry() -> Mapping[str, Any]:
    path = _find_registry_path()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RegistryError(f"cannot read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise RegistryError(f"invalid YAML in {path}: {error}") from error

    if not isinstance(raw, dict):
        raise RegistryError(f"{path}: root must be a mapping")
    capabilities = raw.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        raise RegistryError(f"{path}: capabilities mapping is required")
    terminal = raw.get("terminal")
    if terminal is not None and not isinstance(terminal, dict):
        raise RegistryError(f"{path}: terminal must be a mapping when present")
    return raw


def reload_registry() -> None:
    """Clear the cached registry (tests / tooling)."""
    _load_registry.cache_clear()


def known_capabilities() -> frozenset[str]:
    """Return handbook-facing capability ids from the registry."""
    return frozenset(_load_registry()["capabilities"])


# Lazy alias for importers that expect a set-like name at import time.
def __getattr__(name: str) -> object:
    if name in {"KNOWN_CAPABILITIES", "KNOWN_ACTION_IDS"}:
        return known_capabilities()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _capability_entry(capability: str) -> Mapping[str, Any]:
    capabilities = _load_registry()["capabilities"]
    if capability not in capabilities:
        raise ValueError(f"unknown capability: {capability}")
    entry = capabilities[capability]
    if not isinstance(entry, dict):
        raise RegistryError(f"capability {capability!r} must be a mapping")
    return entry


def _provider_ids(raw_providers: object) -> list[str]:
    if not isinstance(raw_providers, list) or not raw_providers:
        return []
    ids: list[str] = []
    for item in raw_providers:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
        else:
            raise RegistryError(f"invalid provider entry: {item!r}")
    return ids


def providers(capability: str) -> list[str]:
    """Return configured provider ids for *capability* (may be unavailable)."""
    if capability == "terminal":
        terminal = _load_registry().get("terminal") or {}
        return _provider_ids(terminal.get("providers", []))
    entry = _capability_entry(capability)
    return _provider_ids(entry.get("providers", []))


def available(capability: str) -> bool:
    """Return True when at least one provider for *capability* is on PATH."""
    try:
        resolve(capability)
    except (CapabilityUnavailableError, ValueError, RegistryError):
        return False
    return True


def _unavailable_message(capability: str, entry: Mapping[str, Any]) -> str:
    message = i18n.capability_unavailable(capability)
    if message:
        return message
    fallback = entry.get("unavailable")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return _DEFAULT_UNAVAILABLE


def _first_on_path(candidates: Sequence[str]) -> str | None:
    for name in candidates:
        path = _which(name)
        if path is not None:
            return path
    return None


def _terminal_provider() -> tuple[str, str] | None:
    """Return (command_name, argv_style) for the first available terminal."""
    terminal = _load_registry().get("terminal") or {}
    raw = terminal.get("providers", [])
    if not isinstance(raw, list):
        return None
    for item in raw:
        if isinstance(item, str):
            name, style = item, "plain"
        elif isinstance(item, dict) and item.get("id"):
            name = str(item["id"])
            style = str(item.get("style", "plain"))
        else:
            continue
        if _which(name):
            return name, style
    return None


def _terminal_argv(shell_command: str) -> list[str] | None:
    found = _terminal_provider()
    if found is None:
        return None
    terminal, style = found
    builder = _ARGV_STYLES.get(style, _ARGV_STYLES["plain"])
    return builder(terminal, shell_command)


def resolve(capability: str) -> list[str]:
    """Resolve *capability* to argv. Does not start the process."""
    entry = _capability_entry(capability)
    kind = str(entry.get("kind", "application"))

    if kind == "application":
        path = _first_on_path(providers(capability))
        if path is None:
            raise CapabilityUnavailableError(
                capability, _unavailable_message(capability, entry)
            )
        return [path]

    if kind == "terminal-command":
        command = entry.get("command")
        if not isinstance(command, str) or not command.strip():
            raise RegistryError(
                f"capability {capability!r} (terminal-command) needs command:"
            )
        argv = _terminal_argv(command.strip())
        if argv is None:
            raise CapabilityUnavailableError(
                capability, _unavailable_message(capability, entry)
            )
        return argv

    raise RegistryError(f"capability {capability!r}: unknown kind {kind!r}")


def launch(capability: str) -> list[str]:
    """Alias for :func:`resolve` (argv for ``Gio.Subprocess``)."""
    return resolve(capability)


def resolve_action(action_id: str) -> list[str]:
    """Compatibility wrapper around :func:`launch`."""
    return launch(action_id)


# Thin helpers kept for readability at call sites / tests.
def open_package_manager() -> list[str]:
    return launch("package-manager")


def open_system_update() -> list[str]:
    return launch("system-update")


def open_desktop_settings() -> list[str]:
    return launch("desktop-settings")


def open_network_settings() -> list[str]:
    return launch("network-settings")
