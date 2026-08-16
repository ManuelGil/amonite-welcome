#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate configuration and internationalization catalogs before release.

Checks identity catalogs, project authoring, providers.yaml, handbook YAML, UI
string catalogs, desktop files, and meson files. Also enforces the metadata
ownership rules: Welcome declares no distribution facts, no desktop names, and
exactly one copy of every project URL and author name. Exits non-zero when any
check fails.
"""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Mapping
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ERRORS: list[str] = []
OKS: list[str] = []

# The authoring vocabulary is defined once, by the runtime identity module.
sys.path.insert(0, str(ROOT))
from amonite_welcome.identity import (  # noqa: E402
    AUTHORING_FIELDS,
    AUTHORING_URL_FIELDS,
    DESKTOP_FIELDS,
    DISTRIBUTION_FIELDS,
)

# The sponsorship URL itself lives only in identity.base.yaml. Validation
# asserts its shape so no second copy of the address exists in the tree.
SPONSOR_URL_SHAPE = re.compile(r"^https://github\.com/sponsors/[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")

# Desktop environments Welcome must never name. Runtime code and every
# user-facing catalog have to obtain the desktop from distribution metadata.
DESKTOP_NAMES = re.compile(
    r"(?i)\b(xfce|labwc|gnome|mate|lxqt|lxde|kde|plasma|cinnamon|budgie|"
    r"pantheon|deepin|enlightenment|openbox|i3|sway|wayfire)\b"
)

# data/providers.yaml and actions.py are the capability registry and its
# resolver: provider executables and terminal argv styles are their vocabulary,
# not desktop assumptions, so they are exempt from the desktop-name rule.
DESKTOP_NAME_EXEMPT = ("data/providers.yaml", "amonite_welcome/actions.py")

PLACEHOLDER = re.compile(r"\$[a-z_]+")
FORBIDDEN_IN_USER_TEXT = re.compile(
    r"(?i)\b(synaptic|kitty|xfce4-|gnome-terminal|nm-connection-editor|"
    r"gnome-control-center|konsole|thunar|exo-open|/usr/)\b"
)
FORBIDDEN_EDITORIAL_DASH = re.compile(r"[—–]")
HANDBOOK_LANGUAGES = ("en", "es", "pt", "it", "fr", "de", "nl")


def fail(message: str) -> None:
    ERRORS.append(message)
    print(f"FAIL: {message}", file=sys.stderr)


def ok(message: str) -> None:
    OKS.append(message)
    print(f"ok  {message}")


def _load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _key_tree(node: object, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Mapping):
                keys |= _key_tree(value, path)
            else:
                keys.add(path)
    return keys


def _leaf_strings(node: object, prefix: str = "") -> list[tuple[str, str]]:
    leaves: list[tuple[str, str]] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Mapping):
                leaves.extend(_leaf_strings(value, path))
            elif isinstance(value, str):
                leaves.append((path, value))
            elif value is None:
                leaves.append((path, ""))
            else:
                leaves.append((path, str(value)))
    return leaves


def validate_meson() -> None:
    for name in ("meson.build", "data/meson.build", "amonite_welcome/meson.build"):
        path = ROOT / name
        if not path.is_file():
            fail(f"missing {name}")
        else:
            ok(f"found {name}")


_IDENTITY_LOCALIZED_KEYS = ("app_name", "slogan", "generic_name", "comment")
_IDENTITY_BASE_KEYS = ("schema_version", "desktop_id", "authoring")


def validate_identity() -> None:
    base_path = DATA / "identity.base.yaml"
    if not base_path.is_file():
        fail("data/identity.base.yaml missing")
        return
    try:
        base = _load_yaml(base_path)
    except yaml.YAMLError as error:
        fail(f"identity.base.yaml: {error}")
        return
    if not isinstance(base, dict):
        fail("identity.base.yaml: root must be a mapping")
        return
    missing_base = [key for key in _IDENTITY_BASE_KEYS if key not in base]
    if missing_base:
        fail(f"identity.base.yaml missing keys: {', '.join(missing_base)}")
        return
    if "desktop_id" in base and not str(base["desktop_id"]).strip():
        fail("identity.base.yaml: desktop_id must not be empty")
        return
    ok("identity.base.yaml")

    en_path = DATA / "identity.en.yaml"
    if not en_path.is_file():
        fail("data/identity.en.yaml missing")
        return
    en_doc = _load_yaml(en_path)
    if not isinstance(en_doc, dict):
        fail("identity.en.yaml invalid")
        return
    en_keys = set(en_doc)
    if set(_IDENTITY_LOCALIZED_KEYS) != en_keys:
        fail(
            "identity.en.yaml must contain exactly "
            f"{list(_IDENTITY_LOCALIZED_KEYS)}, found {sorted(en_keys)}"
        )
        return

    for language in HANDBOOK_LANGUAGES:
        path = DATA / f"identity.{language}.yaml"
        if not path.is_file():
            fail(f"missing identity catalog identity.{language}.yaml")
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"{path.name}: not valid UTF-8")
            continue
        try:
            doc = _load_yaml(path)
        except yaml.YAMLError as error:
            fail(f"{path.name}: {error}")
            continue
        if not isinstance(doc, dict):
            fail(f"{path.name}: root must be a mapping")
            continue
        keys = set(doc)
        missing = sorted(en_keys - keys)
        extra = sorted(keys - en_keys)
        if missing:
            fail(f"{path.name}: missing keys: {', '.join(missing)}")
        if extra:
            fail(f"{path.name}: obsolete keys: {', '.join(extra)}")
        empty = [
            key
            for key in _IDENTITY_LOCALIZED_KEYS
            if not str(doc.get(key, "")).strip()
        ]
        if empty:
            fail(f"{path.name}: empty values: {', '.join(empty)}")
        for key in _IDENTITY_LOCALIZED_KEYS:
            value = str(doc.get(key, ""))
            if FORBIDDEN_EDITORIAL_DASH.search(value):
                fail(f"{path.name}: use commas or separate sentences instead of an em dash")
        if language != "en":
            for key in _IDENTITY_LOCALIZED_KEYS:
                value = str(doc.get(key, "")).strip()
                english = str(en_doc.get(key, "")).strip()
                if value and english and value == english:
                    fail(f"{path.name}: untranslated identity field {key}")
        if not missing and not extra and not empty:
            ok(f"{path.name} synchronized")


def validate_providers() -> None:
    path = DATA / "providers.yaml"
    if not path.is_file():
        fail("data/providers.yaml missing")
        return
    try:
        raw = _load_yaml(path)
    except yaml.YAMLError as error:
        fail(f"providers.yaml: {error}")
        return
    if not isinstance(raw, dict):
        fail("providers.yaml: root must be a mapping")
        return
    caps = raw.get("capabilities")
    if not isinstance(caps, dict) or not caps:
        fail("providers.yaml: capabilities mapping required")
        return
    terminal = raw.get("terminal")
    if not isinstance(terminal, dict) or not terminal.get("providers"):
        fail("providers.yaml: terminal.providers required")
        return
    allowed_kinds = {"application", "terminal-command"}
    for name, entry in caps.items():
        if not isinstance(entry, dict):
            fail(f"providers.yaml: capability {name!r} must be a mapping")
            continue
        if "unavailable" in entry:
            fail(
                f"providers.yaml: capability {name!r} must not embed user strings "
                "(use strings.<lang>.yaml)"
            )
        kind = entry.get("kind", "application")
        if kind not in allowed_kinds:
            fail(f"providers.yaml: capability {name!r} has unknown kind {kind!r}")
        if kind == "terminal-command" and not entry.get("command"):
            fail(f"providers.yaml: capability {name!r} needs command")
        if kind == "application" and not entry.get("providers"):
            fail(f"providers.yaml: capability {name!r} needs providers")
        for provider in entry.get("providers") or []:
            # Providers are plain executable names. A mapping would suggest a
            # condition the resolver does not evaluate: which provider runs is
            # decided by the registry order and by what is installed, never by
            # the session (Welcome stays desktop-independent).
            if not isinstance(provider, str) or not provider or "/" in provider:
                fail(
                    f"providers.yaml: capability {name!r} provider {provider!r} "
                    "must be a plain executable name"
                )
    ok(f"providers.yaml ({len(caps)} capabilities)")


# Terminal argv shapes, each confirmed by running the terminal and checking
# that the command really executed. They are pinned here because getting one
# wrong is silent at build time and fatal at runtime: the terminal tries to
# execute the whole command line as a program name and reports
# "no such file or directory" to the user instead of updating the system.
#
# ``alternative`` is not a shape. x-terminal-emulator is an alternatives
# symlink whose target the administrator chooses, so its shape has to be read
# from that target at runtime; pinning any fixed shape for it is a bug.
VERIFIED_TERMINAL_STYLES = {
    "x-terminal-emulator": "alternative",
    "kitty": "plain",
    "foot": "plain",
    "gnome-terminal": "dash-dash",
    "xfce4-terminal": "exec-string",
    "konsole": "exec-argv",
    "lxterminal": "exec-string",
    "mate-terminal": "exec-string",
    "alacritty": "exec-argv",
    "wezterm": "start-argv",
    "xterm": "exec-argv",
}

# Providers accepted for each capability, with the reason each one is accepted.
#
# This is a contract, not an inventory: it records which programs Welcome may
# use when they are present, so a distribution that changes what it installs
# does not need a change here, while a program nobody chose cannot slip in.
# Resolution is deliberately desktop-independent, so this record is what keeps
# another desktop's tool from being selected merely because someone installed
# its package. Adding an entry is a decision that belongs next to its reason.
RECORDED_PROVIDERS = {
    "desktop-settings": {
        "xfce4-settings-manager": "settings program of the desktop environment editions install",
    },
    "network-settings": {
        "nm-connection-editor": "connection editor shipped with the network applet",
    },
}

_PROBE_COMMAND = "printf ok && printf 'done'"


def validate_capability_providers() -> None:
    """Every provider a capability names is one the project accepted, with a reason."""
    raw = _load_yaml(DATA / "providers.yaml")
    if not isinstance(raw, dict):
        return
    caps = raw.get("capabilities")
    if not isinstance(caps, dict):
        return

    before = len(ERRORS)
    declared_total = 0
    for name, entry in caps.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("kind", "application") != "application":
            continue
        recorded = RECORDED_PROVIDERS.get(name)
        if recorded is None:
            fail(
                f"providers.yaml: capability {name!r} is not recorded in "
                "RECORDED_PROVIDERS; record the providers it may use and why, "
                "or drop the capability"
            )
            continue
        declared = list(entry.get("providers") or [])
        declared_total += len(declared)
        for provider in declared:
            if provider not in recorded:
                fail(
                    f"providers.yaml: capability {name!r} names provider "
                    f"{provider!r}, which is not recorded as accepted; add it to "
                    "RECORDED_PROVIDERS with the reason it belongs, or remove it"
                )
        if not declared:
            fail(f"providers.yaml: capability {name!r} declares no provider")

    for name in sorted(set(RECORDED_PROVIDERS) - set(caps)):
        fail(f"providers.yaml: capability {name!r} was recorded but is gone")

    if len(ERRORS) == before:
        ok(
            f"capability providers are recorded decisions "
            f"({declared_total} declared, {sum(len(v) for v in RECORDED_PROVIDERS.values())} accepted)"
        )


def validate_terminal_styles() -> None:
    """Every declared terminal keeps the argv shape that was verified for it."""
    from amonite_welcome import actions

    raw = _load_yaml(DATA / "providers.yaml")
    if not isinstance(raw, dict):
        return
    terminal = raw.get("terminal") or {}
    declared = terminal.get("providers") or []
    if not isinstance(declared, list):
        fail("providers.yaml: terminal.providers must be a list")
        return
    alternatives = terminal.get("alternative_styles") or {}
    if not isinstance(alternatives, dict):
        fail("providers.yaml: terminal.alternative_styles must be a mapping")
        return

    before = len(ERRORS)
    checked: dict[str, str] = {}

    for item in declared:
        if not isinstance(item, dict) or not item.get("id") or not item.get("style"):
            fail(f"providers.yaml: terminal provider {item!r} must declare id and style")
            continue
        checked[str(item["id"])] = str(item["style"])

    for name, style in alternatives.items():
        name, style = str(name), str(style)
        if style == "alternative":
            fail(
                f"providers.yaml: alternative_styles[{name!r}] cannot be "
                "'alternative'; that would resolve to itself"
            )
        if name in checked and checked[name] != style:
            fail(
                f"providers.yaml: terminal {name!r} declares style "
                f"{checked[name]!r} but alternative_styles says {style!r}"
            )
        checked.setdefault(name, style)

    for name, style in sorted(checked.items()):
        expected = VERIFIED_TERMINAL_STYLES.get(name)
        if expected is None:
            fail(
                f"providers.yaml: terminal {name!r} has no verified argv shape; "
                "run the terminal with the intended shape, then record it in "
                "VERIFIED_TERMINAL_STYLES"
            )
        elif style != expected:
            fail(
                f"providers.yaml: terminal {name!r} declares style {style!r}, "
                f"but {expected!r} is the shape verified against that terminal"
            )
        if style != "alternative" and style not in actions._ARGV_STYLES:
            fail(f"providers.yaml: terminal {name!r} uses unimplemented style {style!r}")

    for name in sorted(set(VERIFIED_TERMINAL_STYLES) - set(checked)):
        fail(f"providers.yaml: terminal {name!r} was verified but is no longer declared")

    if len(ERRORS) == before:
        ok(f"terminal argv shapes match the verified table ({len(checked)} terminals)")


def validate_terminal_argv_shapes() -> None:
    """Each argv shape stays executable: tokens separate, strings shell-quoted."""
    from amonite_welcome import actions

    before = len(ERRORS)
    for style, builder in sorted(actions._ARGV_STYLES.items()):
        argv = builder("terminal", _PROBE_COMMAND)
        if argv[0] != "terminal":
            fail(f"argv style {style!r} must launch the terminal first: {argv}")
            continue
        blobs = [part for part in argv[1:] if "sh -c" in part]
        if style == "exec-string":
            # One string the terminal re-parses: it has to survive shell
            # quoting rules, or the command line is torn apart on spaces.
            if len(blobs) != 1 or blobs[0] != argv[-1]:
                fail(f"argv style {style!r} must pass one trailing command string: {argv}")
                continue
            try:
                parsed = shlex.split(blobs[0])
            except ValueError as error:
                fail(f"argv style {style!r} produces unparsable quoting: {error}")
                continue
            if parsed != ["sh", "-c", _PROBE_COMMAND]:
                fail(f"argv style {style!r} does not re-parse to the command: {parsed}")
        else:
            # Everything else is handed to execvp() as it stands, so the
            # program name must be a program name and nothing else.
            if blobs:
                fail(
                    f"argv style {style!r} passes a command line where a program "
                    f"name is expected: {argv}"
                )
                continue
            if argv[-3:] != ["sh", "-c", _PROBE_COMMAND]:
                fail(f"argv style {style!r} must end in sh -c <command>: {argv}")
    if len(ERRORS) == before:
        ok(f"terminal argv shapes stay executable ({len(actions._ARGV_STYLES)} shapes)")


def _handbook_texts(doc: Mapping) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for page in doc.get("pages") or []:
        for key in ("title", "description"):
            if page.get(key):
                texts.append((key, str(page[key])))
        for section in page.get("sections") or []:
            for key in ("heading", "body"):
                if section.get(key):
                    texts.append((key, str(section[key])))
        for action in page.get("actions") or []:
            for key in ("label", "description"):
                if action.get(key):
                    texts.append((key, str(action[key])))
    return texts


def _handbook_structure(doc: Mapping) -> list[dict]:
    structure = []
    for page in doc.get("pages") or []:
        structure.append(
            {
                "icon": page.get("icon", ""),
                "section_data": [
                    section.get("data", "") for section in page.get("sections") or []
                ],
                "section_requires": [
                    list(section.get("requires") or []) for section in page.get("sections") or []
                ],
                "actions": [
                    (action.get("command", ""), "url" in action)
                    for action in page.get("actions") or []
                ],
            }
        )
    return structure


def validate_handbook() -> None:
    providers = _load_yaml(DATA / "providers.yaml")
    caps = set(providers["capabilities"])  # type: ignore[index]
    en_path = DATA / "pages.en.yaml"
    en_doc = _load_yaml(en_path)
    if not isinstance(en_doc, dict):
        fail("pages.en.yaml invalid")
        return
    en_structure = _handbook_structure(en_doc)
    en_texts = _handbook_texts(en_doc)

    for language in HANDBOOK_LANGUAGES:
        path = DATA / f"pages.{language}.yaml"
        if not path.is_file():
            fail(f"missing handbook edition pages.{language}.yaml")
            continue
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            fail(f"{path.name}: not valid UTF-8")
            continue
        try:
            doc = _load_yaml(path)
        except yaml.YAMLError as error:
            fail(f"{path.name}: {error}")
            continue
        if not isinstance(doc, dict):
            fail(f"{path.name}: root must be a mapping")
            continue
        structure = _handbook_structure(doc)
        if structure != en_structure:
            fail(f"{path.name}: structure differs from pages.en.yaml")
            continue
        for page in doc.get("pages") or []:
            for action in page.get("actions") or []:
                command = action.get("command")
                if command and command not in caps:
                    fail(
                        f"{path.name}: unknown capability {command!r} "
                        f"(action {action.get('label')!r})"
                    )
                if command and action.get("label") == command:
                    fail(f"{path.name}: action label must not be capability id {command!r}")
        texts = _handbook_texts(doc)
        if len(texts) != len(en_texts):
            fail(f"{path.name}: editorial field count differs from English")
            continue
        for (_, en_text), (_, text) in zip(en_texts, texts):
            if PLACEHOLDER.findall(en_text) != PLACEHOLDER.findall(text):
                fail(f"{path.name}: placeholder mismatch near {text[:48]!r}")
            if FORBIDDEN_IN_USER_TEXT.search(text):
                fail(f"{path.name}: user text leaks implementation detail: {text[:64]!r}")
            if FORBIDDEN_EDITORIAL_DASH.search(text):
                fail(f"{path.name}: use commas or separate sentences instead of an em dash")
            if language != "en" and text.strip() == en_text.strip() and len(en_text.strip()) > 24:
                fail(f"{path.name}: untranslated English remnant: {text[:64]!r}")
        ok(f"{path.name} synchronized ({len(texts)} fields)")


def validate_strings() -> None:
    en_path = DATA / "strings.en.yaml"
    if not en_path.is_file():
        fail("data/strings.en.yaml missing")
        return
    en_doc = _load_yaml(en_path)
    if not isinstance(en_doc, dict):
        fail("strings.en.yaml invalid")
        return
    en_keys = _key_tree(en_doc)
    en_leaves = dict(_leaf_strings(en_doc))
    required_groups = {"ui", "dialogs", "facts", "capabilities"}
    if not required_groups.issubset(en_doc):
        fail(f"strings.en.yaml missing groups: {sorted(required_groups - set(en_doc))}")
        return
    if "desktop" in en_doc:
        fail(
            "strings.*.yaml must not contain desktop: "
            "(use identity.<lang>.yaml for GenericName/Comment)"
        )
        return

    providers = _load_yaml(DATA / "providers.yaml")
    caps = set(providers["capabilities"])  # type: ignore[index]
    cap_msgs = en_doc.get("capabilities")
    if not isinstance(cap_msgs, dict) or set(cap_msgs) != caps:
        fail(
            "strings.en.yaml capabilities keys must match providers.yaml exactly: "
            f"{sorted(caps)}"
        )
        return

    for language in HANDBOOK_LANGUAGES:
        path = DATA / f"strings.{language}.yaml"
        if not path.is_file():
            fail(f"missing strings catalog strings.{language}.yaml")
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"{path.name}: not valid UTF-8")
            continue
        try:
            doc = _load_yaml(path)
        except yaml.YAMLError as error:
            fail(f"{path.name}: {error}")
            continue
        if not isinstance(doc, dict):
            fail(f"{path.name}: root must be a mapping")
            continue
        keys = _key_tree(doc)
        missing = sorted(en_keys - keys)
        extra = sorted(keys - en_keys)
        if missing:
            fail(f"{path.name}: missing keys: {', '.join(missing[:8])}")
        if extra:
            fail(f"{path.name}: obsolete keys: {', '.join(extra[:8])}")
        leaves = dict(_leaf_strings(doc))
        empty = [key for key, value in leaves.items() if not str(value).strip()]
        if empty:
            fail(f"{path.name}: empty translations: {', '.join(empty[:8])}")
        for key, value in leaves.items():
            if FORBIDDEN_IN_USER_TEXT.search(value):
                fail(f"{path.name}: implementation detail in {key}: {value[:64]!r}")
            if FORBIDDEN_EDITORIAL_DASH.search(value):
                fail(f"{path.name}: use commas or separate sentences instead of an em dash")
            if language != "en":
                english = en_leaves.get(key, "")
                # Shared short terms (Distribution, Architecture) may match English.
                if (
                    english
                    and value.strip() == english.strip()
                    and len(english.strip()) > 40
                ):
                    fail(f"{path.name}: untranslated key {key}")
        # Capability unavailable must differ from English for non-en.
        if language != "en":
            for cap in caps:
                en_msg = en_leaves.get(f"capabilities.{cap}.unavailable", "")
                msg = leaves.get(f"capabilities.{cap}.unavailable", "")
                if en_msg and msg and msg.strip() == en_msg.strip():
                    fail(f"{path.name}: untranslated capability message {cap}")
        translated = sum(
            1
            for key, value in leaves.items()
            if value.strip() and value.strip() != en_leaves.get(key, "").strip()
        )
        if language == "en":
            ok(f"{path.name} canonical ({len(leaves)} strings)")
        else:
            pct = 100.0 * (len(leaves) - len(empty)) / max(len(leaves), 1)
            if missing or extra or empty:
                continue
            ok(f"{path.name} complete ({pct:.0f}%, {translated}/{len(leaves)} localized)")


def _desktop_field(text: str, key: str) -> str | None:
    prefix = f"{key}="
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.partition("=")[2]
    return None


def validate_desktop() -> None:
    import shutil
    import subprocess

    desktop = DATA / "amonite-welcome.desktop"
    autostart = DATA / "autostart" / "amonite-welcome.desktop"
    base = _load_yaml(DATA / "identity.base.yaml")
    desktop_id = (
        str(base.get("desktop_id") or "").strip() if isinstance(base, dict) else ""
    )
    app_id = _meson_app_id() or ""
    identities: dict[str, dict] = {}
    for language in HANDBOOK_LANGUAGES:
        path = DATA / f"identity.{language}.yaml"
        if path.is_file():
            doc = _load_yaml(path)
            if isinstance(doc, dict):
                identities[language] = doc

    keyword_values: list[str] = []
    for path in (desktop, autostart):
        if not path.is_file():
            fail(f"missing {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        en = identities.get("en", {})
        if en:
            if _desktop_field(text, "Name") != en.get("app_name"):
                fail(
                    f"{path.name}: Name= must match identity.en.yaml app_name "
                    f"({en.get('app_name')!r})"
                )
            if _desktop_field(text, "GenericName") != en.get("generic_name"):
                fail(f"{path.name}: GenericName= must match identity.en.yaml")
            if _desktop_field(text, "Comment") != en.get("comment"):
                fail(f"{path.name}: Comment= must match identity.en.yaml")
        if desktop_id:
            if _desktop_field(text, "Exec") != desktop_id:
                fail(f"{path.name}: Exec= must match identity.base.yaml desktop_id")
            if _desktop_field(text, "Icon") != desktop_id:
                fail(f"{path.name}: Icon= must match identity.base.yaml desktop_id")
        if app_id and _desktop_field(text, "StartupWMClass") != app_id:
            fail(f"{path.name}: StartupWMClass= must match meson app_id {app_id!r}")
        keywords = _desktop_field(text, "Keywords")
        if keywords is None:
            fail(f"{path.name}: Keywords= is required")
        else:
            keyword_values.append(keywords)
        for language in HANDBOOK_LANGUAGES:
            if language == "en":
                continue
            identity = identities.get(language)
            if identity is None:
                continue
            if f"Name[{language}]=" not in text:
                fail(f"{path.name}: missing Name[{language}]")
            elif _desktop_field(text, f"Name[{language}]") != identity.get("app_name"):
                fail(f"{path.name}: Name[{language}] must match identity.{language}.yaml")
            if f"GenericName[{language}]=" not in text:
                fail(f"{path.name}: missing GenericName[{language}]")
            elif _desktop_field(text, f"GenericName[{language}]") != identity.get(
                "generic_name"
            ):
                fail(
                    f"{path.name}: GenericName[{language}] must match "
                    f"identity.{language}.yaml"
                )
            if f"Comment[{language}]=" not in text:
                fail(f"{path.name}: missing Comment[{language}]")
            elif _desktop_field(text, f"Comment[{language}]") != identity.get("comment"):
                fail(f"{path.name}: Comment[{language}] must match identity.{language}.yaml")
        validator = shutil.which("desktop-file-validate")
        if validator is None:
            ok(f"{path.name} present (desktop-file-validate not installed)")
            continue
        result = subprocess.run(
            [validator, str(path)], capture_output=True, text=True
        )
        if result.returncode != 0:
            fail(f"{path.name}: {result.stderr.strip() or result.stdout.strip()}")
        else:
            ok(f"{path.name} validates and matches identity catalogs")

    if len(keyword_values) == 2 and keyword_values[0] != keyword_values[1]:
        fail("menu and autostart desktop Keywords= must be identical")
    elif len(keyword_values) == 2:
        ok("menu and autostart desktop Keywords= stay synchronized")


def validate_no_gettext_bypass() -> None:
    """Confirm the project uses YAML catalogs, not an incomplete gettext layer."""
    po_files = list(ROOT.rglob("*.po")) + list(ROOT.rglob("*.pot"))
    if po_files:
        fail(
            "unexpected gettext catalogs present; this project uses YAML "
            f"editions: {[str(p.relative_to(ROOT)) for p in po_files[:5]]}"
        )
        return
    ok("no gettext PO/POT catalogs (YAML i18n model)")


_URL_LITERAL = re.compile(r"https?://[^\s\"'<>)]+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The freedesktop autostart key is a standard cross-desktop spelling that
# happens to carry a vendor name. It is a key, not a desktop assumption.
_DESKTOP_NAME_EXEMPT_LINES = ("X-GNOME-Autostart-enabled",)


def _authoring() -> dict[str, str]:
    """Return the canonical authoring block as merged identity fields."""
    base = _load_yaml(DATA / "identity.base.yaml")
    block = base.get("authoring") if isinstance(base, dict) else None
    if not isinstance(block, Mapping):
        return {}
    return {field: str(block.get(key, "") or "").strip() for key, field in AUTHORING_FIELDS.items()}


def validate_authoring() -> None:
    """Project authoring is declared once, completely, and with valid URLs."""
    base = _load_yaml(DATA / "identity.base.yaml")
    if not isinstance(base, dict):
        fail("identity.base.yaml: root must be a mapping")
        return
    block = base.get("authoring")
    if not isinstance(block, Mapping):
        fail("identity.base.yaml: 'authoring' must be a mapping")
        return

    expected = set(AUTHORING_FIELDS)
    found = set(block)
    if found != expected:
        missing = sorted(expected - found)
        extra = sorted(found - expected)
        if missing:
            fail(f"identity.base.yaml authoring missing: {', '.join(missing)}")
        if extra:
            fail(f"identity.base.yaml authoring has unknown keys: {', '.join(extra)}")
        return

    authoring = _authoring()
    empty = sorted(field for field, value in authoring.items() if not value)
    if empty:
        fail(f"identity.base.yaml authoring has empty values: {', '.join(empty)}")
        return

    for field in AUTHORING_URL_FIELDS:
        url = authoring[field]
        if not url.startswith("https://"):
            fail(f"authoring {field} must be an absolute https URL: {url!r}")
        elif _URL_LITERAL.fullmatch(url) is None:
            fail(f"authoring {field} is not a well-formed URL: {url!r}")

    if not SPONSOR_URL_SHAPE.match(authoring["project_sponsor_url"]):
        fail(
            "authoring sponsor must be a GitHub Sponsors account URL "
            f"(https://github.com/sponsors/<account>), found "
            f"{authoring['project_sponsor_url']!r}"
        )
    if not _EMAIL.match(authoring["project_contact"]):
        fail(f"authoring contact is not an email address: {authoring['project_contact']!r}")

    ok(f"project authoring declared once in identity.base.yaml ({len(authoring)} fields)")


def _control_field(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            return line.partition(":")[2].strip()
    return ""


def validate_packaging_authoring() -> None:
    """Debian packaging mirrors authoring exactly, and keeps roles distinct."""
    authoring = _authoring()
    if not authoring:
        return

    control = ROOT / "debian" / "control"
    copyright_path = ROOT / "debian" / "copyright"
    changelog = ROOT / "debian" / "changelog"
    for path in (control, copyright_path, changelog):
        if not path.is_file():
            fail(f"missing {path.relative_to(ROOT)}")
            return

    before = len(ERRORS)
    signature = f"{authoring['project_maintainer']} <{authoring['project_contact']}>"
    control_text = control.read_text(encoding="utf-8")
    if _control_field(control_text, "Maintainer") != signature:
        fail(
            f"debian/control Maintainer must be {signature!r}, "
            f"found {_control_field(control_text, 'Maintainer')!r}"
        )
    if _control_field(control_text, "Homepage") != authoring["project_website_url"]:
        fail("debian/control Homepage must match identity.base.yaml authoring website")

    copyright_text = copyright_path.read_text(encoding="utf-8")
    if _control_field(copyright_text, "Upstream-Contact") != signature:
        fail(f"debian/copyright Upstream-Contact must be {signature!r}")
    if _control_field(copyright_text, "Source") != authoring["project_repository_url"]:
        fail("debian/copyright Source must match identity.base.yaml authoring repository")
    if authoring["project_creator"] not in copyright_text:
        fail(
            "debian/copyright must attribute the project creator "
            f"{authoring['project_creator']!r}"
        )
    # Upstream ownership and packaging responsibility stay in separate stanzas.
    if "Files: *" not in copyright_text or "Files: debian/*" not in copyright_text:
        fail(
            "debian/copyright must keep separate 'Files: *' (project) and "
            "'Files: debian/*' (packaging) stanzas"
        )

    if f"<{authoring['project_contact']}>" not in changelog.read_text(encoding="utf-8"):
        fail("debian/changelog trailer must use the authoring contact address")

    if len(ERRORS) == before:
        ok("debian packaging mirrors authoring and separates maintainer from author")


def _meson_app_id() -> str | None:
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    match = re.search(r"app_id\s*=\s*'([^']+)'", meson)
    return match.group(1) if match else None


def _meson_project_name() -> str | None:
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    match = re.search(r"project\(\s*'([^']+)'", meson)
    return match.group(1) if match else None


def _meson_version() -> str | None:
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    match = re.search(r"version:\s*'([^']+)'", meson)
    return match.group(1) if match else None


def _changelog_version() -> str | None:
    changelog = (ROOT / "debian" / "changelog").read_text(encoding="utf-8")
    match = re.match(r"\S+ \(([^)]+)\)", changelog)
    return match.group(1) if match else None


def validate_build_identity() -> None:
    """desktop_id, binary name, and APP_ID each have one owner and stay aligned."""
    base = _load_yaml(DATA / "identity.base.yaml")
    if not isinstance(base, dict):
        fail("identity.base.yaml: root must be a mapping")
        return
    desktop_id = str(base.get("desktop_id") or "").strip()
    project_name = _meson_project_name()
    app_id = _meson_app_id()
    before = len(ERRORS)
    if not desktop_id:
        fail("identity.base.yaml: desktop_id is required")
    if not project_name:
        fail("meson.build: project() name not found")
    if not app_id:
        fail("meson.build: app_id not found")
    if desktop_id and project_name and desktop_id != project_name:
        fail(
            f"desktop_id {desktop_id!r} must equal meson project name "
            f"{project_name!r} (single basename owner)"
        )
    # The launcher prints meson's version through config.py, and the package
    # carries the changelog's. One release cannot claim two versions.
    meson_version = _meson_version()
    changelog_version = _changelog_version()
    if not meson_version:
        fail("meson.build: project() version not found")
    if not changelog_version:
        fail("debian/changelog: version not found")
    if meson_version and changelog_version and meson_version != changelog_version:
        fail(
            f"version mismatch: meson.build {meson_version!r} vs "
            f"debian/changelog {changelog_version!r}"
        )
    if len(ERRORS) == before:
        ok(
            f"build identity aligned "
            f"(desktop_id={desktop_id}, app_id={app_id}, version={meson_version})"
        )


# Meson entry points that must never be hidden by ignore rules.
_REQUIRED_MESON_FILES = (
    "meson.build",
    "data/meson.build",
    "data/autostart/meson.build",
    "amonite_welcome/meson.build",
)


def validate_source_visibility() -> None:
    """Required build sources must exist on the filesystem."""
    before = len(ERRORS)
    for relative in _REQUIRED_MESON_FILES:
        path = ROOT / relative
        if not path.is_file():
            fail(f"missing required build source: {relative}")
    if len(ERRORS) == before:
        ok("required Meson sources exist on the filesystem")


def validate_application_icons() -> None:
    """Freedesktop PNG icons are present; obsolete SVG assets must not return."""
    before = len(ERRORS)
    desktop_id = ""
    base = _load_yaml(DATA / "identity.base.yaml")
    if isinstance(base, dict):
        desktop_id = str(base.get("desktop_id") or "").strip()
    if not desktop_id:
        fail("identity.base.yaml: desktop_id required for icon validation")
        return

    obsolete = DATA / "icons" / "amonite-mark.svg"
    if obsolete.is_file():
        fail(f"obsolete icon must be removed: {obsolete.relative_to(ROOT)}")

    for stray in (DATA / "icons").glob("*.png"):
        fail(
            f"unpackaged logo under data/icons/ must be removed or moved into "
            f"hicolor/: {stray.relative_to(ROOT)}"
        )

    gresource = DATA / "amonite-welcome.gresource.xml.in"
    if gresource.is_file() and "amonite-mark" in gresource.read_text(encoding="utf-8"):
        fail("gresource must not reference amonite-mark.svg")

    sizes = (
        "16x16",
        "22x22",
        "24x24",
        "32x32",
        "48x48",
        "64x64",
        "128x128",
        "256x256",
    )
    for size in sizes:
        path = DATA / "icons" / "hicolor" / size / "apps" / f"{desktop_id}.png"
        if not path.is_file():
            fail(f"missing application icon: {path.relative_to(ROOT)}")

    scalable = DATA / "icons" / "hicolor" / "scalable" / "apps" / f"{desktop_id}.svg"
    if scalable.is_file():
        fail(f"scalable SVG application icon must not exist: {scalable.relative_to(ROOT)}")

    for desktop_path in (
        DATA / "amonite-welcome.desktop",
        DATA / "autostart" / "amonite-welcome.desktop",
    ):
        text = desktop_path.read_text(encoding="utf-8")
        icon = _desktop_field(text, "Icon")
        if icon != desktop_id:
            fail(f"{desktop_path.name}: Icon= must be {desktop_id!r} (theme name)")
        if icon and ("/" in icon or icon.endswith((".png", ".svg", ".xpm"))):
            fail(f"{desktop_path.name}: Icon= must not be a path or filename")

    if len(ERRORS) == before:
        ok(
            f"application icons: {len(sizes)} hicolor PNGs for {desktop_id}; "
            "no obsolete SVG"
        )


def validate_system_update_message() -> None:
    """Unavailable text may restate the registry command; it must not invent one."""
    providers = _load_yaml(DATA / "providers.yaml")
    if not isinstance(providers, dict):
        return
    caps = providers.get("capabilities")
    if not isinstance(caps, dict):
        return
    entry = caps.get("system-update")
    if not isinstance(entry, dict):
        return
    command = str(entry.get("command") or "").strip()
    if not command:
        return
    before = len(ERRORS)
    for language in HANDBOOK_LANGUAGES:
        path = DATA / f"strings.{language}.yaml"
        if not path.is_file():
            continue
        doc = _load_yaml(path)
        if not isinstance(doc, dict):
            continue
        message = (
            ((doc.get("capabilities") or {}).get("system-update") or {}).get(
                "unavailable"
            )
            or ""
        )
        if command not in str(message):
            fail(
                f"{path.name}: capabilities.system-update.unavailable must include "
                f"the providers.yaml command {command!r}"
            )
    if len(ERRORS) == before:
        ok("system-update unavailable messages mirror providers.yaml command")


def _scan_files(patterns: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(sorted(ROOT.glob(pattern)))
    return found


def validate_no_hardcoded_desktop() -> None:
    """No runtime module or user-facing catalog names a desktop environment."""
    targets = _scan_files(
        (
            "amonite_welcome/*.py",
            "data/*.yaml",
            "data/*.desktop",
            "data/autostart/*.desktop",
        )
    )
    offenders: list[str] = []
    for path in targets:
        relative = path.relative_to(ROOT).as_posix()
        if relative in DESKTOP_NAME_EXEMPT:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(_DESKTOP_NAME_EXEMPT_LINES):
                continue
            match = DESKTOP_NAMES.search(line)
            if match:
                offenders.append(f"{relative}:{number}: {match.group(0)}")
    if offenders:
        for offender in offenders:
            fail(f"hardcoded desktop name: {offender}")
        return
    ok(f"no hardcoded desktop names in {len(targets)} runtime and catalog files")


def validate_desktop_metadata_usage() -> None:
    """Desktop prose is guarded, so missing desktop metadata omits the section."""
    desktop_placeholders = {f"${field}" for field in DESKTOP_FIELDS}
    checked = 0
    for language in HANDBOOK_LANGUAGES:
        path = DATA / f"pages.{language}.yaml"
        if not path.is_file():
            continue
        doc = _load_yaml(path)
        if not isinstance(doc, dict):
            continue
        for page in doc.get("pages") or []:
            for section in page.get("sections") or []:
                text = f"{section.get('heading', '')} {section.get('body', '')}"
                used = {token for token in desktop_placeholders if token in text}
                if not used:
                    continue
                checked += 1
                declared = {f"${key}" for key in section.get("requires") or []}
                undeclared = sorted(used - declared)
                if undeclared:
                    fail(
                        f"{path.name}: section {section.get('heading')!r} uses "
                        f"{', '.join(undeclared)} without listing it under 'requires'"
                    )
    if checked:
        ok(f"desktop prose is guarded by 'requires' in {checked} section(s)")
    else:
        ok("no handbook section depends on desktop metadata")


def validate_no_duplicated_metadata() -> None:
    """Project URLs, author names, and distribution facts appear exactly once."""
    authoring = _authoring()
    if not authoring:
        return
    literals = {
        authoring[field]: field
        for field in (*AUTHORING_URL_FIELDS, "project_creator", "project_maintainer")
    }

    # Runtime modules and every localized catalog must reach this data through
    # identity, never restate it.
    targets = _scan_files(("amonite_welcome/*.py", "data/*.yaml"))
    duplicates: list[str] = []
    for path in targets:
        relative = path.relative_to(ROOT).as_posix()
        if relative == "data/identity.base.yaml":
            continue
        text = path.read_text(encoding="utf-8")
        for literal, field in literals.items():
            if literal in text:
                duplicates.append(f"{relative}: duplicates authoring {field} ({literal})")
    for duplicate in duplicates:
        fail(duplicate)

    # Handbook and UI prose must reach distribution facts through placeholders.
    catalogs = _scan_files(("data/pages.*.yaml", "data/strings.*.yaml"))
    leaks: list[str] = []
    for path in catalogs:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            url = _URL_LITERAL.search(line)
            if url:
                leaks.append(f"{path.name}:{number}: literal URL {url.group(0)}")
    for leak in leaks:
        fail(f"user text must use an identity placeholder: {leak}")

    if not duplicates and not leaks:
        ok(
            f"no duplicated project URLs, author names, or literal URLs "
            f"in {len(targets) + len(catalogs)} files"
        )


def validate_no_declared_distribution() -> None:
    """Welcome declares no distribution field; all come from os-release."""
    declared: list[str] = []
    for path in _scan_files(("data/identity*.yaml",)):
        doc = _load_yaml(path)
        if not isinstance(doc, dict):
            continue
        for field in (*DISTRIBUTION_FIELDS, *DESKTOP_FIELDS):
            if field in doc:
                declared.append(f"{path.name}: declares {field}")
    for entry in declared:
        fail(f"distribution or desktop metadata must not be declared: {entry}")
    if not declared:
        ok("identity catalogs declare no distribution or desktop fields")


def main() -> int:
    print("Configuration and internationalization validation")
    validate_meson()
    validate_identity()
    validate_build_identity()
    validate_source_visibility()
    validate_authoring()
    validate_packaging_authoring()
    validate_providers()
    validate_capability_providers()
    validate_terminal_styles()
    validate_terminal_argv_shapes()
    validate_handbook()
    validate_strings()
    validate_system_update_message()
    validate_desktop()
    validate_application_icons()
    validate_desktop_metadata_usage()
    validate_no_hardcoded_desktop()
    validate_no_declared_distribution()
    validate_no_duplicated_metadata()
    validate_no_gettext_bypass()
    print()
    if ERRORS:
        print(f"{len(ERRORS)} error(s), {len(OKS)} check(s) passed", file=sys.stderr)
        return 1
    print(f"All {len(OKS)} configuration and i18n checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
