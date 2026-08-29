# Changelog

All notable packaging and project releases are recorded in
[`debian/changelog`](../debian/changelog).

## 2.0.0

Welcome now looks like the system it is part of, and says more of what the
system actually is.

- The handbook covers what the system is and why its defaults are what they
  are, the edition this installation runs, how to make the system yours, how
  to keep it secure, and what to include when reporting a problem.
- The edition is read from the `VARIANT` keys of `os-release`: it names the
  edition in the Welcome chapter, and it is listed under Your System. A distribution that
  publishes a single edition shows neither.
- Installing software is an action again, through the `software-install`
  capability, offered only where a provider for it exists.
- The palette is read from the running GTK theme and derived into semantic
  roles; Welcome ships no colours of its own beyond a quiet fallback, and a
  colour that would not be readable is adjusted conservatively.
- The handbook is composed as a document: numbered chapters, a single reading
  measure, prose without containers, and actions as buttons.
- The interface is split into shell, navigation, page view, components,
  accessibility and activation; platform code lives under
  `amonite_welcome/services`.
- A distribution restyles Welcome with one file, `theme/distro.css`.
- Capability visibility, accessibility, keyboard navigation, the seven
  languages, and the launcher options are unchanged from 1.1.0.

## 1.1.0

Capability and packaging updates aligned with the software actually provided by
each edition.

- Fixed terminal update commands and terminal-specific argv handling.
- Actions are now shown only when their required capability is available.
- Removed the unsupported graphical package-manager action.
- Fixed accessible heading roles.
- Added `--help`, `--version`, and `--capabilities` to the launcher.
- Updated the provider registry and packaging metadata.

## 1.0.0

First public stable release.

## 0.1.0

First engineering-stable baseline: GTK 4 handbook, Meson build, Debian
packaging, multi-language catalogs, identity model, and release pipeline.
