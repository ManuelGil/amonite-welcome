# Handbook and UI string translations

How to contribute translations to Amonite Welcome.

For general contribution rules, see [CONTRIBUTING.md](CONTRIBUTING.md).
For the capability registry and maintainer tool, see [ENGINEERING.md](ENGINEERING.md).

Amonite Welcome does **not** use gettext/PO catalogs. User-visible text ships as
complete YAML editions selected from the system locale.

## Catalogs

| Catalog | Files | Contents |
| ------- | ----- | -------- |
| Product identity | `data/identity.<lang>.yaml` (+ `identity.base.yaml`) | App name, slogan, desktop Name/GenericName/Comment |
| Handbook | `data/pages.<lang>.yaml` | Chapter titles, prose, action labels |
| UI strings | `data/strings.<lang>.yaml` | Chrome, dialogs, fact labels, capability messages |
| Desktop entries | `data/*.desktop` | Must match identity catalogs (`Name[lang]`, …) |

`identity.en.yaml`, `pages.en.yaml`, and `strings.en.yaml` are the canonical
English sources.

## Why YAML, not gettext

Handbook content is long-form prose edited as structured documents. UI chrome
uses the same locale model so maintainers review one format. Capability
identifiers (`command:`) and provider registries stay untranslated.

## How languages are selected

At startup the application reads the system locale (`LC_ALL`, then
`LC_MESSAGES`, then `LANG`) and maps it to a two-letter language code.
Regional variants share one edition: `es_ES` and `es_CO` both load
`pages.es.yaml`, `strings.es.yaml`, and `identity.es.yaml`.

If a language file does not exist, English loads silently.

```bash
make
LANG=it_IT.UTF-8 builddir/amonite-welcome/prefix/bin/amonite-welcome
LANG=de_DE.UTF-8 builddir/amonite-welcome/prefix/bin/amonite-welcome
```

## Shipped languages

- English - `pages.en.yaml` / `strings.en.yaml` / `identity.en.yaml` (canonical)
- Spanish - `es`
- Portuguese - `pt`
- Italian - `it`
- French - `fr`
- German - `de`
- Dutch - `nl`

## Standardized terminology

Use consistent wording across handbook actions, capability messages, and UI:

| English | Meaning |
| ------- | ------- |
| Package Manager | Capability `package-manager` |
| Desktop Settings | Capability `desktop-settings` |
| Network Connections / Network Settings | Capability `network-settings` |
| Update the System / System Update | Capability `system-update` |
| Software | Capability `software-install` |
| Documentation | URL action to project docs |
| Support | URL action to support channels |

Never expose executable names (Synaptic, Kitty, xfce4-settings-manager) in
user-visible text.

Never name a distribution or a desktop environment either. Both arrive at
runtime: write `$distro_name` and `$desktop_env_label`, never the literal. A
section that mentions the desktop must keep its `requires: [desktop_env_label]`
line so it disappears on systems that publish no desktop metadata. The edition
works the same way: write `$edition_name` and keep `requires: [edition_name]`,
so the section disappears on a distribution that publishes a single edition.

## Translation rules

**Do:**

- Translate meaning, not word order.
- Use established Linux and Debian terminology.
- Keep technical names the ecosystem uses (Debian Stable, apt) when they are
  product nouns, not missing-tool diagnostics.

**Do not:**

- Add, remove, or reorder chapters, sections, or string keys.
- Change placeholders, capability ids, data ids, or icons.
- Translate `$placeholders` or their names.
- Leave English remnants in non-English catalogs.

### What must stay unchanged

| Field | Example | Reason |
| ----- | ------- | ------ |
| `$placeholders` | `$distro_name`, `$slogan`, `$website_url`, `$forum_url`, `$edition_name`, `$desktop_env_label` | Filled at runtime |
| `requires:` lists | `requires: [desktop_env_label]`, `requires: [edition_name]` | Hides the section when the value is missing |
| `command:` ids | `package-manager`, `system-update`, … | Must match `providers.yaml` |
| `data:` ids | `os_facts`, `hardware_facts` | Mapped to fact readers |
| `icon:` values | `go-home-symbolic` | Sidebar icons |
| YAML keys in `strings.*` | `dialogs.action_unavailable` | Looked up by code |
| YAML structure | page/action/key counts | Validated against English |

## Workflow

### Handbook

```bash
cp data/pages.en.yaml data/pages.it.yaml
# Translate editorial fields only.
make validate
```

### UI strings

```bash
cp data/strings.en.yaml data/strings.it.yaml
# Translate every value; keep every key.
make validate
```

### Product identity

```bash
cp data/identity.en.yaml data/identity.it.yaml
# Translate app_name, slogan, generic_name, comment.
# Keep desktop Name[lang] / GenericName[lang] / Comment[lang] in sync.
make validate
```

### Desktop locale keys

Update `Name[lang]`, `GenericName[lang]`, and `Comment[lang]` in both desktop
files so they match `identity.<lang>.yaml`.

### Verify

```bash
make
make verify
LANG=it_IT.UTF-8 builddir/amonite-welcome/prefix/bin/amonite-welcome
```

## Validation

`make validate` fails the release when catalogs are missing keys,
leave empty values, leak implementation details, break placeholders, or diverge
structurally from English.
