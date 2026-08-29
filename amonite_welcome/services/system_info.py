# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Read-only facts about this installation for handbook ``data:`` sections.

Facts come from standard Linux files and the environment. A value that cannot
be read is omitted so a section shows fewer lines rather than failing.
"""

import os
import platform
import shutil

from amonite_welcome.services import catalog as i18n
from amonite_welcome.services.identity import read_os_release

Fact = tuple[str, str]

_DEBIAN_VERSION_PATH = "/etc/debian_version"
_CPUINFO_PATH = "/proc/cpuinfo"
_MEMINFO_PATH = "/proc/meminfo"


def os_facts() -> list[Fact]:
    """Facts that identify this operating system and desktop session."""
    readers = (
        ("distribution", _distribution),
        ("edition", _edition),
        ("debian_version", _debian_version),
        ("desktop", _desktop),
        ("session_type", _session_type),
        ("architecture", _architecture),
        ("kernel", _kernel),
        ("hostname", _hostname),
    )
    facts: list[Fact] = []
    for key, read in readers:
        value = read()
        if not value:
            continue
        label = i18n.text("facts", key, default=key.replace("_", " ").title())
        facts.append((label, value))
    return facts


def hardware_facts() -> list[Fact]:
    """Facts that describe the computer this installation runs on."""
    readers = (
        ("processor", _cpu_model),
        ("memory", _memory),
        ("disk_usage", _disk_usage),
    )
    facts: list[Fact] = []
    for key, read in readers:
        value = read()
        if not value:
            continue
        label = i18n.text("facts", key, default=key.replace("_", " ").title())
        facts.append((label, value))
    return facts


def _distribution() -> str:
    return read_os_release().get("PRETTY_NAME", "")


def _edition() -> str:
    # os-release(5) VARIANT names the edition of this distribution. A
    # distribution that publishes a single edition sets none, and the row is
    # then omitted rather than shown empty.
    return read_os_release().get("VARIANT", "")


def _debian_version() -> str:
    try:
        with open(_DEBIAN_VERSION_PATH, encoding="utf-8") as debian_version_file:
            return debian_version_file.read().strip()
    except OSError:
        return ""


def _desktop() -> str:
    # The desktop of the *running session*, reported by the session itself.
    # The desktop the distribution ships is a separate fact and belongs to
    # identity (``desktop_env_*``); neither is named in this file.
    return os.environ.get("XDG_CURRENT_DESKTOP", "")


def _session_type() -> str:
    return os.environ.get("XDG_SESSION_TYPE", "")


def _architecture() -> str:
    return platform.machine()


def _kernel() -> str:
    return platform.release()


def _hostname() -> str:
    return platform.node()


def _cpu_model() -> str:
    try:
        with open(_CPUINFO_PATH, encoding="utf-8") as cpuinfo_file:
            for line in cpuinfo_file:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def _memory() -> str:
    try:
        with open(_MEMINFO_PATH, encoding="utf-8") as meminfo_file:
            for line in meminfo_file:
                if line.startswith("MemTotal:"):
                    kibibytes = int(line.split()[1])
                    return f"{kibibytes / (1024 * 1024):.1f} GiB"
    except (OSError, ValueError, IndexError):
        pass
    return ""


def _disk_usage() -> str:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return ""
    used_gib = usage.used / (1024**3)
    total_gib = usage.total / (1024**3)
    return f"{used_gib:.1f} GiB of {total_gib:.1f} GiB used"


DATA_READERS = {
    "os_facts": os_facts,
    "hardware_facts": hardware_facts,
}
