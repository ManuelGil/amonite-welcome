#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Maintainer tool for Amonite Welcome.
#
# Usage:
#   ./packaging/release.sh [command]
#
# Default command: release
#
# Exit codes:
#   0  PASS
#   1  Engineering failure
#   2  Environment limitation (ownership, missing optional display, etc.)
#
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer the system Meson toolchain for packaging reproducibility.
export PATH="/usr/bin:/bin${PATH:+:$PATH}"
export PYTHONNOUSERSITE=1

BUILDDIR="$ROOT/builddir"
PACKAGE_ROOT="$ROOT/package-root"
DIST="$ROOT/dist"
PARENT="$(cd "$ROOT/.." && pwd)"

PACKAGE_PATH=""
PACKAGE_NAME=""
PACKAGE_SIZE=""
PACKAGE_VERSION=""
PACKAGE_ARCH=""
PACKAGE_SHA256=""

# Capture skip notes for the release summary (e.g. headless verify).
RELEASE_NOTES=()

# Stage results for release-manifest.json (PASS / FAIL / SKIPPED).
STAGE_DOCTOR=""
STAGE_VALIDATE=""
STAGE_HEALTH=""
STAGE_VERIFY=""
STAGE_RELEASE=""
SIGNING_STATUS=""
SIGNING_FINGERPRINT=""
SIGNING_KEY=""
SIGNING_UID=""
SIGNING_VERIFICATION=""
BUILD_TIMESTAMP=""

# Official Amonite Release Signing Key (canonical; do not change).
# Public verification: https://github.com/ManuelGil/amonite/blob/main/VERIFY.md
AMONITE_CANONICAL_SIGNING_FINGERPRINT="0AFF5507884548626087F84A5E1E335B601FB44B"

# Signing: enabled by default. Set AMONITE_RELEASE_SIGN=0 to skip explicitly.
# Silent skip is never allowed. Key selection is by fingerprint only.
AMONITE_RELEASE_SIGN="${AMONITE_RELEASE_SIGN:-1}"
# Prefer AMONITE_SIGNING_KEY; accept legacy AMONITE_RELEASE_GPG_KEY as alias.
AMONITE_SIGNING_KEY="${AMONITE_SIGNING_KEY:-${AMONITE_RELEASE_GPG_KEY:-$AMONITE_CANONICAL_SIGNING_FINGERPRINT}}"

log() { printf '%s\n' "$*"; }
section() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
die_env() { printf 'ENVIRONMENT: %s\n' "$*" >&2; exit 2; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

require_cmd() {
  if ! have_cmd "$1"; then
    die "required tool not found: $1
Install build dependencies; see README.md and docs/ENGINEERING.md."
  fi
}

tool_version() {
  local name="$1"
  shift
  if have_cmd "$name"; then
    # shellcheck disable=SC2068
    log "  $name: $($@ 2>/dev/null | head -n1 || command -v "$name")"
  else
    log "  $name: MISSING"
  fi
}

has_display() {
  [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]
}

display_usable() {
  # Env vars alone are not enough (CI often sets empty DISPLAY stubs).
  has_display || return 1
  python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
raise SystemExit(0 if Gtk.init_check() else 1)
PY
}

find_package() {
  local matches=()
  # Prefer the in-repo release directory.
  shopt -s nullglob
  matches=( "$DIST"/amonite-welcome_*.deb )
  if [ "${#matches[@]}" -eq 0 ]; then
    matches=( "$PARENT"/amonite-welcome_*.deb )
  fi
  if [ "${#matches[@]}" -eq 0 ]; then
    matches=( "$ROOT"/amonite-welcome_*.deb )
  fi
  shopt -u nullglob
  if [ "${#matches[@]}" -eq 1 ]; then
    PACKAGE_PATH="${matches[0]}"
    PACKAGE_NAME="$(basename "$PACKAGE_PATH")"
    PACKAGE_SIZE="$(wc -c <"$PACKAGE_PATH" | tr -d ' ')"
    PACKAGE_VERSION="$(dpkg-deb -f "$PACKAGE_PATH" Version 2>/dev/null || true)"
    PACKAGE_ARCH="$(dpkg-deb -f "$PACKAGE_PATH" Architecture 2>/dev/null || true)"
    if have_cmd sha256sum; then
      PACKAGE_SHA256="$(sha256sum "$PACKAGE_PATH" | awk '{print $1}')"
    else
      PACKAGE_SHA256=""
    fi
    return 0
  fi
  if [ "${#matches[@]}" -gt 1 ]; then
    die "multiple amonite-welcome_*.deb packages found; remove stale artifacts"
  fi
  return 1
}

ensure_dist() {
  mkdir -p "$DIST"
}

clear_dist_artifacts() {
  ensure_dist
  find "$DIST" -mindepth 1 -maxdepth 1 ! -name 'README.md' -print0 \
    | xargs -0r rm -rf
}

collect_debian_artifacts() {
  # dpkg-buildpackage writes beside the source tree; gather into dist/.
  ensure_dist
  local path
  shopt -s nullglob
  for path in \
    "$PARENT"/amonite-welcome_*.deb \
    "$PARENT"/amonite-welcome_*.buildinfo \
    "$PARENT"/amonite-welcome_*.changes \
    "$PARENT"/amonite-welcome_*.build \
    "$ROOT"/amonite-welcome_*.deb \
    "$ROOT"/amonite-welcome_*.buildinfo \
    "$ROOT"/amonite-welcome_*.changes \
    "$ROOT"/amonite-welcome_*.build
  do
    [ -e "$path" ] || continue
    case "$path" in
      *.deb)
        mv -f "$path" "$DIST/"
        ;;
      *)
        # Temporary Debian metadata: remove after packaging; not final artifacts.
        rm -f "$path"
        ;;
    esac
  done
  shopt -u nullglob
}

signing_requested() {
  case "${AMONITE_RELEASE_SIGN,,}" in
    0|no|false|off|skip) return 1 ;;
    *) return 0 ;;
  esac
}

normalize_fingerprint() {
  # Strip spaces/colons; uppercase. Never select by name or email.
  printf '%s' "$1" | tr -d '[:space:]:' | tr '[:lower:]' '[:upper:]'
}

verify_bundled_public_key() {
  # security/amonite-signing-key.asc is a synchronized convenience copy only.
  local pubkey="$ROOT/security/amonite-signing-key.asc"
  local expected bundled
  expected="$(normalize_fingerprint "$AMONITE_CANONICAL_SIGNING_FINGERPRINT")"
  if [ ! -f "$pubkey" ]; then
    die "missing synchronized public key: security/amonite-signing-key.asc

Restore the public Amonite Release Signing Key copy (not a private key).
Canonical source:
  https://github.com/ManuelGil/amonite/blob/main/security/amonite-signing-key.asc
  https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
  fi
  if grep -q 'BEGIN PGP PRIVATE KEY BLOCK' "$pubkey"; then
    die "security/amonite-signing-key.asc contains private key material

Remove it immediately. Only the public key may be stored in this repository."
  fi
  bundled="$(
    gpg --batch --show-keys --with-colons "$pubkey" 2>/dev/null \
      | awk -F: '/^fpr:/{print toupper($10); exit}'
  )"
  bundled="$(normalize_fingerprint "$bundled")"
  if [ -z "$bundled" ]; then
    die "could not read fingerprint from security/amonite-signing-key.asc"
  fi
  if [ "$bundled" != "$expected" ]; then
    die "security/amonite-signing-key.asc fingerprint does not match the Amonite Release Signing Key.

  bundled:  $bundled
  required: $expected

Replace the file from the canonical Amonite repository.
This repository must not introduce a parallel trust source.
  https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
  fi
}

require_signing_key() {
  verify_bundled_public_key
  if ! have_cmd gpg; then
    die_env "cryptographic signing requires gpg, but gpg was not found on PATH.

Install GnuPG (apt install gnupg), import the Amonite Release Signing Key, then retry.

Canonical verification guide:
  https://github.com/ManuelGil/amonite/blob/main/VERIFY.md

To disable signing explicitly (not silent):
  AMONITE_RELEASE_SIGN=0 ./packaging/release.sh release"
  fi

  local configured expected actual
  configured="$(normalize_fingerprint "${AMONITE_SIGNING_KEY}")"
  expected="$(normalize_fingerprint "$AMONITE_CANONICAL_SIGNING_FINGERPRINT")"

  if [ -z "$configured" ]; then
    die_env "AMONITE_SIGNING_KEY is empty.

Set it to the Amonite Release Signing Key fingerprint:
  AMONITE_SIGNING_KEY=$AMONITE_CANONICAL_SIGNING_FINGERPRINT

Canonical verification guide:
  https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
  fi

  if [ "$configured" != "$expected" ]; then
    die_env "refusing to sign with a non-canonical key fingerprint.

Amonite Welcome uses only the Amonite Release Signing Key.
No parallel trust chain is allowed.

  configured: $configured
  required:   $expected

Unset AMONITE_SIGNING_KEY (or set it to the required fingerprint), then retry.

Canonical verification guide:
  https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
  fi

  SIGNING_KEY="$expected"
  SIGNING_FINGERPRINT="$expected"

  local keys
  keys="$(gpg --batch --list-secret-keys --with-colons "$SIGNING_KEY" 2>/dev/null || true)"
  if ! printf '%s\n' "$keys" | grep -q '^sec:'; then
    die_env "Amonite Release Signing Key secret material is not available in this GnuPG keyring.

Missing secret key for fingerprint:
  $SIGNING_FINGERPRINT

Import the official private signing key into GnuPG, then retry.
Public key and verification procedure:
  https://github.com/ManuelGil/amonite/blob/main/VERIFY.md
  https://github.com/ManuelGil/amonite/blob/main/security/amonite-signing-key.asc

Never fall back to another personal key.
To disable signing explicitly (not silent):
  AMONITE_RELEASE_SIGN=0 ./packaging/release.sh release"
  fi

  actual="$(
    printf '%s\n' "$keys" | awk -F: '
      /^fpr:/ {
        gsub(/ /, "", $10)
        print toupper($10)
        exit
      }'
  )"
  if [ -z "$actual" ]; then
    die_env "could not read fingerprint for configured signing key $SIGNING_KEY"
  fi
  if [ "$actual" != "$expected" ]; then
    die_env "GnuPG returned a fingerprint that does not match the Amonite Release Signing Key.

  expected: $expected
  resolved: $actual

Refusing to sign. No fallback to another key is permitted."
  fi

  SIGNING_UID="$(
    printf '%s\n' "$keys" | awk -F: '
      /^uid:/ {
        print $10
        exit
      }'
  )"
  if [ -z "$SIGNING_UID" ]; then
    SIGNING_UID="(uid unavailable)"
  fi

  # Log fingerprint and uid only — never key material or passphrases.
  log "  signing identity: Amonite Release Signing Key"
  log "  fingerprint:      $SIGNING_FINGERPRINT"
  log "  uid:              $SIGNING_UID"
  log "  public copy:      security/amonite-signing-key.asc (synchronized; not canonical)"
}

gpg_sign_detached() {
  local input="$1"
  local output="$2"
  local -a gpg_args=(
    --batch --yes
    --local-user "$SIGNING_FINGERPRINT"
    --detach-sign --armor
    --output "$output"
  )
  # Optional non-interactive unlock. Never log or echo the passphrase.
  if [ -n "${AMONITE_SIGNING_PASSPHRASE+x}" ]; then
    gpg_args+=(--pinentry-mode loopback --passphrase-fd 3)
    if ! gpg "${gpg_args[@]}" "$input" 3<<<"${AMONITE_SIGNING_PASSPHRASE}"; then
      die "gpg failed to create detached signature for $(basename "$input")

The Amonite Release Signing Key could not sign (passphrase or agent failure).
Fingerprint: $SIGNING_FINGERPRINT
Unlock the key via pinentry, or set AMONITE_SIGNING_PASSPHRASE for loopback use.
Verification guide: https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
    fi
    return 0
  fi

  # Prefer a real terminal for curses pinentry when available.
  if [ -z "${GPG_TTY:-}" ] && [ -t 0 ]; then
    local detected_tty
    detected_tty="$(tty 2>/dev/null || true)"
    if [ -n "$detected_tty" ] && [ -c "$detected_tty" ]; then
      GPG_TTY="$detected_tty"
      export GPG_TTY
    fi
  fi
  # Refuse only when neither a usable TTY nor a graphical pinentry session exists.
  # DISPLAY/WAYLAND allow pinentry-gnome3 (and peers) without a controlling TTY.
  if { [ -z "${GPG_TTY:-}" ] || [ ! -c "${GPG_TTY}" ]; } \
      && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    gpg_args+=(--pinentry-mode error)
  fi

  if ! gpg "${gpg_args[@]}" "$input"; then
    die "gpg failed to create detached signature for $(basename "$input")

The Amonite Release Signing Key could not sign.
Common causes:
  - pinentry unavailable or timed out (unlock the key interactively, then retry)
  - gpg-agent not running
  - secret key not imported for fingerprint $SIGNING_FINGERPRINT
  - headless session without AMONITE_SIGNING_PASSPHRASE

Verification guide: https://github.com/ManuelGil/amonite/blob/main/VERIFY.md
Optional non-interactive unlock:
  AMONITE_SIGNING_PASSPHRASE=… ./packaging/release.sh release"
  fi
}

gpg_verify_detached() {
  local signature="$1"
  local data="$2"
  local status_file valid_fpr
  status_file="$(mktemp)"
  if ! gpg --batch --status-fd 3 --verify "$signature" "$data" \
      3>"$status_file" >/dev/null 2>&1; then
    rm -f "$status_file"
    SIGNING_VERIFICATION="FAIL"
    die "signature verification failed for $(basename "$data")

Expected signer fingerprint:
  $SIGNING_FINGERPRINT

Re-import the public Amonite Release Signing Key and retry.
Verification guide: https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
  fi
  valid_fpr="$(
    awk '
      $1 == "[GNUPG:]" && $2 == "VALIDSIG" {
        print toupper($3)
        exit
      }
    ' "$status_file"
  )"
  rm -f "$status_file"
  if [ -z "$valid_fpr" ]; then
    SIGNING_VERIFICATION="FAIL"
    die "signature verification produced no VALIDSIG status for $(basename "$data")"
  fi
  if [ "$valid_fpr" != "$SIGNING_FINGERPRINT" ]; then
    SIGNING_VERIFICATION="FAIL"
    die "signature for $(basename "$data") was not made by the Amonite Release Signing Key.

  expected: $SIGNING_FINGERPRINT
  got:      $valid_fpr

No parallel trust chain is allowed."
  fi
  SIGNING_VERIFICATION="PASS"
}

# --- Ownership / environment ------------------------------------------------

ownership_candidates() {
  # Paths the pipeline may remove or rewrite. Unmatched globs are ignored.
  local path
  for path in \
    "$BUILDDIR" \
    "$PACKAGE_ROOT" \
    "$ROOT"/obj-* \
    "$ROOT/debian/.debhelper" \
    "$ROOT/debian/amonite-welcome" \
    "$ROOT/debian/tmp" \
    "$ROOT/debian/files" \
    "$ROOT/debian"/*.debhelper \
    "$ROOT/debian"/*.debhelper.log \
    "$ROOT/debian"/*.substvars \
    "$ROOT/debian/debhelper-build-stamp" \
    "$PARENT"/amonite-welcome_*.deb \
    "$PARENT"/amonite-welcome_*.buildinfo \
    "$PARENT"/amonite-welcome_*.changes \
    "$PARENT"/amonite-welcome_*.build \
    "$ROOT"/amonite-welcome_*.deb \
    "$ROOT"/amonite-welcome_*.buildinfo \
    "$ROOT"/amonite-welcome_*.changes \
    "$ROOT"/amonite-welcome_*.build \
    "$DIST" \
    "$DIST"/*
  do
    case "$path" in
      *\*) continue ;;
      "$DIST"/README.md) continue ;;
    esac
    printf '%s\n' "$path"
  done
}

check_removable_ownership() {
  local path owner uid me_uid me_user me_group
  local bad=()
  me_uid="$(id -u)"
  me_user="$(id -un)"
  me_group="$(id -gn)"

  while IFS= read -r path; do
    [ -e "$path" ] || continue
    # Skip globs that did not expand.
    case "$path" in
      *\*) continue ;;
    esac
    owner="$(stat -c '%u' "$path" 2>/dev/null || true)"
    [ -n "$owner" ] || continue
    if [ "$owner" != "$me_uid" ]; then
      bad+=("$(stat -c '%U:%G %n' "$path" 2>/dev/null || printf '%s\n' "$path")")
    fi
  done < <(ownership_candidates)

  if [ "${#bad[@]}" -eq 0 ]; then
    return 0
  fi

  printf '\nENVIRONMENT LIMITATION: files not owned by %s block a reproducible clean.\n\n' "$me_user" >&2
  printf 'Found files owned by another user:\n' >&2
  printf '  %s\n' "${bad[@]}" >&2
  printf '\nThese files prevent reproducible releases.\n\n' >&2
  printf 'Suggested fix (choose one):\n' >&2
  printf '  sudo chown -R %s:%s %s\n' "$me_user" "$me_group" "$PARENT" >&2
  printf '  sudo rm -f %s/amonite-welcome_*.deb %s/amonite-welcome_*.buildinfo %s/amonite-welcome_*.changes\n' \
    "$PARENT" "$PARENT" "$PARENT" >&2
  printf '  sudo rm -rf %s/dist/* %s/builddir %s/package-root %s/obj-*\n' \
    "$ROOT" "$ROOT" "$ROOT" "$ROOT" >&2
  printf '\nRefusing destructive operations until ownership is corrected.\n' >&2
  return 1
}

ensure_build() {
  require_cmd meson
  if [ ! -f "$BUILDDIR/build.ninja" ]; then
    log "  preparing builddir (configure + build)"
    cmd_configure
    cmd_build
  else
    # Always recompile so source edits cannot hide behind a stale builddir.
    log "  refreshing builddir (compile)"
    cmd_build
  fi
}

ensure_install() {
  ensure_build
  # Always reinstall so verify/health never consume a stale package-root.
  log "  refreshing package-root (install)"
  cmd_install
}

# --- Cleaning ---------------------------------------------------------------

cmd_clean() {
  section "clean - remove build trees"
  if ! check_removable_ownership; then
    die_env "cannot clean: foreign-owned artefacts present"
  fi
  rm -rf "$BUILDDIR" "$PACKAGE_ROOT"
  rm -rf "$ROOT"/obj-*/
  rm -rf \
    "$ROOT/debian/.debhelper" \
    "$ROOT/debian/amonite-welcome" \
    "$ROOT/debian/tmp" \
    "$ROOT/debian/files"
  rm -f \
    "$ROOT/debian"/*.debhelper \
    "$ROOT/debian"/*.debhelper.log \
    "$ROOT/debian"/*.substvars \
    "$ROOT/debian/debhelper-build-stamp"
  log "  removed builddir, package-root, obj-*, debian build leftovers"
}

cmd_distclean() {
  section "distclean - clean + remove packages and metadata"
  if ! check_removable_ownership; then
    die_env "cannot distclean: foreign-owned artefacts present"
  fi
  cmd_clean
  rm -f \
    "$PARENT"/amonite-welcome_*.deb \
    "$PARENT"/amonite-welcome_*.buildinfo \
    "$PARENT"/amonite-welcome_*.changes \
    "$PARENT"/amonite-welcome_*.build \
    "$ROOT"/amonite-welcome_*.deb \
    "$ROOT"/amonite-welcome_*.buildinfo \
    "$ROOT"/amonite-welcome_*.changes \
    "$ROOT"/amonite-welcome_*.build
  clear_dist_artifacts
  rm -rf "$BUILDDIR"/meson-logs "$ROOT"/obj-*/meson-logs 2>/dev/null || true
  log "  removed generated packages, dist/ artifacts, and build metadata"
}

# --- Diagnostics ------------------------------------------------------------

cmd_doctor() {
  section "doctor - self diagnostics"
  local missing=0

  check() {
    local label="$1"
    shift
    if "$@"; then
      log "  OK  $label"
    else
      log "  MISSING  $label"
      missing=1
    fi
  }

  check "python3" have_cmd python3
  if have_cmd python3; then
    log "       $(python3 --version 2>&1)"
  fi
  check "meson" have_cmd meson
  check "ninja" have_cmd ninja
  check "pkg-config" have_cmd pkg-config
  check "dpkg-buildpackage" have_cmd dpkg-buildpackage
  check "dpkg-deb" have_cmd dpkg-deb
  check "desktop-file-validate" have_cmd desktop-file-validate

  if have_cmd pkg-config; then
    if pkg-config --exists gtk4; then
      log "  OK  gtk4 ($(pkg-config --modversion gtk4))"
    else
      log "  MISSING  gtk4 (pkg-config)"
      missing=1
    fi
    if pkg-config --exists pygobject-3.0; then
      log "  OK  pygobject-3.0 ($(pkg-config --modversion pygobject-3.0))"
    else
      log "  MISSING  pygobject-3.0"
      missing=1
    fi
  fi

  if python3 -c 'import yaml' 2>/dev/null; then
    log "  OK  python3-yaml"
  else
    log "  MISSING  python3-yaml"
    missing=1
  fi

  if display_usable; then
    log "  OK  graphical session (DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-})"
  elif has_display; then
    log "  NOTE display variables set but GTK cannot initialize — runtime measurements will be SKIPPED"
  else
    log "  NOTE graphical session absent — runtime GTK measurements will be SKIPPED"
  fi

  if signing_requested; then
    if ! have_cmd gpg; then
      log "  MISSING  gpg (required for Amonite Release Signing Key)"
      missing=1
    else
      local configured expected bundled_fpr
      configured="$(normalize_fingerprint "${AMONITE_SIGNING_KEY}")"
      expected="$(normalize_fingerprint "$AMONITE_CANONICAL_SIGNING_FINGERPRINT")"
      if [ ! -f "$ROOT/security/amonite-signing-key.asc" ]; then
        log "  MISSING  security/amonite-signing-key.asc (synchronized public copy)"
        missing=1
      elif grep -q 'BEGIN PGP PRIVATE KEY BLOCK' "$ROOT/security/amonite-signing-key.asc"; then
        log "  FAIL  security/amonite-signing-key.asc contains private key material"
        missing=1
      else
        bundled_fpr="$(
          gpg --batch --show-keys --with-colons "$ROOT/security/amonite-signing-key.asc" 2>/dev/null \
            | awk -F: '/^fpr:/{print toupper($10); exit}'
        )"
        bundled_fpr="$(normalize_fingerprint "$bundled_fpr")"
        if [ "$bundled_fpr" = "$expected" ]; then
          log "  OK  security/amonite-signing-key.asc matches canonical fingerprint"
        else
          log "  FAIL  security/amonite-signing-key.asc fingerprint mismatch"
          log "        bundled=$bundled_fpr required=$expected"
          missing=1
        fi
      fi
      if [ "$configured" != "$expected" ]; then
        log "  FAIL  AMONITE_SIGNING_KEY is not the Amonite Release Signing Key"
        log "        configured=$configured"
        log "        required=$expected"
        missing=1
      elif gpg --batch --list-secret-keys --with-colons "$expected" 2>/dev/null | grep -q '^sec:'; then
        log "  OK  Amonite Release Signing Key (secret) $expected"
      else
        log "  MISSING  Amonite Release Signing Key secret for $expected"
        log "        Import the official key; see https://github.com/ManuelGil/amonite/blob/main/VERIFY.md"
        missing=1
      fi
    fi
  else
    log "  NOTE signing disabled (AMONITE_RELEASE_SIGN=$AMONITE_RELEASE_SIGN)"
  fi

  log "  PATH=$PATH"

  if [ "$missing" -ne 0 ]; then
    die "doctor found missing requirements"
  fi
  log "  all required tools present"
}

cmd_status() {
  section "status - repository state (read-only)"
  log "  root: $ROOT"
  if [ -d "$BUILDDIR" ]; then
    log "  builddir: present"
  else
    log "  builddir: absent"
  fi
  if [ -d "$PACKAGE_ROOT" ]; then
    log "  package-root: present"
  else
    log "  package-root: absent"
  fi
  if find_package; then
    log "  package: $PACKAGE_NAME ($PACKAGE_SIZE bytes, $PACKAGE_VERSION $PACKAGE_ARCH)"
    log "  path: $PACKAGE_PATH"
  else
    log "  package: none"
  fi
  if display_usable; then
    log "  display: usable"
  elif has_display; then
    log "  display: present but unusable (runtime health SKIPPED)"
  else
    log "  display: absent (runtime health SKIPPED)"
  fi
  tool_version meson meson --version
  tool_version ninja ninja --version
  tool_version python3 python3 --version
  tool_version dpkg dpkg --version
  if [ -d "$ROOT/.git" ]; then
    log "  git status --porcelain:"
    git -C "$ROOT" status --porcelain | sed 's/^/    /' || true
  else
    log "  git: not a repository"
  fi
}

# --- Config validation ------------------------------------------------------

cmd_validate() {
  section "validate - configuration"
  python3 "$ROOT/packaging/validate-config.py"
}

# --- Build stages -----------------------------------------------------------

cmd_configure() {
  section "configure - meson setup builddir"
  require_cmd meson
  require_cmd pkg-config
  if [ -f "$BUILDDIR/build.ninja" ]; then
    meson setup --reconfigure "$BUILDDIR" --prefix=/usr
  else
    meson setup "$BUILDDIR" --prefix=/usr
  fi
}

cmd_build() {
  section "build - meson compile"
  require_cmd meson
  if [ ! -f "$BUILDDIR/build.ninja" ]; then
    cmd_configure
  fi
  meson compile -C "$BUILDDIR"
}

cmd_test() {
  section "test - meson test"
  require_cmd meson
  ensure_build
  meson test -C "$BUILDDIR" --print-errorlogs
}

cmd_install() {
  section "install - DESTDIR=package-root meson install"
  require_cmd meson
  ensure_build
  DESTDIR="$PACKAGE_ROOT" meson install -C "$BUILDDIR"

  local marker="$PACKAGE_ROOT/usr/share/amonite-welcome/amonite-welcome.gresource"
  local providers="$PACKAGE_ROOT/usr/share/amonite-welcome/providers.yaml"
  local binary="$PACKAGE_ROOT/usr/bin/amonite-welcome"
  for path in "$marker" "$providers" "$binary"; do
    [ -e "$path" ] || die "staged install missing: $path"
  done
  log "  install tree OK (includes providers.yaml)"
}

cmd_verify() {
  section "verify - packaging/verify.py"
  require_cmd python3
  ensure_install

  if ! display_usable; then
    log "  SKIPPED runtime GTK verification"
    if has_display; then
      log "  Reason: display variables set but GTK cannot initialize a display"
    else
      log "  Reason: no graphical session (DISPLAY / WAYLAND_DISPLAY unset)"
    fi
    log "  Static packaging checks remain covered by validate, inspect, and health."
    RELEASE_NOTES+=("verify: SKIPPED (no usable graphical session)")
    return 0
  fi
  python3 "$ROOT/packaging/verify.py"
}

cmd_package() {
  section "package - dpkg-buildpackage → dist/"
  require_cmd dpkg-buildpackage
  require_cmd dpkg-deb
  if ! check_removable_ownership; then
    die_env "cannot package while foreign-owned artefacts block output paths"
  fi
  ensure_dist
  # Remove prior release packages so collect cannot see duplicates.
  rm -f "$DIST"/amonite-welcome_*.deb
  dpkg-buildpackage -us -uc -b
  collect_debian_artifacts
  find_package || die "dpkg-buildpackage did not produce amonite-welcome_*.deb in $DIST"
  # Ensure package lives under dist/ even if find_package matched a stray path.
  if [ "$(dirname "$PACKAGE_PATH")" != "$DIST" ]; then
    mv -f "$PACKAGE_PATH" "$DIST/"
    find_package || die "failed to relocate package into $DIST"
  fi
  log "  filename:     $PACKAGE_NAME"
  log "  path:         $PACKAGE_PATH"
  log "  size:         $PACKAGE_SIZE bytes"
  log "  version:      $PACKAGE_VERSION"
  log "  architecture: $PACKAGE_ARCH"
  log "  sha256:       $PACKAGE_SHA256"
}

cmd_inspect() {
  section "inspect - dpkg-deb contents"
  require_cmd dpkg-deb
  require_cmd desktop-file-validate
  if ! find_package; then
    log "  no package present; packaging first"
    cmd_package
  fi

  local listing
  listing="$(dpkg-deb -c "$PACKAGE_PATH")"

  require_in_listing() {
    local needle="$1"
    local label="$2"
    if ! printf '%s\n' "$listing" | grep -q "$needle"; then
      die "package missing $label ($needle)"
    fi
    log "  OK $label"
  }

  require_in_listing './usr/share/applications/amonite-welcome.desktop' 'desktop file'
  require_in_listing './usr/share/icons/hicolor/48x48/apps/amonite-welcome.png' '48x48 icon'
  require_in_listing './usr/share/icons/hicolor/256x256/apps/amonite-welcome.png' '256x256 icon'
  if printf '%s\n' "$listing" | grep -q 'amonite-mark\.svg'; then
    die 'package must not contain obsolete amonite-mark.svg'
  fi
  if printf '%s\n' "$listing" | grep -q 'scalable/apps/amonite-welcome\.svg'; then
    die 'package must not contain scalable SVG application icon'
  fi
  log '  OK no obsolete SVG icons'
  require_in_listing './usr/share/amonite-welcome/pages.en.yaml' 'handbook (en)'
  require_in_listing './usr/share/amonite-welcome/pages.es.yaml' 'handbook translation (es)'
  require_in_listing './usr/share/amonite-welcome/identity.base.yaml' 'identity base'
  require_in_listing './usr/share/amonite-welcome/identity.en.yaml' 'identity (en)'
  require_in_listing './usr/share/amonite-welcome/identity.es.yaml' 'identity translation (es)'
  require_in_listing './usr/share/amonite-welcome/providers.yaml' 'capability registry'
  require_in_listing './usr/share/amonite-welcome/amonite-welcome.gresource' 'gresource'
  require_in_listing './usr/share/doc/amonite-welcome/LICENSE' 'LICENSE'
  require_in_listing './usr/share/doc/amonite-welcome/README.md' 'documentation (README)'
  require_in_listing './usr/bin/amonite-welcome' 'binary'
  require_in_listing './etc/xdg/autostart/amonite-welcome.desktop' 'system autostart'

  local tmp
  tmp="$(mktemp -d)"
  dpkg-deb -x "$PACKAGE_PATH" "$tmp"
  desktop-file-validate "$tmp/usr/share/applications/amonite-welcome.desktop"
  rm -rf "$tmp"
  log "  OK desktop-file-validate"
  log "  package: $PACKAGE_NAME ($PACKAGE_SIZE bytes)"
}

cmd_purity() {
  section "hygiene - generated artefacts and repository state"
  if [ ! -d "$ROOT/.git" ]; then
    log "  skip: not a git repository"
    return
  fi
  local tracked_noise
  tracked_noise="$(
    git -C "$ROOT" ls-files -- \
      'builddir/**' 'package-root/**' 'obj-*/**' 'dist/**' \
      'debian/amonite-welcome/**' 'debian/.debhelper/**' \
      '*.deb' '*.buildinfo' '*.changes' 2>/dev/null || true
  )"
  if [ -n "$tracked_noise" ]; then
    # Allow the optional tracked pointer file.
    tracked_noise="$(printf '%s\n' "$tracked_noise" | grep -v '^dist/README.md$' || true)"
  fi
  if [ -n "$tracked_noise" ]; then
    die "generated artefacts are tracked by git:
$tracked_noise"
  fi
  log "  OK no generated artefacts tracked"
  if ! git -C "$ROOT" diff --check; then
    die "whitespace errors found by git diff --check"
  fi
  for path in \
    "$ROOT/builddir" "$ROOT/package-root" "$ROOT"/obj-* \
    "$ROOT/debian/amonite-welcome" "$ROOT/debian/.debhelper"; do
    if [ -e "$path" ] && ! git -C "$ROOT" check-ignore -q "$path"; then
      die "generated path is not ignored: $path"
    fi
  done
  if [ -d "$DIST" ]; then
    local sample
    sample="$(find "$DIST" -maxdepth 1 -type f ! -name 'README.md' | head -n1 || true)"
    if [ -n "$sample" ] && ! git -C "$ROOT" check-ignore -q "$sample"; then
      die "generated release artifact is not ignored: $sample"
    fi
  fi
  for tool in \
    "$ROOT/packaging/release.sh" \
    "$ROOT/packaging/verify.py" \
    "$ROOT/packaging/validate-config.py" \
    "$ROOT/health/check.py"; do
    [ -x "$tool" ] || die "maintainer tool is not executable: ${tool#$ROOT/}"
  done
  log "  OK generated paths are ignored and maintainer tools are executable"

  if check_removable_ownership; then
    log "  OK no foreign-owned generated artefacts"
  else
    die_env "hygiene: foreign-owned artefacts present (see above)"
  fi

  git -C "$ROOT" status --porcelain | sed 's/^/    /' || true
}

cmd_hygiene() {
  cmd_purity
}

cmd_health() {
  section "health - engineering health gate"
  require_cmd python3
  # Static health needs install tree metrics when possible; prepare quietly.
  ensure_install
  # Forward optional flags (e.g. --update-baseline, --within-release).
  python3 "$ROOT/health/check.py" "$@"
}

cmd_checksums() {
  section "checksums - SHA256SUMS"
  require_cmd sha256sum
  find_package || die "checksums require a package in $DIST"
  ensure_dist
  [ -f "$DIST/build.log" ] || die "checksums require $DIST/build.log"
  [ -f "$DIST/release-manifest.json" ] || die "checksums require $DIST/release-manifest.json"

  (
    cd "$DIST"
    local files=()
    local path
    shopt -s nullglob
    for path in amonite-welcome_*.deb build.log release-manifest.json; do
      [ -f "$path" ] || continue
      files+=("$path")
    done
    shopt -u nullglob
    [ "${#files[@]}" -gt 0 ] || die "no checksum targets in $DIST"
    : >SHA256SUMS
    printf '%s\n' "${files[@]}" | LC_ALL=C sort | while IFS= read -r file; do
      sha256sum "$file" >>SHA256SUMS
    done
  )
  log "  wrote $DIST/SHA256SUMS"
  ( cd "$DIST" && sha256sum -c SHA256SUMS )
  log "  checksum verification: PASS"
}

cmd_sign() {
  section "sign - Amonite Release Signing Key"
  find_package || die "sign requires a package in $DIST"
  [ -f "$DIST/SHA256SUMS" ] || die "sign requires $DIST/SHA256SUMS (run checksums first)"

  if ! signing_requested; then
    SIGNING_STATUS="SKIPPED"
    SIGNING_VERIFICATION="SKIPPED"
    log "  signing skipped: AMONITE_RELEASE_SIGN=$AMONITE_RELEASE_SIGN"
    log "  (explicit disable; silent skip is not allowed)"
    RELEASE_NOTES+=("signing: SKIPPED (AMONITE_RELEASE_SIGN=$AMONITE_RELEASE_SIGN)")
    rm -f "$DIST"/*.asc
    return 0
  fi

  require_signing_key
  rm -f "$DIST/$PACKAGE_NAME.asc" "$DIST/SHA256SUMS.asc"
  gpg_sign_detached "$DIST/$PACKAGE_NAME" "$DIST/$PACKAGE_NAME.asc"
  gpg_sign_detached "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.asc"
  gpg_verify_detached "$DIST/$PACKAGE_NAME.asc" "$DIST/$PACKAGE_NAME"
  gpg_verify_detached "$DIST/SHA256SUMS.asc" "$DIST/SHA256SUMS"
  SIGNING_STATUS="PASS"
  log "  signature verification: PASS (Amonite Release Signing Key)"
}

cmd_manifest() {
  section "manifest - release-manifest.json"
  require_cmd python3
  find_package || die "manifest requires a package in $DIST"
  ensure_dist
  BUILD_TIMESTAMP="${BUILD_TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

  local git_commit="" git_tag="" git_describe=""
  if [ -d "$ROOT/.git" ]; then
    if git_commit="$(git -C "$ROOT" rev-parse --verify HEAD 2>/dev/null)"; then
      :
    else
      git_commit=""
    fi
    if git_tag="$(git -C "$ROOT" describe --tags --exact-match 2>/dev/null)"; then
      :
    else
      git_tag=""
    fi
    if git_describe="$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null)"; then
      :
    else
      git_describe=""
    fi
  fi

  local meson_v ninja_v python_v dpkg_v gpg_v
  meson_v="$(meson --version 2>/dev/null | head -n1 || true)"
  ninja_v="$(ninja --version 2>/dev/null | head -n1 || true)"
  python_v="$(python3 --version 2>/dev/null | head -n1 || true)"
  dpkg_v="$(dpkg-buildpackage --version 2>/dev/null | head -n1 || true)"
  gpg_v="$(gpg --version 2>/dev/null | head -n1 || true)"

  PACKAGE_SHA256="$(sha256sum "$PACKAGE_PATH" | awk '{print $1}')"

  DIST="$DIST" \
  PACKAGE_NAME="$PACKAGE_NAME" \
  PACKAGE_SIZE="$PACKAGE_SIZE" \
  PACKAGE_VERSION="$PACKAGE_VERSION" \
  PACKAGE_ARCH="$PACKAGE_ARCH" \
  PACKAGE_SHA256="$PACKAGE_SHA256" \
  BUILD_TIMESTAMP="$BUILD_TIMESTAMP" \
  GIT_COMMIT="$git_commit" \
  GIT_TAG="$git_tag" \
  GIT_DESCRIBE="$git_describe" \
  STAGE_DOCTOR="${STAGE_DOCTOR:-PASS}" \
  STAGE_VALIDATE="${STAGE_VALIDATE:-PASS}" \
  STAGE_HEALTH="${STAGE_HEALTH:-PASS}" \
  STAGE_VERIFY="${STAGE_VERIFY:-PASS}" \
  STAGE_RELEASE="${STAGE_RELEASE:-PASS}" \
  SIGNING_STATUS="${SIGNING_STATUS:-}" \
  SIGNING_FINGERPRINT="${SIGNING_FINGERPRINT:-}" \
  SIGNING_KEY="${SIGNING_KEY:-}" \
  SIGNING_UID="${SIGNING_UID:-}" \
  SIGNING_VERIFICATION="${SIGNING_VERIFICATION:-}" \
  SIGNING_ENABLED="$(signing_requested && echo true || echo false)" \
  MESON_V="$meson_v" \
  NINJA_V="$ninja_v" \
  PYTHON_V="$python_v" \
  DPKG_V="$dpkg_v" \
  GPG_V="$gpg_v" \
  python3 - <<'PY'
import json, os
from pathlib import Path

dist = Path(os.environ["DIST"])
enabled = os.environ.get("SIGNING_ENABLED") == "true"
manifest = {
    "schema": 1,
    "project": "amonite-welcome",
    "version": os.environ["PACKAGE_VERSION"],
    "package": {
        "filename": os.environ["PACKAGE_NAME"],
        "architecture": os.environ["PACKAGE_ARCH"],
        "size_bytes": int(os.environ["PACKAGE_SIZE"]),
        "sha256": os.environ["PACKAGE_SHA256"],
    },
    "build_timestamp": os.environ["BUILD_TIMESTAMP"],
    "git": {
        "commit": os.environ.get("GIT_COMMIT") or None,
        "tag": os.environ.get("GIT_TAG") or None,
        "describe": os.environ.get("GIT_DESCRIBE") or None,
    },
    "tool_versions": {
        "meson": os.environ.get("MESON_V") or None,
        "ninja": os.environ.get("NINJA_V") or None,
        "python": os.environ.get("PYTHON_V") or None,
        "dpkg-buildpackage": os.environ.get("DPKG_V") or None,
        "gpg": os.environ.get("GPG_V") or None,
    },
    "results": {
        "doctor": os.environ.get("STAGE_DOCTOR") or None,
        "validate": os.environ.get("STAGE_VALIDATE") or None,
        "health": os.environ.get("STAGE_HEALTH") or None,
        "verify": os.environ.get("STAGE_VERIFY") or None,
        "release": os.environ.get("STAGE_RELEASE") or None,
        "signing": os.environ.get("SIGNING_STATUS") or None,
    },
    "signing": {
        "enabled": enabled,
        "status": os.environ.get("SIGNING_STATUS") or None,
        "identity": "Amonite Release Signing Key" if enabled else None,
        "fingerprint": os.environ.get("SIGNING_FINGERPRINT") or None,
        "uid": os.environ.get("SIGNING_UID") or None,
        "verification": os.environ.get("SIGNING_VERIFICATION") or None,
        "canonical_verification": "https://github.com/ManuelGil/amonite/blob/main/VERIFY.md",
    },
    "artifacts": sorted(
        name for name in [
            os.environ["PACKAGE_NAME"],
            "build.log",
            "release-manifest.json",
            "SHA256SUMS",
            (
                os.environ["PACKAGE_NAME"] + ".asc"
                if os.environ.get("SIGNING_STATUS") == "PASS"
                else None
            ),
            (
                "SHA256SUMS.asc"
                if os.environ.get("SIGNING_STATUS") == "PASS"
                else None
            ),
        ]
        if name
    ),
}
path = dist / "release-manifest.json"
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"  wrote {path}")
PY
}

cmd_release_safety() {
  section "release-safety - artifact consistency"
  find_package || die "release safety: package missing from $DIST"
  [ -f "$DIST/SHA256SUMS" ] || die "release safety: SHA256SUMS missing"
  [ -f "$DIST/release-manifest.json" ] || die "release safety: release-manifest.json missing"
  [ -f "$DIST/build.log" ] || die "release safety: build.log missing"

  ( cd "$DIST" && sha256sum -c SHA256SUMS ) || die "release safety: checksum verification failed"

  python3 - <<PY
import json, hashlib, sys
from pathlib import Path
dist = Path("$DIST")
manifest = json.loads((dist / "release-manifest.json").read_text(encoding="utf-8"))
pkg_name = manifest["package"]["filename"]
pkg = dist / pkg_name
if not pkg.is_file():
    sys.exit(f"manifest package missing: {pkg_name}")
digest = hashlib.sha256(pkg.read_bytes()).hexdigest()
expected = manifest["package"]["sha256"]
if digest != expected:
    sys.exit(f"manifest sha256 mismatch: {digest} != {expected}")
if int(pkg.stat().st_size) != int(manifest["package"]["size_bytes"]):
    sys.exit("manifest size mismatch")
print("  manifest matches package: PASS")
PY

  if signing_requested; then
    [ -f "$DIST/$PACKAGE_NAME.asc" ] || die "release safety: package signature missing"
    [ -f "$DIST/SHA256SUMS.asc" ] || die "release safety: SHA256SUMS signature missing"
    gpg_verify_detached "$DIST/$PACKAGE_NAME.asc" "$DIST/$PACKAGE_NAME"
    gpg_verify_detached "$DIST/SHA256SUMS.asc" "$DIST/SHA256SUMS"
    log "  signatures present and valid: PASS"
  else
    log "  signatures: not required (AMONITE_RELEASE_SIGN=$AMONITE_RELEASE_SIGN)"
  fi

  shopt -s nullglob
  local leftovers=(
    "$PARENT"/amonite-welcome_*.deb
    "$PARENT"/amonite-welcome_*.buildinfo
    "$PARENT"/amonite-welcome_*.changes
    "$ROOT"/amonite-welcome_*.deb
  )
  shopt -u nullglob
  if [ "${#leftovers[@]}" -gt 0 ]; then
    die "release safety: stale artifacts outside dist/: ${leftovers[*]}"
  fi
  log "  no stale artifacts outside dist/: PASS"
}

write_build_log() {
  ensure_dist
  find_package || die "build.log requires a package in $DIST"
  {
    printf 'Amonite Welcome release build log\n'
    printf '================================\n'
    printf 'timestamp: %s\n' "${BUILD_TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
    printf 'version:   %s\n' "$PACKAGE_VERSION"
    printf 'package:   %s\n' "$PACKAGE_NAME"
    printf 'size:      %s bytes\n' "$PACKAGE_SIZE"
    printf 'sha256:    %s\n' "$(sha256sum "$PACKAGE_PATH" | awk '{print $1}')"
    printf 'doctor:    %s\n' "${STAGE_DOCTOR:-}"
    printf 'validate:  %s\n' "${STAGE_VALIDATE:-}"
    printf 'verify:    %s\n' "${STAGE_VERIFY:-}"
    printf 'health:    %s\n' "${STAGE_HEALTH:-}"
    printf 'release:   %s\n' "${STAGE_RELEASE:-}"
    printf 'signing:   %s\n' "${SIGNING_STATUS:-pending}"
    if [ -d "$ROOT/.git" ]; then
      printf 'git:       %s\n' "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
      printf 'describe:  %s\n' "$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || true)"
    fi
    printf '\n--- dpkg-deb -I ---\n'
    dpkg-deb -I "$PACKAGE_PATH"
    printf '\n--- dpkg-deb -c (paths) ---\n'
    dpkg-deb -c "$PACKAGE_PATH" | awk '{print $NF}'
  } >"$DIST/build.log"
  log "  wrote $DIST/build.log"
}

cmd_finalize() {
  section "finalize - checksums, signatures, manifest"
  find_package || die "finalize requires a package in $DIST"
  ensure_dist

  # Establish signing status before writing checksummed artifacts.
  if signing_requested; then
    require_signing_key
    rm -f "$DIST/$PACKAGE_NAME.asc"
    gpg_sign_detached "$DIST/$PACKAGE_NAME" "$DIST/$PACKAGE_NAME.asc"
    gpg_verify_detached "$DIST/$PACKAGE_NAME.asc" "$DIST/$PACKAGE_NAME"
    SIGNING_STATUS="PASS"
    log "  package signature: PASS"
  else
    SIGNING_STATUS="SKIPPED"
    SIGNING_VERIFICATION="SKIPPED"
    log "  signing skipped: AMONITE_RELEASE_SIGN=$AMONITE_RELEASE_SIGN"
    log "  (explicit disable; silent skip is not allowed)"
    RELEASE_NOTES+=("signing: SKIPPED (AMONITE_RELEASE_SIGN=$AMONITE_RELEASE_SIGN)")
    rm -f "$DIST"/*.asc
  fi

  write_build_log
  cmd_manifest
  cmd_checksums

  if signing_requested; then
    rm -f "$DIST/SHA256SUMS.asc"
    gpg_sign_detached "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.asc"
    gpg_verify_detached "$DIST/SHA256SUMS.asc" "$DIST/SHA256SUMS"
    log "  SHA256SUMS signature: PASS"
  fi

  cmd_release_safety
}

cmd_release() {
  log "Amonite Welcome release pipeline"
  log "Root: $ROOT"
  BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  STAGE_RELEASE="FAIL"

  if ! check_removable_ownership; then
    die_env "release blocked: foreign-owned artefacts present"
  fi

  cmd_distclean
  cmd_doctor
  STAGE_DOCTOR="PASS"
  cmd_hygiene
  cmd_validate
  STAGE_VALIDATE="PASS"
  cmd_configure
  cmd_build
  cmd_test
  cmd_install
  cmd_verify
  STAGE_VERIFY="PASS"
  local note
  for note in "${RELEASE_NOTES[@]+"${RELEASE_NOTES[@]}"}"; do
    case "$note" in
      verify:\ SKIPPED*) STAGE_VERIFY="SKIPPED" ;;
    esac
  done
  cmd_package
  cmd_inspect
  cmd_health --within-release
  STAGE_HEALTH="PASS"
  STAGE_RELEASE="PASS"
  cmd_finalize
  cmd_purity

  section "summary"
  printf '✔ distclean\n✔ doctor\n✔ hygiene\n✔ validate\n✔ configure\n✔ build\n✔ test\n'
  printf '✔ install\n✔ verify\n✔ package\n✔ inspect\n✔ health\n✔ finalize\n✔ hygiene\n'
  if [ "${#RELEASE_NOTES[@]}" -gt 0 ]; then
    printf '\nNotes:\n'
    printf '  - %s\n' "${RELEASE_NOTES[@]}"
  fi
  printf '\nRelease directory:\n  %s\n' "$DIST"
  printf 'Package:\n  %s\n' "$PACKAGE_NAME"
  printf 'Artifacts:\n'
  find "$DIST" -maxdepth 1 -type f ! -name 'README.md' -printf '  %f\n' | LC_ALL=C sort
  printf '\nReady for publication.\n'
}

cmd_help() {
  cat <<'EOF'
Amonite Welcome packaging pipeline

Usage:
  ./packaging/release.sh [command]

Commands:
  release      Full pipeline → dist/ (package, checksums, sign, manifest)
  doctor       Check required tools and libraries
  hygiene      Check repository purity, ownership, and permissions
  validate     Validate providers.yaml, handbook, desktop, meson
  status       Show repository / build / package state (read-only)
  clean        Remove builddir, package-root, obj-*, debian leftovers
  distclean    clean + remove dist/ artifacts and leftover .deb metadata
  configure    meson setup builddir
  build        meson compile (auto-configures if needed)
  test         meson test (auto-builds if needed)
  install      DESTDIR=package-root meson install (auto-builds if needed)
  verify       run packaging/verify.py (auto-installs; skips GTK without display)
  package      dpkg-buildpackage and collect .deb into dist/
  inspect      inspect the generated .deb (packages if needed)
  health       static + optional runtime health (auto-prepares build/install)
  finalize     checksums, optional GPG signatures, manifest, safety checks
  help         Show this help

Signing:
  Enabled by default. Uses only the Amonite Release Signing Key.
  Fingerprint: 0AFF5507884548626087F84A5E1E335B601FB44B
  Configure:   AMONITE_SIGNING_KEY=<fingerprint>  (must match the fingerprint above)
  Disable:     AMONITE_RELEASE_SIGN=0
  Silent skip is not allowed. Selection by name/email is not allowed.
  Verification: https://github.com/ManuelGil/amonite/blob/main/VERIFY.md

Exit codes:
  0  PASS
  1  Engineering failure
  2  Environment limitation (foreign ownership, missing signing key, etc.)

Self-healing:
  Missing builddir / package-root are prepared automatically by test,
  install, verify, health, and inspect. Runtime GTK work is SKIPPED when
  no DISPLAY or WAYLAND_DISPLAY is present; that is not a software failure.

Release artifacts are written only under dist/.

See docs/ENGINEERING.md and docs/RELEASE.md.
EOF
}

main() {
  local cmd="${1:-release}"
  if [ "$#" -gt 0 ]; then
    shift
  fi
  case "$cmd" in
    release) cmd_release "$@" ;;
    doctor) cmd_doctor "$@" ;;
    hygiene) cmd_hygiene "$@" ;;
    validate) cmd_validate "$@" ;;
    status) cmd_status "$@" ;;
    clean) cmd_clean "$@" ;;
    distclean) cmd_distclean "$@" ;;
    configure) cmd_configure "$@" ;;
    build) cmd_build "$@" ;;
    test) cmd_test "$@" ;;
    install) cmd_install "$@" ;;
    verify) cmd_verify "$@" ;;
    package) cmd_package "$@" ;;
    inspect) cmd_inspect "$@" ;;
    health) cmd_health "$@" ;;
    finalize) cmd_finalize "$@" ;;
    checksums) cmd_checksums "$@" ;;
    sign) cmd_sign "$@" ;;
    manifest) cmd_manifest "$@" ;;
    help|-h|--help) cmd_help ;;
    *)
      die "unknown command: $cmd
Run: $0 help"
      ;;
  esac
}

main "$@"
