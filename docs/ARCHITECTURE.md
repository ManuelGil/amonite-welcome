# Architecture

Amonite Welcome is a small GTK 4 / Python application. Boundaries stay separate
so each kind of change has one obvious place.

## Layers

| Layer | Location | Responsibility |
| ----- | -------- | -------------- |
| Application entry | `amonite_welcome/main.py`, `__main__.py` | GTK Application, GResource, startup errors |
| Presentation | `window.py`, `data/ui/window.ui`, `data/style.css` | Sidebar, pages, actions |
| Handbook | `pages.py`, `data/pages.*.yaml` | Load, validate, locale, placeholders |
| External actions | `actions.py` + `data/providers.yaml` | Generic resolver; providers in registry |
| UI strings | `strings.py`, `data/strings.*.yaml` | Chrome, dialogs, facts, capability messages |
| Application identity | `identity.py`, `data/identity.base.yaml`, `data/identity.<lang>.yaml` | Localized `app_name`, `slogan`, `desktop_id` |
| Project authoring | `identity.py`, `data/identity.base.yaml` (`authoring:`) | Creator, maintainer, project URLs, sponsorship |
| Distribution identity | `identity.py` → `/etc/os-release` | Name, version, codename, URLs |
| Desktop identity | `identity.py` → desktop metadata drop-in, then `/etc/os-release` | Desktop name, version, label |
| System facts | `system_info.py` | Live `data:` sections (os / hardware) |
| Autostart | `autostart.py`, `/etc/xdg/autostart/` | Default on; user opt-out via `Hidden=true` |
| Build identity | top-level `meson.build`, `config.py.in` | App id, resource path, binary name |

## Identity

`identity.py` merges four domains into one read-only mapping. Each domain owns
its own fields and nothing else. Callers use `identity.get(...)` /
`load_identity(pkgdatadir)` and never parse YAML or `os-release` themselves.

| Domain | Owns | Canonical source |
| ------ | ---- | ---------------- |
| Application | `app_name`, `slogan`, `generic_name`, `comment`, `desktop_id` | `identity.base.yaml` + `identity.<lang>.yaml` |
| Project authoring | `project_creator`, `project_maintainer`, `project_contact`, `project_website_url`, `project_repository_url`, `project_support_url`, `project_sponsor_url` | `identity.base.yaml` (`authoring:`) |
| Distribution | `distro_name`, `pretty_name`, `release_version`, `release_codename`, `release_label`, `website_url`, `forum_url` | `/etc/os-release` |
| Desktop | `desktop_env_name`, `desktop_env_version`, `desktop_env_label` | desktop metadata drop-in, then `/etc/os-release` |

`desktop_id` is the `.desktop` basename this application installs. It is
application identity and has nothing to do with the desktop environment, whose
fields are the `desktop_env_*` group. Meson `project()` name and installed
binary basename must equal `desktop_id`; `make validate` enforces
that alignment so there is still a single basename owner.

Desktop `Keywords=` live only in the installed menu and system autostart
`.desktop` files (kept identical by validation). Runtime user overrides written
by `autostart.py` intentionally omit Keywords; they exist only to set
`Hidden=true` or restore a minimal entry when no system autostart is present.

### Distribution metadata

Welcome declares no distribution fact and never ships a copy of one. Everything
is read at runtime: `$forum_url` resolves from `SUPPORT_URL`, then
`BUG_REPORT_URL`, then `HOME_URL`. Fields absent from `os-release` stay empty.

### Desktop metadata

Welcome names no desktop environment anywhere. The distribution publishes it,
in `os-release` syntax, and the first source that carries a name wins:

1. `/etc/amonite/desktop-release` (local override)
2. `/usr/lib/amonite/desktop-release` (vendor default)
3. `/etc/os-release`, keys `AMONITE_DESKTOP_NAME` / `AMONITE_DESKTOP_VERSION` /
   `AMONITE_DESKTOP_PRETTY_NAME`, then the unprefixed `DESKTOP_*` spellings

The drop-in is checked first so that changing the desktop is a change to the
package that provides it, not to `base-files` and not to this application.

When no source publishes desktop metadata, every `desktop_env_*` field stays
empty and any handbook section that declares `requires: [desktop_env_label]` is
omitted. Nothing is guessed and nothing is shown half-filled. `system_info.py`
separately reports the desktop of the *running session* from
`XDG_CURRENT_DESKTOP`; that is a live fact, not identity.

### Project authoring

Creator, maintainer, contact, website, repository, support, and sponsorship are
declared once in the `authoring:` block of `data/identity.base.yaml` and reach
the runtime as `$project_*` placeholders. No module, catalog, or document
restates them; `debian/control`, `debian/copyright`, and `debian/changelog`
carry the literals Debian policy requires and are checked against the block by
`make validate`.

Handbook placeholders: `$distro_name`, `$website_url`, `$forum_url`, `$slogan`,
`$desktop_env_label`, and the `$project_*` group.

## Handbook commands and facts

- Capability ids in YAML are resolved by `actions.py` from `data/providers.yaml`
  (missing capabilities show a friendly error). See [ENGINEERING.md](ENGINEERING.md).
- Fact section ids map to `DATA_READERS` (`system_info.py`).
- A section may declare `requires:` with identity field names. When any of them
  is empty the section is dropped, so prose never depends on metadata the
  system did not publish.

## Generated files

Do not edit or commit:

- `amonite_welcome/config.py` (from `config.py.in`)
- GResource bundle and configured launcher scripts

These are produced under `builddir/` (or `obj-*/` when packaging).

## Window presentation

The handbook window suggests size only:

1. `set_size_request(800, 600)` — accessibility floor
2. `set_default_size(960, 700)` — preferred initial size
3. `present()` — show the window

GTK4 provides no portable API to request a centered top-level window
(`gtk_window_set_position` / `GTK_WIN_POS_CENTER` were removed with no
replacement). Freedesktop EWMH `_NET_WM_FULL_PLACEMENT` expects compositors to
perform reasonable placement; clients should not invent default coordinates.
Welcome therefore never moves windows, never queries monitors for placement,
and never special-cases a desktop environment.

## Accessibility

Keyboard and assistive technology support rely on GTK defaults:

- Initial focus lands on the chapter sidebar after `present()`.
- Focus order follows the visual layout: sidebar → page actions → footer checkbox.
- Accessible names use `Gtk.AccessibleProperty.LABEL`; headings use
  `AccessibleRole.HEADING`; decorative images use `AccessibleRole.PRESENTATION`.
- Fact values expose a paired accessible name (`Label: value`); action rows
  expose descriptions. Prose uses an explicit non-heading accessible role so
  body text is not announced as a heading.
- Custom CSS must not override theme focus outlines.
- Errors use `Gtk.AlertDialog` (no custom dialog keyboard handling).

## Stability

The project is in maintenance mode. Prefer fixing bugs, updating compatibility,
translations, and distribution integration over adding features.
