# Contributing

Thank you for contributing to Amonite Welcome.

## Before you start

1. Read [../README.md](../README.md) for build and run instructions.
2. Read [ARCHITECTURE.md](ARCHITECTURE.md) so changes land in the right layer.
3. Read [ENGINEERING.md](ENGINEERING.md) for tooling and the capability registry.
4. For handbook languages, follow [TRANSLATING.md](TRANSLATING.md).

## Development loop

Use the workflow in [ENGINEERING.md](ENGINEERING.md)
(`doctor` → `validate` → `make` → `verify`). Keep generated trees
out of git; see `.gitignore`.

## Where to change what

| Change | Where |
| ------ | ----- |
| Application name, slogan, desktop Name/GenericName/Comment | `data/identity.<lang>.yaml` (+ `identity.base.yaml` for ids) |
| Handbook prose or actions | `data/pages.en.yaml` first; then translations |
| UI / dialog strings | `data/strings.<lang>.yaml` (all languages) |
| Capability providers | `data/providers.yaml` only |
| New live fact section | `DATA_READERS` in `amonite_welcome/system_info.py` |
| Window layout | `data/ui/window.ui` |
| Spacing / typography | `data/style.css` |
| Icons | `data/icons/hicolor/` (Freedesktop application icon) |
| Menu desktop | `data/amonite-welcome.desktop` (must match identity catalogs) |
| Autostart template | `data/autostart/amonite-welcome.desktop` (installed to `/etc/xdg/autostart`; default on) |
| App id / binary name | top-level `meson.build` |

Do not put distribution name, version, or URLs in identity catalogs. Those come
from `/etc/os-release`.

## Pull requests

- Keep changes focused; one concern per PR when practical.
- Do not add features without a clear maintenance benefit (see Architecture →
  Stability).
- Run `make validate` and `make verify` before
  submitting.
- For translations, ship a complete `pages.<lang>.yaml` that matches the
  English structure.

## License

Contributions are accepted under GPL-3.0-or-later. See [../LICENSE](../LICENSE).
