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

"""Identity: four separate domains merged into one read-only mapping.

===================  =========================================================
Domain               Canonical source
===================  =========================================================
Application          ``identity.base.yaml`` + ``identity.<lang>.yaml``
Project authoring    ``identity.base.yaml`` (``authoring:``)
Distribution         ``/etc/os-release``
Desktop environment  desktop metadata drop-in, then ``/etc/os-release``
===================  =========================================================

No domain owns fields belonging to another. Welcome declares nothing about the
distribution or the desktop; it reads both at runtime and omits what is
missing. Callers use :func:`get` / :func:`load_identity` and never read YAML or
``os-release`` themselves.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlparse

import yaml

from amonite_welcome.services.locale import DEFAULT_LANGUAGE, editorial_language

# Localized application prose, required in every identity.<lang>.yaml.
APP_LOCALIZED_FIELDS = ("app_name", "slogan", "generic_name", "comment")

# Schemes allowed for handbook / UriLauncher destinations. file:, javascript:,
# data:, and other handlers are rejected so hostile os-release or catalogs
# cannot open unexpected local handlers.
_ALLOWED_WEB_URL_SCHEMES = frozenset({"http", "https"})

# os-release ID as it may be used to name a file. Host metadata is untrusted:
# anything outside this shape becomes empty rather than a path fragment.
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def sanitize_identifier(value: str) -> str:
    """Return *value* if it is a safe bare identifier, otherwise empty."""
    value = value.strip().lower()
    if not value or len(value) > 64 or not _SAFE_ID.match(value):
        return ""
    return value


def is_safe_web_url(url: str) -> bool:
    """Return True when *url* is an absolute http(s) URL with a host."""
    text = (url or "").strip()
    if not text or any(ord(char) < 32 for char in text):
        return False
    parsed = urlparse(text)
    if parsed.scheme.lower() not in _ALLOWED_WEB_URL_SCHEMES:
        return False
    if not parsed.netloc:
        return False
    return True


def sanitize_web_url(url: str) -> str:
    """Return *url* when safe for UriLauncher, otherwise an empty string."""
    text = (url or "").strip()
    return text if is_safe_web_url(text) else ""


# Project authoring: identity.base.yaml key -> merged identity field.
# This mapping is the only place the authoring vocabulary is defined; runtime,
# packaging checks, and validation all read it from here.
AUTHORING_FIELDS = MappingProxyType(
    {
        "creator": "project_creator",
        "maintainer": "project_maintainer",
        "contact": "project_contact",
        "website": "project_website_url",
        "repository": "project_repository_url",
        "support": "project_support_url",
        "sponsor": "project_sponsor_url",
    }
)

# Authoring fields that must carry an absolute https URL.
AUTHORING_URL_FIELDS = (
    "project_website_url",
    "project_repository_url",
    "project_support_url",
    "project_sponsor_url",
)

# Distribution fields derived from os-release. Never declared in this repository.
DISTRIBUTION_FIELDS = (
    "distro_id",
    "distro_name",
    "pretty_name",
    "release_version",
    "release_codename",
    "release_label",
    "edition_name",
    "edition_id",
    "website_url",
    "forum_url",
)

# Desktop-environment fields. Empty when the distribution publishes no desktop
# metadata; ``desktop_id`` above is the application's .desktop basename and is
# deliberately unrelated to these.
DESKTOP_FIELDS = ("desktop_env_name", "desktop_env_version", "desktop_env_label")

# Every field present after load_identity() merges the four domains.
IDENTITY_FIELDS = (
    *APP_LOCALIZED_FIELDS,
    "desktop_id",
    *AUTHORING_FIELDS.values(),
    *DISTRIBUTION_FIELDS,
    *DESKTOP_FIELDS,
)

_BASE_NAME = "identity.base.yaml"
_DEFAULT_OS_RELEASE = "/etc/os-release"

# Desktop metadata drop-in, in os-release syntax, published by whichever
# package provides the desktop. Checked before os-release so that swapping the
# desktop needs no change to base-files and no change to Welcome. Local
# override first, then the vendor default.
DESKTOP_RELEASE_PATHS = (
    "/etc/amonite/desktop-release",
    "/usr/lib/amonite/desktop-release",
)

# os-release keys read when no drop-in exists: vendor-namespaced first, as the
# os-release specification requires for extensions, then the generic spelling.
_DESKTOP_OS_RELEASE_KEYS = (
    ("AMONITE_DESKTOP_NAME", "AMONITE_DESKTOP_VERSION", "AMONITE_DESKTOP_PRETTY_NAME"),
    ("DESKTOP_NAME", "DESKTOP_VERSION", "DESKTOP_PRETTY_NAME"),
)

_active: Mapping[str, str] = MappingProxyType({})


class IdentityError(Exception):
    """Raised when application identity cannot be loaded or is incomplete."""


def bind(identity: Mapping[str, str]) -> None:
    """Activate *identity* for :func:`get` lookups."""
    global _active
    _active = MappingProxyType(dict(identity))


def clear() -> None:
    """Clear the active identity (tests)."""
    bind({})


def get(key: str, default: str = "") -> str:
    """Return a field from the active identity mapping."""
    value = _active.get(key)
    if value is None or value == "":
        return default
    return value


@lru_cache(maxsize=8)
def read_metadata_file(path: str) -> Mapping[str, str]:
    """Parse an os-release syntax file into a key/value mapping.

    A file that cannot be read, or that is not valid UTF-8, yields an empty
    mapping or replacement characters: absent or damaged metadata is a
    supported state, never an error.
    """
    result: dict[str, str] = {}
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return MappingProxyType(result)

    # Invalid UTF-8 must not abort startup; replace undecodable bytes.
    text = raw.decode("utf-8", errors="replace")

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return MappingProxyType(result)


def read_os_release(path: str = _DEFAULT_OS_RELEASE) -> Mapping[str, str]:
    """Parse an os-release file into a key/value mapping."""
    return read_metadata_file(path)


def load_os_identity(os_release_path: str = _DEFAULT_OS_RELEASE) -> dict[str, str]:
    """Build distribution identity from os-release fields."""
    data = read_os_release(os_release_path)

    name = data.get("NAME") or data.get("PRETTY_NAME") or "Linux"
    pretty_name = data.get("PRETTY_NAME") or name
    version = data.get("VERSION_ID") or ""
    codename = data.get("VERSION_CODENAME") or ""
    # os-release(5) VARIANT / VARIANT_ID name the edition of one distribution.
    # A distribution that publishes a single edition sets neither, and then the
    # edition fields stay empty and prose that declares them is omitted.
    edition_name = (data.get("VARIANT") or "").strip()
    # os-release URLs are untrusted host metadata; only http(s) survive.
    website_url = sanitize_web_url(data.get("HOME_URL") or "")
    forum_url = sanitize_web_url(
        data.get("SUPPORT_URL") or data.get("BUG_REPORT_URL") or ""
    ) or website_url

    if name and version and codename:
        release_label = f"{name} {version} ({codename})"
    elif name and version:
        release_label = f"{name} {version}"
    else:
        release_label = pretty_name

    return {
        "distro_id": sanitize_identifier(data.get("ID") or ""),
        "distro_name": name,
        "pretty_name": pretty_name,
        "release_version": version,
        "release_codename": codename,
        "release_label": release_label,
        "edition_name": edition_name,
        "edition_id": sanitize_identifier(data.get("VARIANT_ID") or ""),
        "website_url": website_url,
        "forum_url": forum_url,
    }


def _desktop_from_dropin(paths: Sequence[str]) -> tuple[str, str, str]:
    for path in paths:
        data = read_metadata_file(path)
        name = data.get("NAME", "").strip()
        if name:
            return name, data.get("VERSION", "").strip(), data.get("PRETTY_NAME", "").strip()
    return "", "", ""


def _desktop_from_os_release(os_release_path: str) -> tuple[str, str, str]:
    data = read_os_release(os_release_path)
    for name_key, version_key, pretty_key in _DESKTOP_OS_RELEASE_KEYS:
        name = data.get(name_key, "").strip()
        if name:
            return name, data.get(version_key, "").strip(), data.get(pretty_key, "").strip()
    return "", "", ""


def load_desktop_identity(
    os_release_path: str = _DEFAULT_OS_RELEASE,
    desktop_release_paths: Sequence[str] | None = None,
) -> dict[str, str]:
    """Build desktop-environment identity from distribution metadata.

    Welcome names no desktop of its own. When the distribution publishes no
    desktop metadata every field stays empty and callers omit them.
    """
    paths = DESKTOP_RELEASE_PATHS if desktop_release_paths is None else desktop_release_paths

    name, version, pretty_name = _desktop_from_dropin(paths)
    if not name:
        name, version, pretty_name = _desktop_from_os_release(os_release_path)

    if pretty_name:
        label = pretty_name
    elif name and version:
        label = f"{name} {version}"
    else:
        label = name

    return {
        "desktop_env_name": name,
        "desktop_env_version": version,
        "desktop_env_label": label,
    }


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise IdentityError(f"cannot read identity file {path}: {error}") from error
    except yaml.YAMLError as error:
        raise IdentityError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(raw, dict):
        raise IdentityError(f"identity file {path} must be a mapping")
    return raw


def find_identity_path(pkgdatadir: str, language: str | None = None) -> Path:
    """Return the localized identity file, falling back to English."""
    language = language or editorial_language()
    localized = Path(pkgdatadir) / f"identity.{language}.yaml"
    if localized.is_file():
        return localized
    english = Path(pkgdatadir) / f"identity.{DEFAULT_LANGUAGE}.yaml"
    if english.is_file():
        return english
    raise IdentityError(
        f"no identity catalog in {pkgdatadir} "
        f"(tried identity.{language}.yaml and identity.{DEFAULT_LANGUAGE}.yaml)"
    )


def load_app_identity(
    pkgdatadir: str, language: str | None = None
) -> dict[str, str]:
    """Load base + localized application identity from *pkgdatadir*."""
    base_path = Path(pkgdatadir) / _BASE_NAME
    localized_path = find_identity_path(pkgdatadir, language)

    merged: dict[str, object] = {}
    if base_path.is_file():
        merged.update(_read_yaml_mapping(base_path))
    merged.update(_read_yaml_mapping(localized_path))

    missing = [
        key
        for key in APP_LOCALIZED_FIELDS
        if not str(merged.get(key, "")).strip()
    ]
    if missing:
        raise IdentityError(
            f"identity catalog {localized_path.name} missing required fields: "
            f"{', '.join(missing)}"
        )

    desktop_id = str(merged.get("desktop_id") or "").strip()
    if not desktop_id:
        raise IdentityError(
            f"{_BASE_NAME} must define a non-empty desktop_id "
            "(the .desktop basename this application installs)"
        )
    identity = {key: str(merged[key]).strip() for key in APP_LOCALIZED_FIELDS}
    identity["desktop_id"] = desktop_id
    return identity


def load_project_identity(pkgdatadir: str) -> dict[str, str]:
    """Load declarative project authoring from ``identity.base.yaml``.

    Creator, maintainer, website, repository, support, and sponsorship live
    here once. No other module, catalog, or document declares them again.
    """
    base_path = Path(pkgdatadir) / _BASE_NAME
    if not base_path.is_file():
        raise IdentityError(f"missing {_BASE_NAME} in {pkgdatadir}")

    authoring = _read_yaml_mapping(base_path).get("authoring")
    if not isinstance(authoring, Mapping):
        raise IdentityError(f"{_BASE_NAME} must define an 'authoring' mapping")

    identity: dict[str, str] = {}
    missing: list[str] = []
    for key, field in AUTHORING_FIELDS.items():
        value = str(authoring.get(key, "") or "").strip()
        if not value:
            missing.append(key)
        identity[field] = value
    if missing:
        raise IdentityError(
            f"{_BASE_NAME} authoring section missing: {', '.join(missing)}"
        )

    bad_urls = [
        field
        for field in AUTHORING_URL_FIELDS
        if not identity[field].startswith("https://")
    ]
    if bad_urls:
        raise IdentityError(
            f"{_BASE_NAME} authoring URLs must be absolute https: "
            f"{', '.join(bad_urls)}"
        )
    return identity


def load_identity(
    pkgdatadir: str,
    os_release_path: str = _DEFAULT_OS_RELEASE,
    language: str | None = None,
    desktop_release_paths: Sequence[str] | None = None,
) -> Mapping[str, str]:
    """Return application, project, distribution, and desktop identity merged."""
    # Legacy: callers once passed a path to identity.yaml.
    if pkgdatadir.endswith(".yaml") or pkgdatadir.endswith(".yml"):
        raise IdentityError(
            "load_identity() expects a package data directory, not a YAML path"
        )
    return {
        **load_app_identity(pkgdatadir, language),
        **load_project_identity(pkgdatadir),
        **load_os_identity(os_release_path),
        **load_desktop_identity(os_release_path, desktop_release_paths),
    }
