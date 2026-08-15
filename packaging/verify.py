#!/usr/bin/env python3
"""Post-install verification for amonite-welcome.

Run after building (`make build` or meson install). Checks packaging metadata,
YAML loading, locale resolution, system facts, and GTK window construction
without opening external programs or URLs.

Reads the install prefix under builddir/ (or build/). Writes only under the
system temporary directory - never into the source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

_ICON_THEME = Path("share") / "icons" / "hicolor"
_ICON_NAME = "amonite-welcome"
_ICON_PNG_SIZES = (
    "16x16",
    "22x22",
    "24x24",
    "32x32",
    "48x48",
    "64x64",
    "128x128",
    "256x256",
)


def _discover_prefix() -> Path:
    """Locate an install tree under builddir/prefix or DESTDIR/package-root."""
    candidates = (
        ROOT / "builddir" / "prefix",
        ROOT / "build" / "prefix",
        ROOT / "package-root" / "usr" / "local",
        ROOT / "package-root" / "usr",
    )
    marker = Path("share") / "amonite-welcome" / "amonite-welcome.gresource"
    for candidate in candidates:
        if (candidate / marker).exists():
            return candidate
    return ROOT / "builddir" / "prefix"


PREFIX = _discover_prefix()
PKGDATA = PREFIX / "share" / "amonite-welcome"
BINDIR = PREFIX / "bin"
ICON_ROOT = PREFIX / _ICON_THEME
ICON_PATH = ICON_ROOT / "256x256" / "apps" / f"{_ICON_NAME}.png"
MENU_DESKTOP = PREFIX / "share" / "applications" / "amonite-welcome.desktop"

EXPECTED_PAGE_COUNT = 4

GRESOURCE_PATHS = (
    "/org/amonite/Welcome/ui/window.ui",
    "/org/amonite/Welcome/style.css",
)

LOCALE_SCENARIOS = (
    ({"LANG": "en_US.UTF-8"}, "Welcome"),
    ({"LANG": "es_ES.UTF-8"}, "Bienvenida"),
    ({"LANG": "es_CO.UTF-8"}, "Bienvenida"),
    ({"LANG": "pt_BR.UTF-8"}, "Boas-vindas"),
    ({"LANG": "pt_PT.UTF-8"}, "Boas-vindas"),
    ({"LANG": "fr_FR.UTF-8"}, "Bienvenue"),
    ({"LANG": "fr_CA.UTF-8"}, "Bienvenue"),
    ({"LANG": "it_IT.UTF-8"}, "Benvenuto"),
    ({"LANG": "de_DE.UTF-8"}, "Willkommen"),
    ({"LANG": "de_AT.UTF-8"}, "Willkommen"),
    ({"LANG": "de_CH.UTF-8"}, "Willkommen"),
    ({"LANG": "nl_NL.UTF-8"}, "Welkom"),
    ({"LANG": "nl_BE.UTF-8"}, "Welkom"),
    ({"LANG": "xx_YY.UTF-8"}, "Welcome"),
    ({"LANG": "not_a_locale"}, "Welcome"),
    ({}, "Welcome"),
    ({"LC_MESSAGES": "it_IT.UTF-8", "LANG": "en_US.UTF-8"}, "Benvenuto"),
    ({"LC_ALL": "fr_FR.UTF-8", "LANG": "en_US.UTF-8"}, "Bienvenue"),
)


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def ok(message: str) -> None:
    print(f"ok  {message}")


def discover_editorial_languages() -> tuple[str, ...]:
    languages = tuple(
        sorted(
            path.name.removeprefix("pages.").removesuffix(".yaml")
            for path in PKGDATA.glob("pages.*.yaml")
        )
    )
    if "en" not in languages:
        fail("pages.en.yaml missing from install prefix")
    return languages


def handbook_structure(path: Path) -> list[dict]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    pages = document.get("pages", [])
    structure = []
    for page in pages:
        structure.append(
            {
                "icon": page.get("icon", ""),
                "section_data": [section.get("data", "") for section in page.get("sections", [])],
                "section_requires": [
                    list(section.get("requires") or []) for section in page.get("sections", [])
                ],
                "section_kinds": [
                    "data" if section.get("data") else "body"
                    for section in page.get("sections", [])
                ],
                "actions": [
                    (action.get("command", ""), "url" in action)
                    for action in page.get("actions", [])
                ],
            }
        )
    return structure


def require_build() -> None:
    required = [
        BINDIR / "amonite-welcome",
        PKGDATA / "amonite-welcome.gresource",
        PKGDATA / "identity.base.yaml",
        PKGDATA / "identity.en.yaml",
        PKGDATA / "providers.yaml",
        PKGDATA / "strings.en.yaml",
        PKGDATA / "pages.en.yaml",
        PKGDATA / "amonite_welcome" / "config.py",
        ICON_PATH,
        MENU_DESKTOP,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        fail(
            "Install prefix incomplete. Build and install first, for example:\n"
            "  meson setup builddir --prefix \"$PWD/builddir/prefix\"\n"
            "  meson compile -C builddir && meson install -C builddir\n"
            "or: make build\n"
            "Missing:\n  "
            + "\n  ".join(str(path) for path in missing)
        )

    languages = discover_editorial_languages()
    for language in languages:
        path = PKGDATA / f"pages.{language}.yaml"
        if not path.exists():
            fail(f"missing handbook edition: {path}")
        identity_path = PKGDATA / f"identity.{language}.yaml"
        if not identity_path.exists():
            fail(f"missing identity catalog: {identity_path}")

    module_dir = str(PKGDATA)
    while module_dir in sys.path:
        sys.path.remove(module_dir)
    sys.path.insert(0, module_dir)
    root_str = str(ROOT)
    while root_str in sys.path:
        sys.path.remove(root_str)
    for name in list(sys.modules):
        if name == "amonite_welcome" or name.startswith("amonite_welcome."):
            del sys.modules[name]


def verify_config() -> None:
    from amonite_welcome import config

    if config.APP_ID != "org.amonite.Welcome":
        fail(f"APP_ID mismatch: {config.APP_ID}")
    if config.RESOURCE_BASE_PATH != "/org/amonite/Welcome":
        fail(f"RESOURCE_BASE_PATH mismatch: {config.RESOURCE_BASE_PATH}")
    if config.PROJECT_NAME != "amonite-welcome":
        fail(f"PROJECT_NAME mismatch: {config.PROJECT_NAME}")
    ok("config.py matches meson.build")


def verify_identity_and_pages() -> tuple[dict[str, str], list]:
    from amonite_welcome import identity as identity_api
    from amonite_welcome.identity import IDENTITY_FIELDS, load_identity

    base = yaml.safe_load((PKGDATA / "identity.base.yaml").read_text(encoding="utf-8"))
    if not isinstance(base, dict) or "desktop_id" not in base:
        fail("identity.base.yaml must define desktop_id")
    if "authoring" not in base:
        fail("identity.base.yaml must define an authoring section")
    en = yaml.safe_load((PKGDATA / "identity.en.yaml").read_text(encoding="utf-8"))
    required = {"app_name", "slogan", "generic_name", "comment"}
    if set(en) != required:
        fail(f"identity.en.yaml must contain exactly {sorted(required)}, found {sorted(en)}")
    ok("identity catalogs define base + localized application fields")

    identity = load_identity(str(PKGDATA), language="en")
    identity_api.bind(identity)
    for field in IDENTITY_FIELDS:
        if field not in identity:
            fail(f"merged identity missing field: {field}")
    if not identity["distro_name"]:
        fail("os-release did not provide distro_name")
    if identity_api.get("slogan") != identity["slogan"]:
        fail("identity.get() does not match loaded slogan")
    ok(f"identity loads from catalogs + os-release ({len(identity)} fields)")

    with tempfile.TemporaryDirectory() as tmp:
        os_release = Path(tmp) / "os-release"
        os_release.write_text(
            'NAME="TestOS"\n'
            'VERSION_ID="1.0"\n'
            'VERSION_CODENAME="trial"\n'
            'HOME_URL="https://example.test/"\n'
            'SUPPORT_URL="https://support.example.test/"\n',
            encoding="utf-8",
        )
        probed = load_identity(str(PKGDATA), str(os_release), language="en")
        if probed["distro_name"] != "TestOS":
            fail(f"os-release NAME not used: {probed['distro_name']!r}")
        if probed["release_label"] != "TestOS 1.0 (trial)":
            fail(f"unexpected release_label: {probed['release_label']!r}")
        if probed["website_url"] != "https://example.test/":
            fail(f"HOME_URL not used: {probed['website_url']!r}")
        if probed["forum_url"] != "https://support.example.test/":
            fail(f"SUPPORT_URL not used: {probed['forum_url']!r}")

        minimal = Path(tmp) / "os-release-minimal"
        minimal.write_text('NAME="Bare"\n', encoding="utf-8")
        sparse = load_identity(str(PKGDATA), str(minimal), language="en")
        if sparse["distro_name"] != "Bare":
            fail(f"minimal os-release NAME not used: {sparse['distro_name']!r}")
        if sparse["website_url"] or sparse["forum_url"]:
            fail("missing URLs should remain empty")
        if sparse["release_label"] != "Bare":
            fail(f"unexpected sparse release_label: {sparse['release_label']!r}")

        damaged = Path(tmp) / "os-release-invalid-utf8"
        damaged.write_bytes(b'NAME="Damaged\xffOS"\nVERSION_ID="1"\n')
        try:
            resilient = load_identity(str(PKGDATA), str(damaged), language="en")
        except UnicodeError as error:
            fail(f"invalid UTF-8 os-release must not raise: {error}")
        if not resilient.get("distro_name"):
            fail("invalid UTF-8 os-release should still yield a distro_name")
        if "\ufffd" not in resilient["distro_name"] and "Damaged" not in resilient["distro_name"]:
            fail(f"unexpected damaged distro_name: {resilient['distro_name']!r}")
    ok("distribution identity follows /etc/os-release")

    from amonite_welcome.pages import load_pages_for_locale
    from amonite_welcome.strings import load_strings_for_locale
    from amonite_welcome import strings as i18n

    i18n.bind(load_strings_for_locale(str(PKGDATA), language="en"))
    pages = load_pages_for_locale(str(PKGDATA), identity, language="en")
    if len(pages) != EXPECTED_PAGE_COUNT:
        fail(f"expected {EXPECTED_PAGE_COUNT} pages, got {len(pages)}")
    ok(f"pages.en.yaml loads ({len(pages)} pages)")

    if "$distro_name" in pages[0].description:
        fail("placeholders left unsubstituted in page description")
    if pages[0].sections and pages[0].sections[0].heading != identity["slogan"]:
        fail(
            f"welcome page slogan heading {pages[0].sections[0].heading!r} "
            f"must match identity slogan {identity['slogan']!r}"
        )
    ok("placeholders substituted in editorial content")

    return dict(identity), pages


def verify_project_identity() -> None:
    """Project authoring loads declaratively and reaches the merged identity."""
    from amonite_welcome.identity import (
        AUTHORING_FIELDS,
        AUTHORING_URL_FIELDS,
        IdentityError,
        load_identity,
        load_project_identity,
    )

    project = load_project_identity(str(PKGDATA))
    for field in AUTHORING_FIELDS.values():
        if not project.get(field, "").strip():
            fail(f"project identity field is empty: {field}")
    for field in AUTHORING_URL_FIELDS:
        if not project[field].startswith("https://"):
            fail(f"project identity {field} is not an https URL: {project[field]!r}")

    sponsor = project["project_sponsor_url"]
    if not sponsor.startswith("https://github.com/sponsors/") or sponsor.rstrip("/").count(
        "/"
    ) != 4:
        fail(f"sponsor URL is not a GitHub Sponsors account URL: {sponsor!r}")

    merged = load_identity(str(PKGDATA), language="en")
    for field, value in project.items():
        if merged.get(field) != value:
            fail(f"merged identity dropped project field {field}")
    ok(f"project authoring loads from identity.base.yaml ({len(project)} fields)")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "identity.base.yaml").write_text(
            "schema_version: 2\ndesktop_id: amonite-welcome\n", encoding="utf-8"
        )
        try:
            load_project_identity(str(tmp_path))
        except IdentityError:
            ok("a missing authoring section raises IdentityError")
        else:
            fail("a missing authoring section should raise IdentityError")


def verify_desktop_identity() -> None:
    """Desktop metadata comes from the distribution and degrades to nothing."""
    from amonite_welcome.identity import load_desktop_identity, load_identity
    from amonite_welcome.pages import load_pages_for_locale

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        bare = tmp_path / "os-release-bare"
        bare.write_text('NAME="Bare"\n', encoding="utf-8")
        absent = load_desktop_identity(str(bare), ())
        if any(absent.values()):
            fail(f"desktop fields must stay empty without metadata: {absent!r}")
        ok("absent desktop metadata yields empty fields, not a default")

        vendor = tmp_path / "os-release-vendor"
        vendor.write_text(
            'NAME="Bare"\n'
            'AMONITE_DESKTOP_NAME="Session"\n'
            'AMONITE_DESKTOP_VERSION="4.2"\n',
            encoding="utf-8",
        )
        namespaced = load_desktop_identity(str(vendor), ())
        if namespaced["desktop_env_name"] != "Session":
            fail(f"vendor os-release desktop name not used: {namespaced!r}")
        if namespaced["desktop_env_label"] != "Session 4.2":
            fail(f"unexpected desktop label: {namespaced['desktop_env_label']!r}")

        generic = tmp_path / "os-release-generic"
        generic.write_text(
            'NAME="Bare"\n'
            'DESKTOP_NAME="Session"\n'
            'DESKTOP_VERSION="4.2"\n'
            'DESKTOP_PRETTY_NAME="Session Desktop 4.2"\n',
            encoding="utf-8",
        )
        plain = load_desktop_identity(str(generic), ())
        if plain["desktop_env_label"] != "Session Desktop 4.2":
            fail(f"DESKTOP_PRETTY_NAME not preferred: {plain['desktop_env_label']!r}")
        ok("os-release desktop extensions load (vendor and generic spellings)")

        dropin = tmp_path / "desktop-release"
        dropin.write_text('NAME="Shell"\nVERSION="1.0"\n', encoding="utf-8")
        overridden = load_desktop_identity(
            str(vendor), (str(tmp_path / "missing-release"), str(dropin))
        )
        if overridden["desktop_env_name"] != "Shell":
            fail(f"desktop drop-in must win over os-release: {overridden!r}")
        if overridden["desktop_env_label"] != "Shell 1.0":
            fail(f"unexpected drop-in label: {overridden['desktop_env_label']!r}")
        ok("desktop drop-in overrides os-release and skips missing paths")

        # The handbook must survive both states without leaking placeholders.
        without = dict(
            load_identity(str(PKGDATA), str(bare), language="en", desktop_release_paths=())
        )
        with_desktop = dict(
            load_identity(
                str(PKGDATA), str(bare), language="en", desktop_release_paths=(str(dropin),)
            )
        )
        pages_without = load_pages_for_locale(str(PKGDATA), without, language="en")
        pages_with = load_pages_for_locale(str(PKGDATA), with_desktop, language="en")

        for pages, label in ((pages_without, "absent"), (pages_with, "present")):
            for page in pages:
                for section in page.sections:
                    if "$desktop" in section.body or "$desktop" in section.heading:
                        fail(f"desktop placeholder left unsubstituted ({label}): {section!r}")

        sections_without = sum(len(page.sections) for page in pages_without)
        sections_with = sum(len(page.sections) for page in pages_with)
        if sections_with != sections_without + 1:
            fail(
                "desktop metadata should add exactly one handbook section "
                f"(without={sections_without}, with={sections_with})"
            )
        if not any(
            "Shell 1.0" in section.body
            for page in pages_with
            for section in page.sections
        ):
            fail("desktop label did not reach handbook prose")
        if any(
            "Shell" in section.body for page in pages_without for section in page.sections
        ):
            fail("desktop prose shown without desktop metadata")
        if len(pages_without) != EXPECTED_PAGE_COUNT:
            fail(f"missing desktop metadata changed the page count: {len(pages_without)}")
    ok("missing desktop metadata omits the section instead of failing")


def verify_error_handling() -> None:
    from amonite_welcome.identity import IdentityError, load_identity
    from amonite_welcome.pages import PagesError, load_pages

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "identity.en.yaml").write_text("app_name: Welcome\n", encoding="utf-8")
        try:
            load_identity(str(tmp_path), language="en")
        except IdentityError:
            ok("missing identity fields raise IdentityError")
        else:
            fail("missing identity fields should raise IdentityError")

        try:
            load_identity(str(PKGDATA / "identity.en.yaml"), language="en")
        except IdentityError:
            ok("load_identity rejects a YAML path")
        else:
            fail("load_identity should reject a YAML file path")

        bad_pages = Path(tmp) / "pages.yaml"
        bad_pages.write_text("pages: []\n", encoding="utf-8")
        try:
            load_pages(str(bad_pages))
        except PagesError:
            ok("empty pages list raises PagesError")
        else:
            fail("empty pages list should raise PagesError")

        bad_yaml = Path(tmp) / "broken.yaml"
        bad_yaml.write_text("pages:\n  - title: x\n    sections: bad\n", encoding="utf-8")
        try:
            load_pages(str(bad_yaml))
        except PagesError:
            ok("invalid pages structure raises PagesError")
        else:
            fail("invalid pages structure should raise PagesError")

        unknown_command = Path(tmp) / "unknown-command.yaml"
        unknown_command.write_text(
            "pages:\n  - title: x\n    actions:\n      - label: x\n        command: not-a-command\n",
            encoding="utf-8",
        )
        try:
            load_pages(str(unknown_command))
        except PagesError:
            ok("unknown command id raises PagesError")
        else:
            fail("unknown command id should raise PagesError")

        unknown_data = Path(tmp) / "unknown-data.yaml"
        unknown_data.write_text(
            "pages:\n  - title: x\n    sections:\n      - heading: h\n        data: not-a-source\n",
            encoding="utf-8",
        )
        try:
            load_pages(str(unknown_data))
        except PagesError:
            ok("unknown data source raises PagesError")
        else:
            fail("unknown data source should raise PagesError")

        # Security regressions: URL schemes and autostart field injection.
        from amonite_welcome.identity import (
            is_safe_web_url,
            load_os_identity,
            sanitize_web_url,
        )

        for bad in (
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,hi",
            "mailto:x@y",
            "/etc/passwd",
            "https://example.test/\nExec=evil",
            "",
        ):
            if is_safe_web_url(bad) or sanitize_web_url(bad):
                fail(f"unsafe URL must be rejected: {bad!r}")
        if not is_safe_web_url("https://example.test/docs"):
            fail("https URL must be accepted")
        if not is_safe_web_url("http://example.test/docs"):
            fail("http URL must be accepted")

        hostile = Path(tmp) / "os-release-hostile-url"
        hostile.write_text(
            'NAME="Hostile"\nHOME_URL="file:///etc/passwd"\nSUPPORT_URL="javascript:alert(1)"\n',
            encoding="utf-8",
        )
        from amonite_welcome.identity import read_metadata_file

        read_metadata_file.cache_clear()
        cleaned = load_os_identity(str(hostile))
        if cleaned["website_url"] or cleaned["forum_url"]:
            fail(
                "hostile os-release URLs must sanitize to empty: "
                f"website={cleaned['website_url']!r} forum={cleaned['forum_url']!r}"
            )
        ok("hostile os-release URL schemes sanitize to empty")

        evil_pages = Path(tmp) / "evil-url.yaml"
        evil_pages.write_text(
            "pages:\n  - title: x\n    actions:\n"
            "      - label: x\n        url: file:///etc/passwd\n",
            encoding="utf-8",
        )
        try:
            load_pages(str(evil_pages), {"website_url": "https://example.test/"})
        except PagesError:
            ok("handbook file:// action URL raises PagesError")
        else:
            fail("handbook file:// action URL must raise PagesError")

        degraded = Path(tmp) / "degraded-url.yaml"
        degraded.write_text(
            "pages:\n  - title: x\n    sections:\n      - heading: h\n        body: b\n"
            "    actions:\n      - label: Docs\n        url: $website_url\n",
            encoding="utf-8",
        )
        pages = load_pages(
            str(degraded),
            {"distro_name": "X", "website_url": "", "forum_url": ""},
        )
        if pages[0].actions:
            fail("empty substituted website_url must omit the URL-only action")
        ok("empty website_url degrades by omitting URL-only actions")

        from amonite_welcome import autostart as autostart_mod
        from amonite_welcome import identity as identity_api
        from amonite_welcome.identity import load_identity

        identity_api.bind(load_identity(str(PKGDATA), language="en"))
        injected = autostart_mod._format_entry(
            autostart_mod._ENABLED_ENTRY_TEMPLATE,
            "Welcome\nExec=/tmp/evil\nX-Injected=1",
        )
        key_lines = [
            line.split("=", 1)[0]
            for line in injected.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        ]
        if "X-Injected" in key_lines:
            fail(f"autostart must not inject extra desktop keys:\n{injected}")
        if key_lines.count("Exec") != 1:
            fail(f"autostart must keep a single Exec= key:\n{injected}")
        if any(line.startswith("Exec=/tmp/evil") for line in injected.splitlines()):
            fail(f"autostart Exec= must not become attacker-controlled:\n{injected}")
        if "Exec=amonite-welcome" not in injected:
            fail(f"autostart Exec= must remain the desktop id:\n{injected}")
        ok("autostart desktop entry rejects newline key injection")


def _locale_probe(env_overrides: dict[str, str]) -> tuple[str, str, str]:
    pkgdatadir = str(PKGDATA)
    script = f"""
import os
import sys

sys.path.insert(0, {pkgdatadir!r})
for variable in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
    os.environ.pop(variable, None)
os.environ.update({env_overrides!r})

from amonite_welcome.identity import load_identity
from amonite_welcome.pages import load_pages_for_locale

identity = load_identity({pkgdatadir!r})
pages = load_pages_for_locale({pkgdatadir!r}, identity)
print(pages[0].title)
print(identity["app_name"])
print(identity["slogan"])
"""
    env = os.environ.copy()
    for variable in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        env.pop(variable, None)
    env.update(env_overrides)
    env["PYTHONPATH"] = pkgdatadir
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        fail(
            "locale scenario subprocess failed:\n"
            f"  env={env_overrides!r}\n"
            f"  {result.stderr.strip()}"
        )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 3:
        fail(f"locale scenario produced incomplete output: {result.stdout!r}")
    return lines[0], lines[1], lines[2]


def verify_locale_resolution() -> None:
    english_slogan = yaml.safe_load(
        (PKGDATA / "identity.en.yaml").read_text(encoding="utf-8")
    )["slogan"]
    for env_overrides, expected_title in LOCALE_SCENARIOS:
        title, app_name, slogan = _locale_probe(env_overrides)
        label = env_overrides or {"LANG": "(unset)"}
        if title != expected_title:
            fail(
                f"locale {label!r}: expected first page {expected_title!r}, got {title!r}"
            )
        if app_name != expected_title:
            fail(
                f"locale {label!r}: identity app_name {app_name!r} "
                f"must match handbook title {expected_title!r}"
            )
        # Non-English locales must not silently keep the English slogan.
        if expected_title != "Welcome" and slogan == english_slogan:
            fail(f"locale {label!r}: identity slogan still English")
    ok(f"system locale resolves handbook + identity ({len(LOCALE_SCENARIOS)} scenarios)")


def verify_editorial_languages(identity: dict[str, str]) -> None:
    from amonite_welcome.identity import load_identity
    from amonite_welcome.pages import find_pages_path, load_pages_for_locale

    pkgdatadir = str(PKGDATA)
    languages = discover_editorial_languages()
    english_structure = handbook_structure(PKGDATA / "pages.en.yaml")
    english_slogan = identity["slogan"]

    for language in languages:
        localized = load_identity(pkgdatadir, language=language)
        pages = load_pages_for_locale(pkgdatadir, localized, language=language)
        if len(pages) != EXPECTED_PAGE_COUNT:
            fail(
                f"pages.{language}.yaml: expected {EXPECTED_PAGE_COUNT} pages, "
                f"got {len(pages)}"
            )
        if find_pages_path(pkgdatadir, language) != str(PKGDATA / f"pages.{language}.yaml"):
            fail(f"pages.{language}.yaml: unexpected path resolution")
        if language != "en":
            structure = handbook_structure(PKGDATA / f"pages.{language}.yaml")
            if structure != english_structure:
                fail(f"pages.{language}.yaml structure differs from pages.en.yaml")
            if localized["slogan"] == english_slogan:
                fail(f"identity.{language}.yaml slogan still English")
            if pages[0].sections and pages[0].sections[0].heading != localized["slogan"]:
                fail(
                    f"pages.{language}.yaml: $slogan resolved to "
                    f"{pages[0].sections[0].heading!r}, expected {localized['slogan']!r}"
                )
    ok(f"editorial editions load ({len(languages)} languages)")

    english = load_pages_for_locale(pkgdatadir, identity, language="en")
    for unsupported in ("ja", "xx"):
        pages = load_pages_for_locale(pkgdatadir, identity, language=unsupported)
        if pages[0].title != english[0].title:
            fail(f"locale {unsupported!r} should fall back to English")
        fallback = load_identity(pkgdatadir, language=unsupported)
        if fallback["app_name"] != identity["app_name"]:
            fail(f"identity locale {unsupported!r} should fall back to English")
    ok("unsupported locales fall back to English")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shutil.copy(PKGDATA / "pages.en.yaml", tmp_path / "pages.en.yaml")
        pages = load_pages_for_locale(str(tmp_path), identity, language="de")
        if pages[0].title != english[0].title:
            fail("missing translation should fall back to English")
    ok("missing translation file falls back to English")


def verify_system_info() -> None:
    from amonite_welcome import system_info
    from amonite_welcome.strings import load_strings_for_locale
    from amonite_welcome import strings as i18n

    i18n.bind(load_strings_for_locale(str(PKGDATA), language="en"))

    os_facts = system_info.os_facts()
    if not os_facts:
        fail("os_facts() returned no facts on this system")
    ok(f"os_facts() ({len(os_facts)} facts)")

    hardware_facts = system_info.hardware_facts()
    if hardware_facts:
        ok(f"hardware_facts() ({len(hardware_facts)} facts)")
    else:
        ok("hardware_facts() returned no facts (skipped on this system)")

    if "build_facts" in system_info.DATA_READERS:
        fail("build_facts should not be registered")
    ok("DATA_READERS exposes only user-facing fact sources")


def verify_capability_resolution() -> None:
    os.environ["AMONITE_WELCOME_PKGDATADIR"] = str(PKGDATA)

    from amonite_welcome import strings as i18n
    from amonite_welcome.actions import (
        CapabilityUnavailableError,
        available,
        known_capabilities,
        launch,
        open_package_manager,
        open_system_update,
        providers,
        reload_registry,
    )
    from amonite_welcome.strings import load_strings_for_locale

    i18n.bind(load_strings_for_locale(str(PKGDATA), language="en"))
    reload_registry()

    if not (PKGDATA / "providers.yaml").is_file():
        fail("providers.yaml missing from install prefix")
    ok("providers.yaml installed")

    expected = {
        "package-manager",
        "system-update",
        "desktop-settings",
        "network-settings",
    }
    caps = known_capabilities()
    if caps != expected:
        fail(f"known_capabilities mismatch: {caps!r}")
    ok(f"known_capabilities ({len(caps)} capabilities)")

    if not providers("package-manager"):
        fail("package-manager has no configured providers")
    if not providers("terminal"):
        fail("terminal has no configured providers")
    ok("providers() returns configured provider lists")

    # Package manager: optional; absence must be graceful without naming providers.
    try:
        argv = open_package_manager()
    except CapabilityUnavailableError as error:
        detail = str(error).lower()
        for leak in ("synaptic", "kitty", "xfce", "gnome-", "/usr/"):
            if leak in detail:
                fail(f"package-manager error leaks provider detail: {error}")
        if available("package-manager"):
            fail("available(package-manager) should be False when unresolved")
        ok("package-manager absence raises CapabilityUnavailableError")
    else:
        if not argv:
            fail(f"unexpected package-manager argv: {argv}")
        if not available("package-manager"):
            fail("available(package-manager) should be True when resolved")
        ok("package-manager resolves when a provider is installed")

    # System update needs a terminal provider.
    try:
        argv = open_system_update()
    except CapabilityUnavailableError as error:
        detail = str(error).lower()
        for leak in ("kitty", "xfce4-terminal", "gnome-terminal", "x-terminal-emulator"):
            if leak in detail:
                fail(f"system-update error leaks provider detail: {error}")
        ok("system-update absence raises CapabilityUnavailableError")
    else:
        if not argv:
            fail("system-update returned empty argv")
        ok("system-update resolves via a terminal provider")

    try:
        launch("not-a-real-capability")
    except ValueError:
        ok("unknown capability raises ValueError")
    else:
        fail("unknown capability should raise ValueError")

    for bad in ("synaptic", "kitty", "xfce4-settings-manager"):
        if bad in caps:
            fail(f"capability id must not be an executable name: {bad}")
    ok("capability ids are not executable names")


def verify_desktop_files(identity: dict[str, str]) -> None:
    app_name = identity["app_name"]
    name_line = None
    icon_line = None
    for line in MENU_DESKTOP.read_text(encoding="utf-8").splitlines():
        if line.startswith("Name="):
            name_line = line.partition("=")[2]
        elif line.startswith("Icon="):
            icon_line = line.partition("=")[2]
    if name_line != app_name:
        fail(f"{MENU_DESKTOP.name}: Name={name_line!r} must match identity app_name={app_name!r}")
    if icon_line != _ICON_NAME:
        fail(f"{MENU_DESKTOP.name}: Icon={icon_line!r} must be {_ICON_NAME!r} (no extension)")

    validator = shutil.which("desktop-file-validate")
    if validator is None:
        ok("desktop Name=/Icon= match; desktop-file-validate not installed (skipped)")
        return

    result = subprocess.run([validator, str(MENU_DESKTOP)], capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"{MENU_DESKTOP}: {result.stdout}{result.stderr}")

    template = ROOT / "data" / "autostart" / "amonite-welcome.desktop"
    if template.is_file():
        result = subprocess.run([validator, str(template)], capture_output=True, text=True)
        if result.returncode != 0:
            fail(f"{template}: {result.stdout}{result.stderr}")
    ok("menu desktop and autostart template validate; Name= and Icon= match")


def verify_icons() -> None:
    missing = []
    for size in _ICON_PNG_SIZES:
        path = ICON_ROOT / size / "apps" / f"{_ICON_NAME}.png"
        if not path.is_file():
            missing.append(path)
    if missing:
        fail(
            "hicolor icon theme incomplete:\n  "
            + "\n  ".join(str(path) for path in missing)
        )
    # Obsolete SVG must not return in source, gresource inputs, or hicolor.
    obsolete = ROOT / "data" / "icons" / "amonite-mark.svg"
    if obsolete.is_file():
        fail(f"obsolete icon asset must be removed: {obsolete}")
    scalable = ICON_ROOT / "scalable" / "apps" / f"{_ICON_NAME}.svg"
    if scalable.is_file():
        fail(f"scalable SVG icon must not be installed: {scalable}")
    gresource_xml = (ROOT / "data" / "amonite-welcome.gresource.xml.in").read_text(
        encoding="utf-8"
    )
    if "amonite-mark" in gresource_xml:
        fail("gresource must not reference amonite-mark.svg")
    ok(f"hicolor icons installed ({len(_ICON_PNG_SIZES)} PNG sizes; no obsolete SVG)")


def verify_gtk_application(identity: dict[str, str], pages: list) -> None:
    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib, Gtk

    resource = Gio.Resource.load(str(PKGDATA / "amonite-welcome.gresource"))
    for path in GRESOURCE_PATHS:
        if resource.lookup_data(path, Gio.ResourceLookupFlags.NONE) is None:
            fail(f"gresource missing {path}")
    ok("gresource bundles expected assets")

    resource._register()

    from amonite_welcome.window import WelcomeWindow

    warnings: list[str] = []

    def on_log(domain, level, message):
        if level in (GLib.LogLevelFlags.LEVEL_CRITICAL, GLib.LogLevelFlags.LEVEL_ERROR):
            warnings.append(message)

    GLib.log_set_handler("Gtk", GLib.LogLevelFlags.LEVEL_MASK, on_log)
    GLib.log_set_handler("GLib", GLib.LogLevelFlags.LEVEL_MASK, on_log)
    GLib.log_set_handler("Gdk", GLib.LogLevelFlags.LEVEL_MASK, on_log)

    app = Gtk.Application(application_id="org.amonite.Welcome.verify")
    window_holder: list[WelcomeWindow] = []

    def pump_events() -> None:
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def on_activate(application):
        from amonite_welcome import identity as identity_api
        from amonite_welcome import strings as i18n

        identity_api.bind(identity)
        window = WelcomeWindow(pages, identity, application=application)
        window_holder.append(window)

        expected_autostart = i18n.text("ui", "autostart_label")
        if window.autostart_button.get_label() != expected_autostart:
            fail(f"autostart label not localized: {window.autostart_button.get_label()!r}")

        if window.get_title() != f"{identity['distro_name']} {identity['app_name']}":
            fail(f"window title: {window.get_title()!r}")
        default_width, default_height = window.get_default_size()
        if (default_width, default_height) != (960, 700):
            fail(
                f"preferred default size expected 960x700, "
                f"got {default_width}x{default_height}"
            )
        # GTK4 has no get_size_request(); confirm the source sets the floor.
        window_source = (ROOT / "amonite_welcome" / "window.py").read_text(encoding="utf-8")
        if "set_size_request(_MIN_WIDTH, _MIN_HEIGHT)" not in window_source and (
            "set_size_request(800, 600)" not in window_source
        ):
            fail("window.py must set minimum size to 800x600")
        for forbidden in (
            "get_workarea",
            "get_monitor_at_surface",
            "get_default_seat",
            "adaptive_default_size",
            "_resolve_monitor",
            "_work_area_size",
        ):
            if forbidden in window_source:
                fail(f"window.py must not contain platform sizing heuristic: {forbidden}")
        ok("canonical preferred size 960x700; minimum 800x600; no monitor heuristics")
        if window.distro_footer_label.get_label() != identity["release_label"]:
            fail(f"footer label: {window.distro_footer_label.get_label()!r}")
        if window.sidebar.get_row_at_index(len(pages) - 1) is None:
            fail("sidebar row count does not match page count")

        # Accessibility: focusable controls and GTK accessible semantics.
        if not window.sidebar.get_focusable():
            fail("sidebar must be focusable for keyboard navigation")
        if not window.autostart_button.get_focusable():
            fail("autostart checkbox must be focusable")
        expected_sidebar = i18n.text("ui", "sidebar_label", default="Chapters")
        if "_set_accessible_label" not in window_source or "_mark_decorative" not in window_source:
            fail("window.py must expose accessible labels and mark decorative images")
        if "AccessibleRole.PRESENTATION" not in window_source:
            fail("decorative images must use PRESENTATION accessible role")
        if "AccessibleRole.HEADING" not in window_source:
            fail("page and section titles must use HEADING accessible role")
        if "_set_paragraph" not in window_source:
            fail("prose labels must set an explicit non-heading accessible role")
        if 'f"{label}: {value}"' not in window_source:
            fail("fact values must expose paired accessible labels")
        if "grab_focus()" not in window_source:
            fail("sidebar must receive initial keyboard focus")
        if "Gtk.AlertDialog" not in window_source:
            fail("errors must use Gtk.AlertDialog for accessible dialogs")
        css_text = (ROOT / "data" / "style.css").read_text(encoding="utf-8")
        for forbidden_css in ("outline:", "outline-style:", "outline-width:", "outline-color:", "max-width:"):
            if forbidden_css in css_text:
                fail(f"custom CSS must not use unsupported/overriding property {forbidden_css}")

        def find_action_lists(widget):
            found = []
            if isinstance(widget, Gtk.ListBox) and "action-list" in (
                widget.get_css_classes() or []
            ):
                found.append(widget)
            child = widget.get_first_child() if hasattr(widget, "get_first_child") else None
            while child is not None:
                found.extend(find_action_lists(child))
                child = child.get_next_sibling()
            return found

        # Keyboard workflow: sidebar → pages → actions → checkbox (no mouse).
        # Do not emit row-activated here: that would launch real providers.
        window.sidebar.grab_focus()
        pump_events()
        if window.get_focus() is None:
            fail("window lost keyboard focus after sidebar.grab_focus()")
        pages_with_actions = 0
        for index in range(len(pages)):
            row = window.sidebar.get_row_at_index(index)
            if not row.get_focusable():
                fail(f"sidebar row {index} must be focusable")
            window.sidebar.select_row(row)
            row.grab_focus()
            pump_events()
            if window.stack.get_visible_child_name() != pages[index].title:
                fail(f"keyboard navigation failed for page {pages[index].title!r}")
            child = window.stack.get_visible_child()
            action_lists = find_action_lists(child) if child is not None else []
            expected_actions = [
                action
                for action in pages[index].actions
                if action.command or action.url
            ]
            if len(action_lists) != (1 if expected_actions else 0):
                fail(
                    f"page {pages[index].title!r}: expected "
                    f"{1 if expected_actions else 0} action list(s), found {len(action_lists)}"
                )
            for actions in action_lists:
                if not actions.get_focusable():
                    fail("action list must be focusable")
                pages_with_actions += 1
                for action_index, _action in enumerate(expected_actions):
                    action_row = actions.get_row_at_index(action_index)
                    if action_row is None or not action_row.get_focusable():
                        fail(
                            f"action row {action_index} on "
                            f"{pages[index].title!r} must be focusable"
                        )
                    action_row.grab_focus()
                    pump_events()
                    if window.get_focus() is None:
                        fail(
                            f"focus lost after focusing action on "
                            f"{pages[index].title!r}"
                        )
        window.autostart_button.grab_focus()
        pump_events()
        if window.get_focus() is not window.autostart_button:
            fail("autostart checkbox did not accept keyboard focus")
        # AlertDialog is GTK-owned; exercise presentation once without launching apps.
        window._show_error("Accessibility probe", "Dialog focus is GTK-managed.")
        pump_events()
        # Stress: repeated page changes must not drop sidebar focusability.
        for _cycle in range(3):
            for index in range(len(pages)):
                window.sidebar.select_row(window.sidebar.get_row_at_index(index))
                pump_events()
            window.sidebar.grab_focus()
            pump_events()
            if window.get_focus() is None:
                fail("focus lost during repeated keyboard page navigation")
        ok(
            f"keyboard navigation and accessibility semantics "
            f"(sidebar {expected_sidebar!r}; {pages_with_actions} action page(s))"
        )

        for index in range(len(pages)):
            row = window.sidebar.get_row_at_index(index)
            window.sidebar.select_row(row)
            pump_events()
            visible = window.stack.get_visible_child_name()
            if visible != pages[index].title:
                fail(f"navigation to {pages[index].title!r} showed {visible!r}")
            ok(f"navigated to {pages[index].title}")

        from amonite_welcome import autostart as autostart_mod

        override = autostart_mod.override_path()
        prior_enabled = autostart_mod.is_enabled()
        prior_text = override.read_text(encoding="utf-8") if override.is_file() else None

        # Default must be enabled on a fresh profile.
        if not autostart_mod.is_enabled():
            # Clear a leftover Hidden=true from a previous run before asserting.
            if override.is_file() and "Hidden=true" in override.read_text(encoding="utf-8"):
                override.unlink()
        if not autostart_mod.is_enabled():
            fail("autostart must default to enabled when the user has not opted out")
        if not window.autostart_button.get_active():
            fail("autostart checkbox must be active by default")

        window.autostart_button.set_active(False)
        pump_events()
        if not override.is_file():
            fail("disabling autostart did not write a user override")
        if "Hidden=true" not in override.read_text(encoding="utf-8"):
            fail("disabling autostart must set Hidden=true on the user override")
        if autostart_mod.is_enabled():
            fail("autostart reports enabled after disable")
        validator = shutil.which("desktop-file-validate")
        if validator is not None:
            result = subprocess.run([validator, str(override)], capture_output=True, text=True)
            if result.returncode != 0:
                fail(f"disabled autostart entry invalid: {result.stdout}{result.stderr}")

        window.autostart_button.set_active(True)
        pump_events()
        if not autostart_mod.is_enabled():
            fail("autostart reports disabled after re-enable")
        # With a system entry, re-enable removes the override; without one, writes it.
        if autostart_mod.system_entry_path() is not None:
            if override.exists() and "Hidden=true" in override.read_text(encoding="utf-8"):
                fail("re-enabling must unmask the system autostart entry")
        else:
            if not override.is_file():
                fail("re-enabling without system autostart did not create a user entry")
            entry = override.read_text(encoding="utf-8")
            if "Hidden=true" in entry:
                fail("re-enabled user autostart must not be Hidden")
            for required in ("Type=Application", "Exec=amonite-welcome", "Icon=amonite-welcome"):
                if required not in entry:
                    fail(f"autostart entry missing {required!r}")

        # Restore prior user preference.
        if prior_text is not None:
            override.write_text(prior_text, encoding="utf-8")
        elif override.exists():
            override.unlink()
        # Leave default-enabled semantics for the next run if there was no prior file.
        if not prior_enabled and override.exists():
            # User had opted out before the test started.
            pass

        application.quit()

    app.connect("activate", on_activate)
    app.run([])

    if warnings:
        fail("GTK critical/error messages:\n  " + "\n  ".join(warnings))
    ok("GTK window, navigation and autostart enable/disable/re-enable")


def main() -> int:
    require_build()

    verify_config()
    identity, pages = verify_identity_and_pages()
    verify_project_identity()
    verify_desktop_identity()
    verify_editorial_languages(identity)
    verify_locale_resolution()
    verify_error_handling()
    verify_system_info()
    verify_capability_resolution()
    verify_desktop_files(identity)
    verify_icons()
    verify_gtk_application(identity, pages)

    print("\nAll verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
