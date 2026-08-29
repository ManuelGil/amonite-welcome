"""Handbook content: the data model and the loader that fills it.

Plain data in, plain data out. Nothing here imports GTK, resolves a provider,
or executes anything. Presentation reads these objects; it never reads YAML.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from string import Template

import yaml

from amonite_welcome.services import system_info
from amonite_welcome.services.identity import IDENTITY_FIELDS, is_safe_web_url
from amonite_welcome.services.locale import DEFAULT_LANGUAGE, editorial_language
from amonite_welcome.services.providers import known_capabilities

KNOWN_DATA_SOURCES = tuple(system_info.DATA_READERS)

# Page ids are structural, never translated: navigation, the window stack and
# the verification suite all key on them, so they survive translation.
_PAGE_ID = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class Section:
    """One unit of handbook prose, or one named table of system facts."""

    heading: str
    body: str = ""
    data: str = ""
    # Identity fields this section talks about. When any of them is empty the
    # section is dropped, so prose never depends on metadata the system did
    # not publish.
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    """Something the reader can start from the handbook.

    Exactly one of *command* (a capability id) or *url* is set. A capability is
    a name, never a command line: what it resolves to is decided by the
    provider registry, not by content.

    *primary* marks the one action a chapter actually recommends, so the page
    can say so visually instead of offering everything with equal weight.
    """

    label: str
    description: str = ""
    command: str = ""
    url: str = ""
    primary: bool = False


@dataclass(frozen=True)
class Page:
    """A chapter: a stable id, a translated title, prose, and actions."""

    id: str
    title: str
    description: str = ""
    sections: tuple[Section, ...] = field(default_factory=tuple)
    actions: tuple[Action, ...] = field(default_factory=tuple)


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
    seen: set[str] = set()
    for page in pages:
        if page.id in seen:
            raise PagesError(f"{path}: duplicate page id '{page.id}'")
        seen.add(page.id)
    return pages


def _substitute(text: str, identity: Mapping[str, str]) -> str:
    # Leave unknown placeholders visible instead of raising at runtime. YAML
    # folded scalars keep a trailing newline, which a label would render as an
    # empty last line, so editorial text is stripped here rather than in every
    # widget that shows it.
    return Template(text).safe_substitute(identity).strip()


def _text(entry: Mapping, key: str, identity: Mapping[str, str]) -> str:
    """Read a string field from *entry* and resolve its $placeholders."""
    return _substitute(str(entry.get(key, "")), identity)


def _parse_page(entry: object, path: str, identity: Mapping[str, str]) -> Page:
    if not isinstance(entry, dict) or not entry.get("title"):
        raise PagesError(f"Every page in {path} needs a 'title'")
    title = entry["title"]
    where = f"page '{title}' in {path}"

    page_id = str(entry.get("id", "")).strip()
    if not _PAGE_ID.match(page_id):
        raise PagesError(f"{where} needs a stable lowercase 'id' (letters, digits, dashes)")

    sections = entry.get("sections", [])
    if not isinstance(sections, list):
        raise PagesError(f"'sections' of {where} must be a list")

    raw_actions = entry.get("actions", [])
    if not isinstance(raw_actions, list):
        raise PagesError(f"'actions' of {where} must be a list")

    parsed = [_parse_section(section, title, path, identity) for section in sections]
    actions = tuple(
        action
        for action in (
            _parse_action(action_entry, title, path, identity)
            for action_entry in raw_actions
        )
        if action is not None
    )
    return Page(
        id=page_id,
        title=_substitute(str(title), identity),
        description=_text(entry, "description", identity),
        sections=tuple(section for section in parsed if _satisfied(section, identity)),
        actions=actions,
    )


def _satisfied(section: Section, identity: Mapping[str, str]) -> bool:
    """Whether every identity field the section depends on has a value."""
    return all(str(identity.get(key, "")).strip() for key in section.requires)


def _parse_requires(entry: Mapping, where: str, heading: str) -> tuple[str, ...]:
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


def _parse_section(
    entry: object, page_title: str, path: str, identity: Mapping[str, str]
) -> Section:
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
    where = f"page '{page_title}' in {path}"
    if not isinstance(entry, dict) or not entry.get("label"):
        raise PagesError(f"Every action of {where} needs a 'label'")
    label = entry["label"]

    command_id = str(entry.get("command", ""))
    raw_url = entry.get("url", "")
    if not command_id and not raw_url:
        raise PagesError(f"Action '{label}' of {where} needs a 'command' or a 'url'")
    if command_id and raw_url:
        raise PagesError(f"Action '{label}' of {where} sets both 'command' and 'url'")
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
        command=command_id,
        url=url,
        primary=bool(entry.get("primary", False)),
    )
