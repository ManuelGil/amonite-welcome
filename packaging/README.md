# Packaging

Debian packaging lives in `../debian/` (required by `dpkg-buildpackage`).

Release and verification logic for maintainers:

| Path | Role |
| ---- | ---- |
| `release.sh` | Build, package, sign, checksum, manifest pipeline |
| `validate-config.py` | Catalog / desktop / authoring validation |
| `verify.py` | Post-install functional and security regressions |

Preferred interface: `make release` (see root `Makefile` and `docs/RELEASE.md`).
