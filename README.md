# Amonite Welcome

First-run handbook for the [Amonite](https://amonite.org) desktop (Debian
Stable). It introduces the system after installation and opens optional
capabilities when a provider is available, without replacing system tools.

## Why it exists

New users need a short introduction, not another control panel. Welcome keeps
the base system minimal and points people to tools already on the machine.

## Features

- Short handbook: Welcome, First Steps, Your System, Help
- Localized handbook editions
- Distribution identity from `/etc/os-release`
- Desktop environment from distribution metadata (omitted when unpublished)
- Optional actions: package manager, updates, settings, network
- Login autostart enabled by default (user can opt out)

## Requirements

**Runtime:** python3 (≥ 3.10), python3-gi, python3-yaml, gir1.2-gtk-4.0 (GTK ≥ 4.10)

**Build:** meson (≥ 0.64), pkg-config, libgtk-4-dev, libglib2.0-dev, python-gi-dev,
desktop-file-utils

```bash
sudo apt install meson pkg-config libgtk-4-dev libglib2.0-dev python-gi-dev \
  python3-gi python3-yaml desktop-file-utils
```

## Build

```bash
make
```

Or with Meson directly:

```bash
meson setup builddir --prefix "$PWD/builddir/prefix"
meson compile -C builddir
meson install -C builddir
```

Without installing:

```bash
meson setup builddir && meson compile -C builddir
meson devenv -C builddir amonite-welcome
```

## Run

```bash
builddir/prefix/bin/amonite-welcome
```

## Test and validate

```bash
make validate
make verify
make check
```

## Package / release

```bash
make release
```

## Repository layout

| Path | Role |
| ---- | ---- |
| `amonite_welcome/` | Application |
| `data/` | Identity, providers, handbook, UI, icons |
| `debian/` | Native Debian packaging |
| `docs/` | Permanent maintainer documentation |
| `packaging/` | Release validation and packaging pipeline |
| `health/` | Health baseline (`check.py`; generated reports ignored) |
| `security/` | Public signing key copy |
| `Makefile` | Maintainer interface |
| `dist/` | Generated release artifacts (gitignored) |

## Documentation

| Document | Topic |
| -------- | ----- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module boundaries and identity |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | How to contribute |
| [docs/TRANSLATING.md](docs/TRANSLATING.md) | Handbook translations |
| [docs/RELEASE.md](docs/RELEASE.md) | Versioning and release checklist |
| [docs/ENGINEERING.md](docs/ENGINEERING.md) | Pipeline, health, maintenance contract |
| [docs/SECURITY.md](docs/SECURITY.md) | Security reporting |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Release notes |

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
