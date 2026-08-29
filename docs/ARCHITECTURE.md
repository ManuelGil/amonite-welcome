# Architecture

Amonite Welcome is a small GTK 4 / Python application. Boundaries stay separate
so each kind of change has one obvious place.

## Layers

| Layer | Location | Responsibility |
| ----- | -------- | -------------- |
| Application entry | `amonite_welcome/app.py`, `__main__.py` | GTK Application, GResource, theme, startup errors |
| Launcher options | `cli.py` | `--help`, `--version`, `--capabilities`; never opens GTK |
| Content | `content.py`, `data/pages.*.yaml` | Handbook model; load, validate, locale, placeholders |
| Presentation | `ui/window.py`, `ui/navigation.py`, `ui/page_view.py`, `data/ui/window.ui` | Shell, chapter list, page composition |
| Components | `ui/components.py`, `ui/a11y.py` | Semantic widgets and their accessible roles |
| Behaviour | `ui/activation.py` | Runs an action: capability, URI, error dialogs |
| Theme | `theme/palette.py`, `theme/system.py`, `theme/theme.py`, `data/theme/components.css` | Desktop colours in, readable semantic roles out |
| Capabilities | `services/capabilities.py`, `services/providers.py` + `data/providers.yaml` | Availability policy; generic provider resolver |
| UI strings | `services/catalog.py`, `data/strings.*.yaml` | Chrome, dialogs, facts, capability messages |
| Identity | `services/identity.py`, `data/identity.base.yaml`, `data/identity.<lang>.yaml`, `/etc/os-release` | Application, project, distribution, desktop |
| System facts | `services/system_info.py` | Live `data:` sections (os / hardware) |
| Autostart | `services/autostart.py`, `/etc/xdg/autostart/` | Default on; user opt-out via `Hidden=true` |
| Build identity | top-level `meson.build`, `config.py.in` | App id, resource path, binary name |

Content never imports GTK; components never resolve a provider; the window
never builds page content. A page is chosen by its stable `id`, so navigation
does not depend on translated titles.

## Theme

Welcome does not decide what the system looks like. `theme/system.py` reads the
colours the running GTK theme already publishes (`theme_base_color`,
`theme_bg_color`, `theme_fg_color`, `theme_selected_bg_color`, `borders`) —
the set every GTK theme still defines — and falls back to a quiet built-in
palette, using `ANSI_COLOR` from `os-release` as an accent if the theme offers
none. `theme/palette.py` derives the semantic roles from that: surfaces from the
desktop's own background, muted text by mixing towards it, and an accent moved
along its own hue only as far as WCAG AA requires. Light and dark are the same
derivation applied to different input, not two palettes.

One CSS provider is composed as: derived `@aw_*` colours, then
`data/theme/components.css` (structure and rhythm, never a literal colour),
then an optional `<pkgdatadir>/theme/distro.css`, which is the single file a
distribution edits to redefine any role. `Theme` reloads when the desktop
changes appearance.

## Identity

`services/identity.py` merges four domains into one read-only mapping. Each domain owns
its own fields and nothing else. Callers use `identity.get(...)` /
`load_identity(pkgdatadir)` and never parse YAML or `os-release` themselves.

| Domain | Owns | Canonical source |
| ------ | ---- | ---------------- |
| Application | `app_name`, `slogan`, `generic_name`, `comment`, `desktop_id` | `identity.base.yaml` + `identity.<lang>.yaml` |
| Project authoring | `project_creator`, `project_maintainer`, `project_contact`, `project_website_url`, `project_repository_url`, `project_support_url`, `project_sponsor_url` | `identity.base.yaml` (`authoring:`) |
| Distribution | `distro_name`, `pretty_name`, `release_version`, `release_codename`, `release_label`, `edition_name`, `edition_id`, `website_url`, `forum_url` | `/etc/os-release` |
| Desktop | `desktop_env_name`, `desktop_env_version`, `desktop_env_label` | desktop metadata drop-in, then `/etc/os-release` |

`desktop_id` is the `.desktop` basename this application installs. It is
application identity and has nothing to do with the desktop environment, whose
fields are the `desktop_env_*` group. Meson `project()` name and installed
binary basename must equal `desktop_id`; `make validate` enforces
that alignment so there is still a single basename owner.

Desktop `Keywords=` live only in the installed menu and system autostart
`.desktop` files (kept identical by validation). Runtime user overrides written
by `services/autostart.py` intentionally omit Keywords; they exist only to set
`Hidden=true` or restore a minimal entry when no system autostart is present.

### Distribution metadata

Welcome declares no distribution fact and never ships a copy of one. Everything
is read at runtime: `$forum_url` resolves from `SUPPORT_URL`, then
`BUG_REPORT_URL`, then `HOME_URL`. The edition comes from the `VARIANT` and
`VARIANT_ID` keys `os-release(5)` defines for exactly that, so a distribution
that publishes one edition sets neither and the edition prose and the edition
fact are both omitted. Fields absent from `os-release` stay empty.

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
omitted. Nothing is guessed and nothing is shown half-filled. `services/system_info.py`
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
`$edition_name`, `$desktop_env_label`, and the `$project_*` group.

## Handbook commands and facts

- Capability ids in YAML are resolved by `services/providers.py` from `data/providers.yaml`
  (missing capabilities show a friendly error). See [ENGINEERING.md](ENGINEERING.md).
- Fact section ids map to `DATA_READERS` (`services/system_info.py`).
- A section may declare `requires:` with identity field names. When any of them
  is empty the section is dropped, so prose never depends on metadata the
  system did not publish.

## Generated files

Do not edit or commit:

- `amonite_welcome/config.py` (from `config.py.in`)
- GResource bundle and configured launcher scripts

These are produced under `builddir/amonite-welcome/`.

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
- Roles are passed when a widget is constructed (`accessible_role=`), never
  assigned afterwards. `accessible-role` is construct-only, and under GTK 4.14
  a later assignment reaches every widget of that class, so the last role set
  becomes the role of every heading, paragraph and decorative node. `verify`
  reads the roles back from the built window for this reason.
- Fact values expose a paired accessible name (`Label: value`); action rows
  expose descriptions. Prose uses an explicit non-heading accessible role so
  body text is not announced as a heading.
- An action with no provider is not built at all, so hiding it leaves no empty
  list, no gap in the focus order and nothing for a screen reader to announce.
- Custom CSS must not override theme focus outlines.
- Errors use `Gtk.AlertDialog` (no custom dialog keyboard handling).

## Stability

The project is in maintenance mode. Prefer fixing bugs, updating compatibility,
translations, and distribution integration over adding features.
