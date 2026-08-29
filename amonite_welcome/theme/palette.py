"""Turning whatever colours the system publishes into a readable palette.

Pure functions, no GTK. The input is a handful of raw colours read from the
running desktop; the output is the semantic token set the stylesheet consumes.
Between the two sits the rule that makes this safe to do at all: every pair of
colours that ends up as text on a surface is checked, and a colour that cannot
be read is moved along its own hue until it can.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

# WCAG 2.1 AA for body text. Applied to every text/surface pair below.
MIN_TEXT_CONTRAST = 4.5
# Hairlines only have to be visible, not readable.
MIN_BORDER_CONTRAST = 1.25


def parse(colour: str) -> tuple[float, float, float]:
    """Read ``#rrggbb`` into floats. Raises ValueError on anything else."""
    text = colour.strip()
    if not text.startswith("#") or len(text) != 7:
        raise ValueError(f"not a #rrggbb colour: {colour!r}")
    return tuple(int(text[index : index + 2], 16) / 255 for index in (1, 3, 5))


def format_colour(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, channel)) * 255):02x}" for channel in rgb)


def luminance(colour: str) -> float:
    channels = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in parse(colour)
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def mix(colour: str, into: str, amount: float) -> str:
    """Blend *colour* *amount* of the way towards *into*."""
    source, target = parse(colour), parse(into)
    return format_colour(
        tuple(a + (b - a) * amount for a, b in zip(source, target))
    )


def is_dark(colour: str) -> bool:
    return luminance(colour) < 0.5


def readable(colour: str, on: str, target: float = MIN_TEXT_CONTRAST) -> str:
    """Return *colour* moved along its own hue until it reads on *on*.

    A distribution accent keeps as much of its character as it can: hue and
    saturation are untouched and only lightness moves, stopping at the first
    step that satisfies *target*. Both directions are tried and the smaller
    change wins, so a mid-tone accent is darkened or lightened, whichever the
    surface needs. When the hue cannot reach the target at either end, plain
    black or white takes over: an unreadable interface is not a style.
    """
    if contrast(colour, on) >= target:
        return colour
    hue, lightness, saturation = colorsys.rgb_to_hls(*parse(colour))
    step = 0.02
    for index in range(1, 51):
        for direction in (-1, 1):
            moved = lightness + direction * step * index
            if not 0.0 <= moved <= 1.0:
                continue
            candidate = format_colour(colorsys.hls_to_rgb(hue, moved, saturation))
            if contrast(candidate, on) >= target:
                return candidate
    return max(("#000000", "#ffffff"), key=lambda plain: contrast(plain, on))


@dataclass(frozen=True)
class SystemColours:
    """The raw colours a desktop publishes, or the built-in stand-ins."""

    background: str
    shell: str
    foreground: str
    accent: str
    accent_foreground: str
    border: str
    source: str = "fallback"


# Used only when the desktop publishes nothing usable. Deliberately quiet: if
# Welcome has to invent an identity, it should not shout one.
FALLBACK_LIGHT = SystemColours(
    background="#ffffff",
    shell="#f4f2ef",
    foreground="#1d1b19",
    accent="#8a4a1f",
    accent_foreground="#ffffff",
    border="#d9d4cc",
)
FALLBACK_DARK = SystemColours(
    background="#1c1b1a",
    shell="#242322",
    foreground="#ebe8e3",
    accent="#d98a52",
    accent_foreground="#1c1b1a",
    border="#393633",
)


def fallback(dark: bool) -> SystemColours:
    return FALLBACK_DARK if dark else FALLBACK_LIGHT


def derive(colours: SystemColours) -> dict[str, str]:
    """Build the semantic token set from *colours*.

    Surfaces are derived from the desktop's own background and foreground, so
    light and dark are the same computation applied to different input rather
    than two palettes maintained by hand.
    """
    background = colours.background
    shell = colours.shell
    foreground = readable(colours.foreground, background)

    muted = readable(mix(foreground, background, 0.32), background)
    faint = readable(mix(foreground, background, 0.46), background)
    # The shell is a different surface; text placed there must hold up too.
    muted = readable(muted, shell)
    faint = readable(faint, shell)

    # A hairline only has to be seen. Nudge it towards the text in small steps
    # rather than replacing it, so a theme's own border keeps its character.
    border = colours.border
    for step in range(1, 21):
        if contrast(border, background) >= MIN_BORDER_CONTRAST:
            break
        border = mix(colours.border, foreground, 0.05 * step)

    accent_fill = colours.accent
    accent_text = readable(accent_fill, background)
    accent_foreground = readable(colours.accent_foreground, accent_fill)
    accent_soft = mix(accent_fill, shell, 0.88)
    selected_text = readable(accent_text, accent_soft)

    return {
        "aw_bg": background,
        "aw_shell": shell,
        "aw_hover": mix(shell, foreground, 0.07),
        "aw_fg": foreground,
        "aw_fg_muted": muted,
        "aw_fg_faint": faint,
        "aw_border": border,
        "aw_accent": accent_text,
        "aw_accent_fill": accent_fill,
        "aw_accent_fg": accent_foreground,
        "aw_accent_soft": accent_soft,
        "aw_selected_fg": selected_text,
    }


# Token pairs that end up as text on a surface. Checked after derivation, and
# by the verification suite against hostile input.
TEXT_PAIRS = (
    ("aw_fg", "aw_bg"),
    ("aw_fg", "aw_shell"),
    ("aw_fg_muted", "aw_bg"),
    ("aw_fg_muted", "aw_shell"),
    ("aw_fg_faint", "aw_bg"),
    ("aw_fg_faint", "aw_shell"),
    ("aw_accent", "aw_bg"),
    ("aw_accent_fg", "aw_accent_fill"),
    ("aw_selected_fg", "aw_accent_soft"),
)


def unreadable_pairs(tokens: dict[str, str]) -> list[tuple[str, str, float]]:
    """Return the text pairs in *tokens* that fall short of AA."""
    failures = []
    for foreground, background in TEXT_PAIRS:
        ratio = contrast(tokens[foreground], tokens[background])
        if ratio < MIN_TEXT_CONTRAST:
            failures.append((foreground, background, ratio))
    return failures


def stylesheet(tokens: dict[str, str]) -> str:
    """Render *tokens* as the GTK colour definitions the components expect."""
    lines = ["/* Generated from the running desktop. Do not edit. */"]
    lines += [f"@define-color {name} {value};" for name, value in sorted(tokens.items())]
    return "\n".join(lines) + "\n"
