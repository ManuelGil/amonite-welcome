# Security

Amonite Welcome is a local first-run handbook. It reads system files, displays
prose, and launches existing desktop tools or URLs. It does not run a network
service and does not process untrusted remote input beyond opening URLs the
user activates.

## Supported versions

Security fixes are applied to the latest released version on the default
branch. Older releases are not maintained separately unless noted in a release
announcement.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report privately to the maintainers using the contact in `debian/copyright`
(Upstream-Contact), or via the project’s private security channel if one is
published on the project website.

Include:

- Amonite Welcome version (`meson.build` / package version)
- Host distribution and desktop environment
- Steps to reproduce
- Impact (for example unexpected command execution, path overwrite)

You should receive an acknowledgement when practical. Fixes are coordinated
before public disclosure when that reduces risk to users.

## Verifying release artifacts

Official `.deb` packages and checksums are signed with the Amonite Release
Signing Key. This repository does not redefine that trust model.

Follow the canonical Amonite verification guide:

- https://github.com/ManuelGil/amonite/blob/main/VERIFY.md

Canonical public key:

- https://github.com/ManuelGil/amonite/blob/main/security/amonite-signing-key.asc

Fingerprint (spaced form): `0AFF 5507 8845 4862 6087 F84A 5E1E 335B 601F B44B`

A synchronized public copy may also appear under `security/amonite-signing-key.asc`
in this repository for maintainer convenience. It is not an independent trust
source.

## Non-security bugs

Ordinary bugs and packaging issues belong in the public issue tracker.
