# Engineering

Maintainer guide for Amonite Welcome: pipeline, capabilities, health, and
maintenance contract.

Product architecture: [ARCHITECTURE.md](ARCHITECTURE.md).  
Release checklist: [RELEASE.md](RELEASE.md).  
Repository layout: [../README.md](../README.md).  
Where to change catalogs and UI: [CONTRIBUTING.md](CONTRIBUTING.md).

## Philosophy

Knowledge belongs in configuration and tooling, not scattered through code:

| Concern | Lives in |
| ------- | -------- |
| Capability providers | `data/providers.yaml` |
| UI / dialog strings | `data/strings.<lang>.yaml` |
| Handbook prose | `data/pages.*.yaml` |
| App branding | `data/identity.base.yaml` + `data/identity.<lang>.yaml` |
| Project authoring | `data/identity.base.yaml` (`authoring:`) |
| Distro identity | `/etc/os-release` (runtime) |
| Desktop identity | distribution desktop metadata (runtime) |
| Build / release | `Makefile` → `packaging/release.sh` |
| Packaging metadata | `debian/` (root; Debian convention) |

Do not hardcode desktop applications outside the capability registry, and do
not name a desktop environment anywhere; `validate` fails on both.

## Maintainer and author

| Role | Meaning | Recorded in |
| ---- | ------- | ----------- |
| Package Maintainer | Debian packaging | `debian/control` `Maintainer:`, changelog trailer, `debian/copyright` `Files: debian/*` |
| Project Author | Upstream project | `data/identity.base.yaml` `authoring:`, mirrored in `debian/copyright` |

Change authoring in `data/identity.base.yaml` first, then run `validate` and
update packaging literals it reports.

## Capability system

Handbook actions name **capabilities** (`command:` in YAML). Providers live in
`data/providers.yaml`. Runtime `actions.py` is a generic resolver
(`resolve` / `launch` / `available` / `providers` / `known_capabilities`).

Kinds: `application` (first available binary) and `terminal-command` (run
inside the first available terminal).

An action is offered only when this system has a provider for its capability
(`pages.visible_actions`). The handbook does not point at a tool the machine
does not have. Availability is read when the window is built, so a provider
installed later appears the next time Welcome starts, and activation resolves
again, keeping the unavailable message for a provider that disappears while
the window is open.

A provider is a plain executable name. Resolution is declaration order plus
what is installed, and nothing else: Welcome stays desktop-independent, so the
running session is reported by `--capabilities` and never decides what is
launched. The registry therefore lists the programs this system actually
installs; a program belonging to another desktop is not listed, so it cannot be
selected merely because someone installed its package. A capability no edition
provides degrades to its `strings.<lang>.yaml` message. `PATH` lookup also
covers the sbin directories, which graphical sessions frequently omit.

Terminal argv styles are the only technical mapping kept in Python. Terminals
disagree about `-e`, and the wrong shape is fatal at runtime: the terminal
tries to execute the whole command line as a program name and the user sees
"no such file or directory" instead of the command.

| Style | Shape |
| ----- | ----- |
| `exec-argv` | `terminal -e sh -c CMD` |
| `exec-string` | `terminal -e "sh -c CMD"` (one shell-quoted string) |
| `dash-dash` | `terminal -- sh -c CMD` |
| `plain` | `terminal sh -c CMD` |
| `start-argv` | `terminal start -- sh -c CMD` |
| `alternative` | alternatives symlink: adopt the target's style |

`x-terminal-emulator` must stay `alternative`. It is a symlink whose target the
administrator chooses, so its argv shape is read from that target (and from the
`.wrapper` convention) at runtime; any fixed style there is a bug. Shapes for
targets that are not themselves providers live under
`terminal.alternative_styles`: consulted only to talk to a target the symlink
already points at, never to select a terminal.

Each style is pinned per terminal in `packaging/validate-config.py`
(`VERIFIED_TERMINAL_STYLES`) and exercised end to end by `packaging/verify.py`,
which runs the produced argv against stub terminals that reproduce the real
parsing, including the alternatives path and the unknown-target fallback.
Verify a change against the terminal itself before editing the table.

Which program the system installs for each application capability is pinned in
`packaging/validate-config.py` (`DISTRIBUTION_PROVIDERS`). Adding a provider is
therefore a reviewed decision recorded next to the evidence for it, not a line
that quietly makes another desktop's tool reachable.

To extend providers or capabilities, edit `data/providers.yaml`, then:

```bash
make validate
make verify   # after install
```

To see what an installation resolves, on the machine that shows the problem:

```bash
amonite-welcome --capabilities
```

## Maintainer interface

Preferred entry point:

```bash
make                 # build
make validate
make verify
make check           # validate + verify + health
make release         # full signed pipeline → dist/
```

`make` targets delegate to `packaging/release.sh`. Additional stages
(`doctor`, `hygiene`, `distclean`, `finalize`, …) remain available as:

```bash
./packaging/release.sh [command]
```

Default command for the script (not Make): `release`.

| Command | Purpose |
| ------- | ------- |
| `release` | Full pipeline (`distclean` → package → finalize → `dist/`) |
| `doctor` | Toolchain diagnostics (read-only) |
| `hygiene` | Repository purity, ownership, and permissions (read-only) |
| `validate` | Catalogs, desktop, meson, authoring mirrors |
| `health` | Footprints, baseline, optional runtime metrics |
| `status` | Read-only repository / build / package state |
| `clean` / `distclean` | Remove rebuild trees; `distclean` also clears `dist/` |
| `configure` / `build` / `test` / `install` | Meson stages |
| `verify` | Post-install checks (`packaging/verify.py`) |
| `package` / `inspect` | Build `.deb` into `dist/` and inspect it |
| `finalize` | Checksums, Amonite Release Signing Key signatures, manifest |

Supporting scripts: `packaging/validate-config.py`, `packaging/verify.py`,
`health/check.py`.

### Cleaning

**clean** removes rebuild trees and keeps previously generated packages under
`dist/` only if you do not run `distclean`.
**distclean** also clears generated files under `dist/` and leftover Debian
metadata beside the source tree. **status** never modifies files.

### Self-preparation and exit codes

Missing `builddir` / `package-root` are prepared by `test`, `install`,
`verify`, `health`, and `inspect`. Foreign-owned artefacts block destructive
commands with exit **2**. Engineering failures exit **1**. Success exits **0**.

Runtime GTK work (health measurements and `verify.py` GTK path) runs only when
`DISPLAY` or `WAYLAND_DISPLAY` is set **and** `Gtk.init_check()` succeeds.
Otherwise runtime is **SKIPPED** and does not fail the release.

## Health gate

Operational cost is a release property. `make health` writes
ignored reports under `health/latest.*` and compares against committed
`health/baseline.json`.

| Measurement | Allowed increase |
| ----------- | ---------------: |
| Startup / first-frame (when measured) | 25% |
| Peak RSS | 15% |
| Installed footprint | 15% |
| Compressed package | 15% |

```bash
./packaging/release.sh health --update-baseline
```

Standalone `health` re-runs compileall, optional ruff/pyflakes, Meson tests,
`validate-config.py`, and `verify.py` so the gate is self-contained. During
`release`, those stages already ran; health is invoked with
`--within-release` and keeps footprint, import, dependency, and process
metrics plus baseline comparison.

## Maintenance contract

Contributions must keep the project understandable, reproducible from the
documented toolchain, lightweight, deterministic, and maintainable without
historical context.

Boundaries that stay frozen:

- Capabilities remain registry-driven.
- Identity remains separate from editorial content.
- Localization remains catalog-driven and structurally synchronized.
- Providers remain lazy.
- The engineering pipeline remains a release gate.

Before publication: preserve ignored-generated-file policy; update docs when
workflows change; run `doctor`, `hygiene`, `validate`, and `health`; run full
`release` with a usable display; explain intentional baseline or footprint
changes. New functionality needs justification that it cannot fit existing
boundaries.

Stability, compatibility, security, distribution integration, and content
quality take priority over architectural change.

## First-run autostart

System autostart defaults on; user opt-out uses `Hidden=true`. See
[ARCHITECTURE.md](ARCHITECTURE.md).

## Development workflow

```bash
./packaging/release.sh doctor
make validate
make
make verify
```
