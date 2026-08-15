# Security

Public cryptographic material for Amonite Welcome.

## Contents

| File | Description |
| ---- | ----------- |
| `amonite-signing-key.asc` | Synchronized copy of the Amonite Release Signing Key (public) |

This directory is an engineering convenience for maintainers. It is **not** the
canonical source of cryptographic trust.

## Canonical verification

Fingerprint, import steps, and artifact verification are defined only in the
Amonite repository:

- https://github.com/ManuelGil/amonite/blob/main/VERIFY.md
- https://github.com/ManuelGil/amonite/blob/main/security/amonite-signing-key.asc

Expected fingerprint:

`0AFF 5507 8845 4862 6087 F84A 5E1E 335B 601F B44B`

UID: `Manuel Gil (Official Release Signing Key) <security@amonite.org>`

If this copy and the canonical key disagree, trust the Amonite repository and
replace this file.

## What must not appear here

Private keys, passphrase files, secret key exports, or generated signatures.
