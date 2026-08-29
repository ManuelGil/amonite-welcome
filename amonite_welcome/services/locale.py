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

"""Resolve the two-letter language code used for YAML catalogs."""

from __future__ import annotations

import locale
import os

DEFAULT_LANGUAGE = "en"


def _normalize_language_code(locale_name: str) -> str | None:
    if not locale_name or locale_name in ("C", "POSIX"):
        return None
    base = locale_name.split("@")[0].split(".")[0].replace("-", "_")
    language = base.split("_")[0].lower()
    if len(language) == 2 and language.isalpha():
        return language
    return None


def _messages_locale_from_environment() -> str:
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable, "")
        if value:
            return value
    return ""


def editorial_language() -> str:
    """Return the two-letter language code for the current locale."""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    code, _ = locale.getlocale(locale.LC_MESSAGES)
    if not code:
        code = _messages_locale_from_environment()

    return _normalize_language_code(code) or DEFAULT_LANGUAGE
