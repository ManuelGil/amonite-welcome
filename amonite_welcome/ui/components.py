"""The visual vocabulary of Welcome.

Small builders, one per element the handbook can show. Each owns its own
accessible semantics and carries only a CSS class for appearance: no colours,
no fonts, and no spacing decisions live here.

The vocabulary is deliberately short. A handbook is prose, a short table of
facts, and a few things the reader can start; anything that would wrap that in
another container has been left out.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from gi.repository import Gtk

from amonite_welcome.content import Action
from amonite_welcome.services.system_info import Fact
from amonite_welcome.ui import a11y

# The reading measure. GTK CSS has no max-width, so line length is a label
# property and the column that holds them is given one width: the same measure
# on every chapter, whatever that chapter's longest paragraph happens to be.
# 64 characters plus the page padding still leaves the window under 800px.
PROSE_WIDTH_CHARS = 64
READING_COLUMN_WIDTH = 574


def _label(text: str, css_class: str, role, *, wrap: bool = True) -> Gtk.Label:
    label = Gtk.Label(
        label=text,
        xalign=0,
        wrap=wrap,
        max_width_chars=PROSE_WIDTH_CHARS if wrap else -1,
        accessible_role=role,
    )
    label.add_css_class(css_class)
    return label


def reading_slot(child: Gtk.Widget) -> Gtk.CenterBox:
    """Place *child* on the page's reading measure.

    A centre box gives its centre slot exactly the width that slot asks for, so
    the column keeps one measure however wide the window becomes, and every
    part of the chapter — prose, tables, the actions below them — sits on the
    same axis instead of drifting apart as the window grows.
    """
    child.set_size_request(READING_COLUMN_WIDTH, -1)
    holder = Gtk.CenterBox()
    holder.set_center_widget(child)
    return holder


def column(spacing: int, *css_classes: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for css_class in css_classes:
        box.add_css_class(css_class)
    return box


def page_title(text: str) -> Gtk.Label:
    label = _label(text, "page-title", a11y.HEADING, wrap=False)
    a11y.heading_level(label, 1)
    return label


def lead(text: str) -> Gtk.Label:
    """The one-line answer to "what is this chapter about"."""
    return _label(text, "lead", a11y.PARAGRAPH)


def section_heading(text: str) -> Gtk.Label:
    label = _label(text, "section-heading", a11y.HEADING)
    a11y.heading_level(label, 2)
    return label


def prose(text: str) -> Gtk.Label:
    return _label(text, "section-body", a11y.PARAGRAPH)


def chapter_number(position: int) -> Gtk.Label:
    """The chapter's place in the handbook. Decorative: the title is the name."""
    label = Gtk.Label(label=f"{position}", xalign=0, accessible_role=a11y.DECORATIVE)
    label.add_css_class("chapter-number")
    return label


def fact_table(facts: Sequence[Fact]) -> Gtk.Grid:
    """Key and value in two columns.

    The key is decorative and the value carries the pair as its accessible
    name, so a screen reader announces "Kernel: 6.12" once instead of reading
    two disconnected labels.
    """
    grid = Gtk.Grid(column_spacing=28, row_spacing=0)
    grid.add_css_class("fact-table")
    for row, (key, value) in enumerate(facts):
        key_label = Gtk.Label(label=key, xalign=0, accessible_role=a11y.DECORATIVE)
        key_label.add_css_class("fact-key")
        key_label.set_valign(Gtk.Align.BASELINE)
        grid.attach(key_label, 0, row, 1, 1)

        value_label = Gtk.Label(
            label=value,
            xalign=0,
            wrap=True,
            max_width_chars=PROSE_WIDTH_CHARS,
            hexpand=True,
            accessible_role=a11y.PARAGRAPH,
        )
        value_label.add_css_class("fact-value")
        value_label.set_valign(Gtk.Align.BASELINE)
        a11y.name(value_label, f"{key}: {value}")
        grid.attach(value_label, 1, row, 1, 1)
    return grid


def action_bar() -> Gtk.FlowBox:
    """Where a chapter's actions sit.

    A flow box because the number of actions is decided by what this system can
    do, and their labels by translation: they wrap when they must and stay on
    one line when they fit, at any window size and in any language.
    """
    flow = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        column_spacing=8,
        row_spacing=8,
        homogeneous=False,
        min_children_per_line=1,
        max_children_per_line=4,
    )
    flow.add_css_class("action-bar")
    # Sit at the start of the measure and keep the buttons next to each other:
    # without this the flow box spreads its columns across the whole width and
    # two buttons end up at opposite ends of the page.
    flow.set_halign(Gtk.Align.START)
    return flow


def action_button(action: Action, on_activate: Callable[[Action], None]) -> Gtk.Button:
    """One thing the reader can start.

    A button, because that is what a control that does something is. The
    button knows a label and an icon; it does not know what the action
    resolves to, and it never runs anything itself.
    """
    button = Gtk.Button(label=action.label)
    button.add_css_class("action")
    button.set_halign(Gtk.Align.START)
    if action.primary:
        button.add_css_class("suggested-action")
    if action.description:
        # Said once, to whoever asks for it, instead of printed under every row.
        button.set_tooltip_text(action.description)
        a11y.describe(button, action.description)
    button.connect("clicked", lambda _button: on_activate(action))
    return button


def chapter_row(position: int, page_id: str, title: str) -> Gtk.ListBoxRow:
    """One chapter in the table of contents."""
    box = Gtk.Box(spacing=12)
    box.append(chapter_number(position))
    label = Gtk.Label(
        label=title, xalign=0, wrap=True, hexpand=True, accessible_role=a11y.PARAGRAPH
    )
    box.append(label)

    row = Gtk.ListBoxRow(child=box)
    row.add_css_class("chapter")
    row.page_id = page_id
    a11y.name(row, title)
    return row
