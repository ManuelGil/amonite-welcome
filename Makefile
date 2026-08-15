# SPDX-License-Identifier: GPL-3.0-or-later
#
# Public maintainer interface for Amonite Welcome.
# Implementation lives in packaging/ and health/; this file only delegates.

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
RELEASE := $(ROOT)/packaging/release.sh

.PHONY: all build test validate verify health check package release clean help

# Default: local Meson build (safe, no packaging or signing).
all: build

build:
	$(RELEASE) build

test:
	$(RELEASE) test

validate:
	$(RELEASE) validate

verify:
	$(RELEASE) verify

health:
	$(RELEASE) health

# Combined static + post-install + health gates (not a full signed release).
check: validate verify health

package:
	$(RELEASE) package

release:
	$(RELEASE) release

clean:
	$(RELEASE) clean

help:
	@printf '%s\n' \
		'make / make build  - Meson compile (auto-configure)' \
		'make test          - Meson tests' \
		'make validate      - Catalog / desktop / authoring checks' \
		'make verify        - Post-install functional checks' \
		'make health        - Engineering health gate' \
		'make check         - validate + verify + health' \
		'make package       - Build .deb into dist/' \
		'make release       - Full signed release pipeline' \
		'make clean         - Remove rebuild trees' \
		'' \
		'Additional stages: $(RELEASE) help'
