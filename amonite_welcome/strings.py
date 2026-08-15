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

"""Locale UI string catalogs (``strings.<lang>.yaml``).

Handbook prose uses ``pages.<lang>.yaml``. Chrome, dialogs, fact labels, and
capability messages use these catalogs. There is no gettext/PO layer.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from types import MappingProxyType

import yaml

from amonite_welcome.localeutil import DEFAULT_LANGUAGE, editorial_language

_catalog: Mapping[str, object] = MappingProxyType({})


class StringsError(Exception):
    """Raised when a strings catalog cannot be loaded."""


def bind(catalog: Mapping[str, object]) -> None:
    """Activate *catalog* for :func:`text` lookups."""
    global _catalog
    _catalog = MappingProxyType(dict(catalog))


def clear() -> None:
    """Clear the active catalog (tests)."""
    bind({})


def find_strings_path(pkgdatadir: str, language: str | None = None) -> str:
    """Return the strings file for *language*, falling back to English."""
    language = language or editorial_language()
    localized = os.path.join(pkgdatadir, f"strings.{language}.yaml")
    if os.path.isfile(localized):
        return localized
    return os.path.join(pkgdatadir, f"strings.{DEFAULT_LANGUAGE}.yaml")


def load_strings(path: str) -> dict[str, object]:
    """Load and validate a strings catalog from *path*."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as error:
        raise StringsError(f"cannot read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise StringsError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(data, dict) or not data:
        raise StringsError(f"{path}: root must be a non-empty mapping")
    return data


def load_strings_for_locale(
    pkgdatadir: str, language: str | None = None
) -> dict[str, object]:
    """Load the strings catalog for *language* from *pkgdatadir*."""
    return load_strings(find_strings_path(pkgdatadir, language))


def text(*path: str, default: str = "") -> str:
    """Return a nested string from the active catalog."""
    node: object = _catalog
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return default
        node = node[key]
    if isinstance(node, str):
        return node.strip() if node.strip() else default
    return default


def capability_unavailable(capability: str) -> str:
    """Return the localized unavailable message for *capability*."""
    message = text("capabilities", capability, "unavailable")
    if message:
        return message
    return text(
        "dialogs",
        "action_unavailable",
        default="This action is not available",
    )
