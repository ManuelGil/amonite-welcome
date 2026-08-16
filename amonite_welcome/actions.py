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
import shlex
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REGISTRY_NAME = "providers.yaml"
from amonite_welcome import strings as i18n

_DEFAULT_UNAVAILABLE = "This action is not available on this system."

# Terminal argv construction styles referenced from providers.yaml.
# Executable names themselves must not appear here.
#
# Terminals disagree on how ``-e`` is parsed and the disagreement is not
# cosmetic: passing the wrong shape makes the terminal try to execute a program
# whose name is the whole command line, which fails with ENOENT. Each style
# below is a distinct, verified argv shape; providers.yaml says which terminal
# speaks which one.
_ARGV_STYLES = {
    # ``T -e sh -c CMD`` - the command line is one argv element per token, so
    # the terminal can hand it to execvp() unchanged (Debian Policy 11.8.3).
    "exec-argv": lambda terminal, command: [terminal, "-e", "sh", "-c", command],
    # ``T -e "sh -c CMD"`` - the terminal takes a single string and re-parses it
    # with shell quoting rules, so the command must be shell-quoted here.
    "exec-string": lambda terminal, command: [
        terminal,
        "-e",
        f"sh -c {shlex.quote(command)}",
    ],
    # ``T -- sh -c CMD`` - everything after ``--`` is the command line.
    "dash-dash": lambda terminal, command: [terminal, "--", "sh", "-c", command],
    # ``T sh -c CMD`` - trailing operands are the command line.
    "plain": lambda terminal, command: [terminal, "sh", "-c", command],
    # ``T start -- sh -c CMD`` - the terminal dispatches on a subcommand first.
    "start-argv": lambda terminal, command: [
        terminal,
        "start",
        "--",
        "sh",
        "-c",
        command,
    ],
}

# Not an argv shape: the provider is a Debian alternatives symlink, so the argv
# shape depends on whichever terminal the administrator selected. The style is
# taken from the resolved target instead of assumed. See _alternative_style().
_ALTERNATIVE_STYLE = "alternative"

# Style used when an alternative resolves to a terminal the registry does not
# list. Debian Policy 11.8.3 requires x-terminal-emulator to accept a command
# and its arguments after ``-e``, which is exactly this shape.
_UNKNOWN_TERMINAL_STYLE = "exec-argv"

# Debian ships shell/perl wrappers (``gnome-terminal.wrapper``) whose only job
# is to provide the historical xterm ``-e`` interface: a single string.
_WRAPPER_SUFFIXES = (".wrapper", ".real")

# Graphical sessions frequently start with a PATH that omits the sbin
# directories, while some systems keep administration programs there. Look in
# the standard locations before declaring a capability unavailable.
_ADMIN_DIRS = ("/usr/local/sbin", "/usr/sbin", "/sbin")

# Session identity as the display managers publish it. Reported by diagnose()
# and never consulted while resolving: which provider runs is a property of the
# registry and of what is installed, not of the session.
_SESSION_VARS = ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "XDG_SESSION_TYPE")


class CapabilityUnavailableError(Exception):
    """Raised when no provider can satisfy a capability."""

    def __init__(self, capability: str, message: str):
        super().__init__(message)
        self.capability = capability


class RegistryError(Exception):
    """Raised when providers.yaml is missing or invalid."""


def _which(executable: str) -> str | None:
    """Locate *executable*, including the sbin directories PATH may omit."""
    found = shutil.which(executable)
    if found is not None:
        return found
    if "/" in executable:
        return None
    for directory in _ADMIN_DIRS:
        candidate = os.path.join(directory, executable)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _session_report() -> list[tuple[str, str]]:
    """Return session variables for reporting. Never used to choose a provider."""
    return [
        (variable, os.environ.get(variable, "").strip() or "(unset)")
        for variable in _SESSION_VARS
    ]


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


def _terminal_declarations() -> list[tuple[str, str]]:
    """Return (provider_id, style) pairs exactly as the registry declares them."""
    terminal = _load_registry().get("terminal") or {}
    raw = terminal.get("providers", [])
    if not isinstance(raw, list):
        return []
    declarations: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            declarations.append((item, _UNKNOWN_TERMINAL_STYLE))
        elif isinstance(item, dict) and item.get("id"):
            declarations.append(
                (str(item["id"]), str(item.get("style", _UNKNOWN_TERMINAL_STYLE)))
            )
    return declarations


def _alternative_target(path: str) -> str | None:
    """Return the basename an alternatives symlink finally points at."""
    try:
        return Path(path).resolve(strict=True).name
    except OSError:
        return None


def _alternative_styles() -> Mapping[str, str]:
    """Argv shapes for terminals that may sit behind the alternatives symlink."""
    terminal = _load_registry().get("terminal") or {}
    styles = terminal.get("alternative_styles") or {}
    if not isinstance(styles, dict):
        raise RegistryError("terminal.alternative_styles must be a mapping")
    return {str(name): str(style) for name, style in styles.items()}


def _alternative_style(path: str) -> str:
    """Return the argv style of the terminal an alternatives symlink points at.

    The administrator chooses the target, and the targets do not agree on how
    ``-e`` is parsed, so the style has to follow the link instead of the name.
    """
    name = _alternative_target(path)
    if name is None:
        return _UNKNOWN_TERMINAL_STYLE

    for suffix in _WRAPPER_SUFFIXES:
        if name.endswith(suffix):
            # A wrapper exists to provide the historical xterm ``-e``
            # interface, whatever the terminal behind it expects.
            return "exec-string"

    for provider_id, style in _terminal_declarations():
        if provider_id == name and style != _ALTERNATIVE_STYLE:
            return style
    return _alternative_styles().get(name, _UNKNOWN_TERMINAL_STYLE)


def _terminal_provider() -> tuple[str, str] | None:
    """Return (executable_path, argv_style) for the first available terminal."""
    for name, style in _terminal_declarations():
        path = _which(name)
        if path is None:
            continue
        if style == _ALTERNATIVE_STYLE:
            style = _alternative_style(path)
        return path, style
    return None


def _terminal_argv(shell_command: str) -> list[str] | None:
    found = _terminal_provider()
    if found is None:
        return None
    terminal, style = found
    builder = _ARGV_STYLES.get(style)
    if builder is None:
        raise RegistryError(f"unknown terminal argv style: {style!r}")
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


def terminal_argv(shell_command: str) -> list[str] | None:
    """Return argv running *shell_command* in a terminal, or None if there is none.

    Exposed so verification can exercise argv construction with a harmless
    command instead of the registry's own.
    """
    return _terminal_argv(shell_command)


def terminal_style() -> str | None:
    """Return the argv style chosen for the terminal this system provides."""
    found = _terminal_provider()
    return None if found is None else found[1]


def diagnose() -> list[tuple[str, str]]:
    """Return (capability, resolution) pairs describing this system.

    Maintenance aid: it reports what the capability registry resolves to here,
    so an installation that shows an action as unavailable can be inspected
    without guessing. Nothing is started.
    """
    report: list[tuple[str, str]] = list(_session_report())

    found = _terminal_provider()
    if found is None:
        report.append(("terminal", "unavailable"))
        report.append(("terminal providers", ", ".join(providers("terminal"))))
    else:
        path, style = found
        target = _alternative_target(path)
        report.append(
            ("terminal", path if target in (None, Path(path).name) else f"{path} -> {target}")
        )
        report.append(("terminal style", style))

    for capability in sorted(known_capabilities()):
        try:
            argv = resolve(capability)
        except CapabilityUnavailableError:
            report.append((capability, "unavailable"))
            report.append(
                (
                    f"{capability} providers",
                    ", ".join(providers(capability)) or "(none configured)",
                )
            )
        except (RegistryError, ValueError) as error:
            report.append((capability, f"error: {error}"))
        else:
            report.append((capability, "available"))
            report.append((f"{capability} argv", " ".join(argv)))
    return report
