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

"""Handbook loading, validation, and locale resolution."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from string import Template

import yaml

from amonite_welcome import system_info
from amonite_welcome.actions import known_capabilities
from amonite_welcome.identity import IDENTITY_FIELDS
from amonite_welcome.localeutil import DEFAULT_LANGUAGE, editorial_language


KNOWN_DATA_SOURCES = tuple(system_info.DATA_READERS)


@dataclass(frozen=True)
class Section:
    heading: str
    body: str = ""
    data: str = ""
    # Identity fields this section talks about. When any of them is empty the
    # section is dropped, so prose never depends on metadata the system did
    # not publish.
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    label: str
    description: str = ""
    command: str = ""
    url: str = ""


@dataclass(frozen=True)
class Page:
    title: str
    icon: str = "applications-system-symbolic"
    description: str = ""
    sections: list[Section] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)


class PagesError(Exception):
    """Raised when a handbook edition is missing or malformed."""


def find_pages_path(pkgdatadir: str, language: str | None = None) -> str:
    """Return the handbook file for *language*, falling back to English."""
    language = language or editorial_language()
    localized = os.path.join(pkgdatadir, f"pages.{language}.yaml")
    if os.path.isfile(localized):
        return localized
    return os.path.join(pkgdatadir, f"pages.{DEFAULT_LANGUAGE}.yaml")


def load_pages_for_locale(
    pkgdatadir: str,
    identity: Mapping[str, str] | None = None,
    language: str | None = None,
) -> list[Page]:
    """Load the handbook edition for *language* from *pkgdatadir*."""
    return load_pages(find_pages_path(pkgdatadir, language), identity)


def load_pages(path: str, identity: Mapping[str, str] | None = None) -> list[Page]:
    """Read and validate a handbook YAML file."""
    try:
        with open(path, encoding="utf-8") as pages_file:
            document = yaml.safe_load(pages_file)
    except OSError as error:
        raise PagesError(f"Cannot read {path}: {error.strerror}") from error
    except yaml.YAMLError as error:
        raise PagesError(f"Invalid YAML in {path}: {error}") from error

    if not isinstance(document, dict) or not isinstance(document.get("pages"), list):
        raise PagesError(f"{path} must contain a top-level 'pages' list")

    identity = identity or {}
    pages = [_parse_page(entry, path, identity) for entry in document["pages"]]
    if not pages:
        raise PagesError(f"{path} contains no pages")
    return pages


def _substitute(text: str, identity: Mapping[str, str]) -> str:
    # Leave unknown placeholders visible instead of raising at runtime.
    return Template(text).safe_substitute(identity)


def _text(entry: dict, key: str, identity: Mapping[str, str]) -> str:
    """Read a string field from *entry* and resolve its $placeholders."""
    return _substitute(str(entry.get(key, "")), identity)


def _parse_page(entry: object, path: str, identity: Mapping[str, str]) -> Page:
    if not isinstance(entry, dict) or not entry.get("title"):
        raise PagesError(f"Every page in {path} needs a 'title'")
    title = entry["title"]
    where = f"page '{title}' in {path}"

    sections = entry.get("sections", [])
    if not isinstance(sections, list):
        raise PagesError(f"'sections' of {where} must be a list")

    raw_actions = entry.get("actions", [])
    if not isinstance(raw_actions, list):
        raise PagesError(f"'actions' of {where} must be a list")

    parsed = [_parse_section(section, title, path, identity) for section in sections]
    actions = [
        action
        for action in (
            _parse_action(action_entry, title, path, identity)
            for action_entry in raw_actions
        )
        if action is not None
    ]
    return Page(
        title=_substitute(str(title), identity),
        icon=str(entry.get("icon", Page.icon)),
        description=_text(entry, "description", identity),
        sections=[section for section in parsed if _satisfied(section, identity)],
        actions=actions,
    )


def _satisfied(section: Section, identity: Mapping[str, str]) -> bool:
    """Whether every identity field the section depends on has a value."""
    return all(str(identity.get(key, "")).strip() for key in section.requires)


def _parse_requires(entry: dict, where: str, heading: str) -> tuple[str, ...]:
    raw = entry.get("requires", ())
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)) or not all(isinstance(key, str) for key in raw):
        raise PagesError(f"'requires' of section '{heading}' in {where} must be a list of names")
    unknown = [key for key in raw if key not in IDENTITY_FIELDS]
    if unknown:
        raise PagesError(
            f"Section '{heading}' of {where} requires unknown identity "
            f"field(s): {', '.join(unknown)}"
        )
    return tuple(raw)


def _parse_section(entry: object, page_title: str, path: str, identity: Mapping[str, str]) -> Section:
    where = f"page '{page_title}' in {path}"
    if not isinstance(entry, dict):
        raise PagesError(f"A section of {where} must be a mapping")
    if not entry.get("heading"):
        raise PagesError(f"A section of {where} needs a 'heading'")

    heading = entry["heading"]
    data = entry.get("data", "")
    if data and data not in KNOWN_DATA_SOURCES:
        raise PagesError(f"Section '{heading}' of {where} uses unknown data '{data}'")
    if data and entry.get("body"):
        raise PagesError(f"Section '{heading}' of {where} sets both 'data' and 'body'")
    if not data and not entry.get("body"):
        raise PagesError(f"Section '{heading}' of {where} needs a 'body'")

    requires = _parse_requires(entry, where, str(heading))
    if data and requires:
        raise PagesError(f"Section '{heading}' of {where} sets both 'data' and 'requires'")

    return Section(
        heading=_text(entry, "heading", identity),
        body=_text(entry, "body", identity),
        data=str(data),
        requires=requires,
    )


def _parse_action(
    entry: object, page_title: str, path: str, identity: Mapping[str, str]
) -> Action | None:
    from amonite_welcome.identity import is_safe_web_url

    where = f"page '{page_title}' in {path}"
    if not isinstance(entry, dict) or not entry.get("label"):
        raise PagesError(f"Every action of {where} needs a 'label'")
    label = entry["label"]

    command_id = entry.get("command", "")
    raw_url = entry.get("url", "")
    if not command_id and not raw_url:
        raise PagesError(f"Action '{label}' of {where} needs a 'command' or a 'url'")
    if command_id and command_id not in known_capabilities():
        raise PagesError(f"Action '{label}' of {where} uses unknown capability '{command_id}'")

    url = _text(entry, "url", identity).strip()
    if url and not is_safe_web_url(url):
        raise PagesError(
            f"Action '{label}' of {where} uses a disallowed URL scheme "
            f"(only http/https are accepted)"
        )
    # Placeholder degraded to empty after sanitizing hostile os-release metadata.
    if not command_id and not url:
        return None

    return Action(
        label=_text(entry, "label", identity),
        description=_text(entry, "description", identity),
        command=str(command_id),
        url=url,
    )
