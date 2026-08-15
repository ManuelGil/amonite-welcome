# Release

How to cut a release of Amonite Welcome.

Engineering details (commands, cleaning modes, capability registry) are in
[ENGINEERING.md](ENGINEERING.md).

## Version sources

Keep these in sync:

| Location | Field |
| -------- | ----- |
| `meson.build` | `project(... version: '…')` |
| `debian/changelog` | package version (e.g. `amonite-welcome (1.0.0)`) |

There is no separate application version in identity catalogs. Distribution
release labels come from `/etc/os-release` on the installed system.

## One-command release

After bumping the version (below), produce a verified package with:

```bash
make release
```

The default command is `release`, so `./packaging/release.sh` is equivalent.

Artifacts are written only under `dist/`:

- `amonite-welcome_<version>_all.deb`
- `SHA256SUMS`
- `SHA256SUMS.asc` and `<package>.asc` when signing is enabled
- `release-manifest.json`
- `build.log`

Signing is enabled by default and uses **only** the Amonite Release Signing
Key (fingerprint `0AFF5507884548626087F84A5E1E335B601FB44B`). Configure with
`AMONITE_SIGNING_KEY=<fingerprint>` (must match that fingerprint). Selection by
name or email is not allowed, and there is no fallback to another key.

To disable signing explicitly:

```bash
AMONITE_RELEASE_SIGN=0 make release
```

Silent skip is not allowed.

Signing requires the secret key to be unlocked (pinentry or
`AMONITE_SIGNING_PASSPHRASE` for non-interactive loopback). Passphrases are
never logged.

How to import the public key and verify release artifacts is documented in the
canonical Amonite guide — do not duplicate that procedure here:

- https://github.com/ManuelGil/amonite/blob/main/VERIFY.md
- https://github.com/ManuelGil/amonite/blob/main/security/amonite-signing-key.asc

GTK checks in `packaging/verify.py` need a usable display. Headless runs skip
runtime GTK; static gates still apply. See [ENGINEERING.md](ENGINEERING.md).

## Release checklist

Complete every item before tagging and handing the `.deb` to ISO integration:

- [ ] Handbook / string edits finished; `make validate` passes
- [ ] Version bumped in `meson.build` and `debian/changelog`
- [ ] `make release` (doctor → hygiene → validate → … → health)
- [ ] Review `health/latest.md`
- [ ] Install the generated `.deb` on a clean test system
- [ ] Confirm Welcome autostarts on login (system `/etc/xdg/autostart` entry)
- [ ] Confirm the “Show this window on startup” checkbox is **on** by default
- [ ] Disable autostart, log out/in (or inspect `~/.config/autostart`), confirm it stays off
- [ ] Re-enable autostart and confirm it returns
- [ ] Review handbook pages in English and at least one other language
- [ ] Exercise each capability action (and missing-provider dialogs if tools absent)
- [ ] Window title / footer match `/etc/os-release`
- [ ] `sudo apt purge amonite-welcome` - no broken desktop leftovers
- [ ] Reinstall the same `.deb` - identical behaviour
- [ ] Tag `vX.Y.Z` to match the package version

## What not to release from

- Uncommitted generated files under `builddir/` or `obj-*/`
- A tree contaminated by packaging leftovers (`obj-*`, `debian/*.substvars`;
  see `.gitignore`). Prefer `make release`, which starts with
  `distclean`.
