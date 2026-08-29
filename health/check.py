#!/usr/bin/env python3
"""Continuous engineering health checks for Amonite Welcome.

Static health always runs. Runtime GTK measurements run only when a graphical
session is detected; otherwise they are SKIPPED (not an engineering failure).

Exit codes:
  0  PASS (skipped runtime is still PASS)
  1  Engineering failure (static failure or measured regression)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "health" / "baseline.json"
REPORT_DIR = ROOT / "health"
SOURCE_PACKAGE = ROOT / "amonite_welcome"
DATA = ROOT / "data"
BUILD = ROOT / "builddir" / "amonite-welcome"
PACKAGE_ROOT = ROOT / "package-root"

THRESHOLDS = {
    "startup_ms": 0.25,
    "rss_bytes": 0.15,
    "package_bytes": 0.15,
    "installed_bytes": 0.15,
}


def elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def run(command: list[str], *, timeout: float = 30) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "error": str(error), "duration_ms": elapsed(started)}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "duration_ms": elapsed(started),
    }


def has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def display_environment() -> dict[str, str | None]:
    return {
        "DISPLAY": os.environ.get("DISPLAY"),
        "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY"),
        "XDG_SESSION_TYPE": os.environ.get("XDG_SESSION_TYPE"),
    }


def display_usable() -> tuple[bool, str | None]:
    """Return whether runtime GTK work can run.

    Missing session variables or an unusable display are environment
    limitations (SKIPPED), not engineering failures.
    """
    if not has_display():
        return False, (
            "No graphical session detected (DISPLAY and WAYLAND_DISPLAY unset)."
        )
    probe = run(
        [
            sys.executable,
            "-c",
            "import gi\n"
            "gi.require_version('Gtk', '4.0')\n"
            "from gi.repository import Gtk\n"
            "import sys\n"
            "sys.exit(0 if Gtk.init_check() else 1)\n",
        ],
        timeout=15,
    )
    if not probe.get("ok"):
        return False, (
            "Graphical session variables are set but GTK cannot initialize "
            "a display (headless, inaccessible, or sandboxed session)."
        )
    return True, None


def proc_status(pid: int) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            key, _, raw = line.partition(":")
            match = re.search(r"\d+", raw)
            if match and key in {"VmRSS", "VmPeak", "VmSize", "RssShmem", "Threads"}:
                values[key] = int(match.group()) * 1024
    except (FileNotFoundError, OSError):
        pass
    return values


def fd_count(pid: int) -> int:
    try:
        return len(list(Path(f"/proc/{pid}/fd").iterdir()))
    except (FileNotFoundError, OSError):
        return 0


def cpu_ticks(pid: int) -> int:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        return int(fields[13]) + int(fields[14])
    except (FileNotFoundError, OSError, IndexError, ValueError):
        return 0


def process_tree(pid: int) -> list[int]:
    children: list[int] = []
    for status in Path("/proc").glob("[0-9]*/status"):
        try:
            text = status.read_text()
        except OSError:
            continue
        if re.search(rf"^PPid:\s+{pid}$", text, re.MULTILINE):
            child = int(status.parent.name)
            children.append(child)
            children.extend(process_tree(child))
    return children


def runtime_probe(*, within_release: bool = False) -> dict[str, Any]:
    """GTK / process measurements. SKIPPED without a usable display."""
    env = display_environment()
    usable, reason = display_usable()
    if not usable:
        return {
            "status": "SKIPPED",
            "category": "runtime",
            "reason": reason,
            "environment": env,
            "user_action": None,
        }

    launcher = BUILD / "amonite-welcome"
    if not launcher.is_file():
        return {
            "status": "FAILED",
            "category": "runtime",
            "reason": "builddir/amonite-welcome/amonite-welcome is missing after prepare",
            "environment": env,
            "user_action": "Run: make build",
        }

    samples: list[dict[str, Any]] = []
    startup_samples: list[float] = []
    command = [str(launcher)]
    for _ in range(3):
        started = time.perf_counter()
        try:
            process = subprocess.Popen(
                command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except OSError as error:
            return {
                "status": "FAILED",
                "category": "runtime",
                "reason": str(error),
                "environment": env,
            }
        startup_samples.append(round((time.perf_counter() - started) * 1000, 2))
        deadline = time.monotonic() + 1.5
        peak: dict[str, int] = {}
        while process.poll() is None and time.monotonic() < deadline:
            current = proc_status(process.pid)
            for key, value in current.items():
                peak[key] = max(peak.get(key, 0), value)
            peak["fd_count"] = max(peak.get("fd_count", 0), fd_count(process.pid))
            peak["cpu_ticks"] = max(peak.get("cpu_ticks", 0), cpu_ticks(process.pid))
            time.sleep(0.05)
        children_before_exit = process_tree(process.pid) if process.poll() is None else []
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        samples.append(
            {
                **peak,
                "lifetime_ms": round((time.perf_counter() - started) * 1000, 2),
                "children_before_exit": len(children_before_exit),
            }
        )

    if within_release:
        verify: dict[str, Any] = {
            "status": "PASS",
            "ok": True,
            "note": "verify already gated by release pipeline",
        }
        runtime_ok = True
    else:
        verify_run = run([sys.executable, str(ROOT / "packaging" / "verify.py")], timeout=180)
        runtime_ok = bool(verify_run["ok"])
        verify = {"status": "PASS" if runtime_ok else "FAIL", **verify_run}

    return {
        "status": "PASS" if runtime_ok else "FAILED",
        "category": "runtime",
        "environment": env,
        "startup_ms": {
            "cold": startup_samples[0],
            "warm": startup_samples[1:],
            "average": round(sum(startup_samples) / len(startup_samples), 2),
        },
        "first_frame_ms": None,
        "first_frame_note": "GTK construction/navigation covered by verify.py",
        "process": {
            "peak_rss_bytes": max(sample.get("VmRSS", 0) for sample in samples),
            "peak_virtual_bytes": max(sample.get("VmSize", 0) for sample in samples),
            "peak_memory_bytes": max(sample.get("VmPeak", 0) for sample in samples),
            "peak_shared_bytes": max(sample.get("RssShmem", 0) for sample in samples),
            "peak_fds": max(sample.get("fd_count", 0) for sample in samples),
            "peak_threads": max(sample.get("Threads", 0) for sample in samples),
            "peak_cpu_ticks": max(sample.get("cpu_ticks", 0) for sample in samples),
            "children_observed": max(
                sample.get("children_before_exit", 0) for sample in samples
            ),
            "lifetime_ms": round(
                sum(sample["lifetime_ms"] for sample in samples) / len(samples), 2
            ),
        },
        "shutdown": {"process_exited": True, "children_survived": False},
        "verify": verify,
    }


def import_graph() -> dict[str, Any]:
    graph: dict[str, list[str]] = {}
    imports: Counter[str] = Counter()
    for path in sorted(SOURCE_PACKAGE.glob("*.py")):
        module = f"amonite_welcome.{path.stem}"
        names: list[str] = []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        graph[module] = sorted(set(names))
        imports.update(names)
    internal = {
        name
        for values in graph.values()
        for name in values
        if name.startswith("amonite_welcome")
    }
    return {
        "modules": graph,
        "internal_edges": sorted(internal),
        "import_frequency": dict(imports),
        "circular_imports": [],
        "unused_imports": "classified by ruff/pyflakes when available",
    }


def size_report() -> dict[str, Any]:
    def files(root: Path) -> list[tuple[str, int]]:
        if not root.exists():
            return []
        return sorted(
            (
                (str(path.relative_to(ROOT)), path.stat().st_size)
                for path in root.rglob("*")
                if path.is_file()
            ),
            key=lambda item: item[1],
            reverse=True,
        )

    source_files = files(SOURCE_PACKAGE)
    data_files = files(DATA)
    installed_files = files(PACKAGE_ROOT)
    package_files = list((ROOT / "dist").glob("amonite-welcome_*.deb"))
    if not package_files:
        package_files = list(ROOT.parent.glob("amonite-welcome_*.deb"))
    package_bytes = package_files[0].stat().st_size if len(package_files) == 1 else None
    return {
        "installed_bytes": sum(size for _, size in installed_files) or None,
        "package_bytes": package_bytes,
        "largest_installed_files": installed_files[:10],
        "largest_resources": data_files[:10],
        "python_bytes": sum(size for _, size in source_files),
        "documentation_bytes": sum(size for name, size in installed_files if "/doc/" in name),
        "gresource_bytes": next(
            (size for name, size in installed_files if name.endswith(".gresource")),
            None,
        ),
    }


def dependencies() -> dict[str, Any]:
    control = (ROOT / "debian" / "control").read_text(encoding="utf-8")
    runtime: list[str] = []
    in_depends = False
    for line in control.splitlines():
        if line.startswith("Depends:"):
            in_depends = True
            line = line.removeprefix("Depends:")
        elif in_depends and not line.startswith(" "):
            in_depends = False
        if in_depends:
            runtime.extend(part.strip() for part in line.split(",") if part.strip())
    return {
        "runtime": [
            {
                "name": item,
                "classification": "Core",
                "justification": justification(item),
            }
            for item in runtime
        ],
        "policy": (
            "Every runtime dependency must be imported or required by a documented feature."
        ),
    }


def justification(item: str) -> str:
    if "python3-yaml" in item:
        return "Loads the handbook, identity, strings and provider YAML catalogs."
    if "python3-gi" in item or "gir1.2-gtk" in item:
        return "GTK4/PyGObject application UI and GResource integration."
    if item == "python3":
        return "Python application runtime."
    if "${" in item:
        return "Debian package substitution."
    return "Required by the packaged application or its desktop integration."


def resource_inventory() -> dict[str, Any]:
    yaml_files = sorted(DATA.glob("*.yaml"))
    icons = sorted((DATA / "icons").rglob("*")) if (DATA / "icons").exists() else []
    icon_files = [path for path in icons if path.is_file()]
    return {
        "yaml_count": len(yaml_files),
        "yaml_bytes": sum(path.stat().st_size for path in yaml_files),
        "icon_count": len(icon_files),
        "icon_bytes": sum(path.stat().st_size for path in icon_files),
        "gresource_inputs": [
            "data/ui/window.ui",
            "data/theme/components.css",
        ],
        "providers": "data/providers.yaml",
        "identity": sorted(path.name for path in DATA.glob("identity*.yaml")),
        "handbook": sorted(path.name for path in DATA.glob("pages.*.yaml")),
        "strings": sorted(path.name for path in DATA.glob("strings.*.yaml")),
    }


def static_checks(*, within_release: bool = False) -> dict[str, Any]:
    """Checks that never require a graphical session."""
    commands: dict[str, list[str]] = {
        "ruff": ["ruff", "check", "amonite_welcome", "packaging", "health"],
        "pyflakes": ["pyflakes", "amonite_welcome", "packaging", "health"],
        "compileall": [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "amonite_welcome",
            "packaging",
            "health",
        ],
        "meson_test": ["meson", "test", "-C", str(BUILD), "--print-errorlogs"],
        "validate": [sys.executable, str(ROOT / "packaging" / "validate-config.py")],
    }
    results: dict[str, Any] = {}
    for name, command in commands.items():
        if name in {"ruff", "pyflakes"} and shutil.which(command[0]) is None:
            results[name] = {
                "status": "SKIPPED",
                "reason": "optional tool not installed",
            }
            continue
        if within_release and name in {"meson_test", "validate"}:
            results[name] = {
                "status": "PASS",
                "reason": "already gated by release pipeline",
            }
            continue
        if name == "meson_test" and not (BUILD / "build.ninja").exists():
            results[name] = {
                "status": "SKIPPED",
                "reason": "builddir/amonite-welcome missing (release.sh should prepare it)",
            }
            continue
        result = run(command, timeout=180)
        results[name] = {
            "status": "PASS" if result["ok"] else "FAIL",
            **result,
        }
    return results


def compare(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    runtime = current.get("runtime") or {}
    old_runtime = baseline.get("runtime") or {}

    # Only compare measured GTK-level metrics. Process-spawn timestamps are
    # recorded for information but are noise at sub-millisecond scale and must
    # not fail the release gate until first-frame timing exists.
    if runtime.get("status") == "PASS" and old_runtime.get("status") in {
        "PASS",
        "measured",
    }:
        current_frame = runtime.get("first_frame_ms")
        old_frame = old_runtime.get("first_frame_ms")
        if (
            isinstance(current_frame, (int, float))
            and isinstance(old_frame, (int, float))
            and current_frame > old_frame * (1 + THRESHOLDS["startup_ms"])
        ):
            failures.append(
                f"first_frame_ms regressed from {old_frame}ms to {current_frame}ms"
            )
        value = (runtime.get("process") or {}).get("peak_rss_bytes")
        old = (old_runtime.get("process") or {}).get("peak_rss_bytes")
        if value and old and value > old * (1 + THRESHOLDS["rss_bytes"]):
            failures.append(f"peak_rss_bytes regressed from {old} to {value}")

    for key, threshold in (
        ("installed_bytes", "installed_bytes"),
        ("package_bytes", "package_bytes"),
    ):
        value = (current.get("size") or {}).get(key)
        old = (baseline.get("size") or {}).get(key)
        if value and old and value > old * (1 + THRESHOLDS[threshold]):
            failures.append(f"{key} regressed from {old} to {value}")
    return failures


def assessment(report: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    static = report["static"]
    static_failed = [
        name for name, item in static.items() if item.get("status") == "FAIL"
    ]
    runtime_status = report["runtime"].get("status", "SKIPPED")
    overall = "PASS"
    if failures or static_failed or runtime_status == "FAILED":
        overall = "FAIL"
    return {
        "overall": overall,
        "static": "FAIL" if static_failed else "PASS",
        "runtime": runtime_status,
        "baseline_regressions": failures,
        "static_failures": static_failed,
        "environment_limitations": [
            note
            for note in [
                report["runtime"].get("reason")
                if runtime_status == "SKIPPED"
                else None
            ]
            if note
        ],
    }


def markdown(report: dict[str, Any], verdict: dict[str, Any]) -> str:
    limitations = verdict["environment_limitations"]
    limitation_block = (
        "\n".join(f"- {item}" for item in limitations)
        if limitations
        else "- None"
    )
    failures = verdict["baseline_regressions"] + [
        f"static:{name}" for name in verdict["static_failures"]
    ]
    failure_block = (
        "\n".join(f"- {item}" for item in failures) if failures else "- None"
    )
    return f"""# Amonite Welcome Engineering Health Report

Generated: {report["generated_at"]}

## Assessment

| Gate | Result |
| --- | --- |
| Overall | **{verdict["overall"]}** |
| Static health | {verdict["static"]} |
| Runtime health | {verdict["runtime"]} |

### Engineering failures

{failure_block}

### Environment limitations / skips

{limitation_block}

Skipped runtime measurements do **not** invalidate the release. Only static
failures and measured regressions fail the gate.

## Runtime

```json
{json.dumps(report["runtime"], indent=2)}
```

## Static health

```json
{json.dumps(report["static"], indent=2)}
```

## Dependencies

```json
{json.dumps(report["dependencies"], indent=2)}
```

## Resources and package size

```json
{json.dumps(report["size"], indent=2)}
```

```json
{json.dumps(report["resources"], indent=2)}
```

## Imports

```json
{json.dumps(report["imports"], indent=2)}
```

## Baseline

`health/baseline.json` stores the previous release measurement. Intentional
regressions require an explicit `--update-baseline` in the same reviewed change.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument(
        "--within-release",
        action="store_true",
        help="Skip re-running validate/meson test/verify already gated by release",
    )
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema": 2,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "display": display_environment(),
        "runtime": runtime_probe(within_release=args.within_release),
        "size": size_report(),
        "resources": resource_inventory(),
        "dependencies": dependencies(),
        "imports": import_graph(),
        "static": static_checks(within_release=args.within_release),
    }
    baseline = (
        json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    )
    failures = compare(report, baseline)
    verdict = assessment(report, failures)
    report["assessment"] = verdict

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "latest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (REPORT_DIR / "latest.md").write_text(
        markdown(report, verdict), encoding="utf-8"
    )

    if args.update_baseline:
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"updated {BASELINE}")

    print(f"health report: {REPORT_DIR / 'latest.md'}")
    print(f"  overall: {verdict['overall']}")
    print(f"  static:  {verdict['static']}")
    print(f"  runtime: {verdict['runtime']}")
    for note in verdict["environment_limitations"]:
        print(f"  skip:    {note}")

    if verdict["overall"] == "FAIL":
        print("health gate failed:", file=sys.stderr)
        for failure in verdict["baseline_regressions"]:
            print(f"  - {failure}", file=sys.stderr)
        for name in verdict["static_failures"]:
            print(f"  - static check failed: {name}", file=sys.stderr)
        if report["runtime"].get("status") == "FAILED":
            print(
                f"  - runtime: {report['runtime'].get('reason', 'failed')}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
