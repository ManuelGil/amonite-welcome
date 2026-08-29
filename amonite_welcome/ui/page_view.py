"""Turning one handbook page into widgets.

Reads a :class:`~amonite_welcome.content.Page`, asks the capability service
which actions this system can offer, and composes components. It resolves
nothing and executes nothing.

The composition is a chapter, not a dashboard: a title, the line that says what
the chapter is for, then the prose, then the things the reader can start. There
is no container around a paragraph.
"""

from __future__ import annotations

from gi.repository import Gtk

from amonite_welcome.content import Page, Section
from amonite_welcome.services import catalog as i18n
from amonite_welcome.services import system_info
from amonite_welcome.services.capabilities import visible_actions
from amonite_welcome.ui import a11y, components
from amonite_welcome.ui.activation import ActionActivator


class PageView:
    """Builds page widgets and routes their activations to *activator*."""

    def __init__(self, activator: ActionActivator):
        self._activator = activator

    def build(self, page: Page) -> Gtk.Widget:
        content = components.column(0, "page")
        content.set_valign(Gtk.Align.START)

        header = components.column(4, "page-header")
        header.append(components.page_title(page.title))
        if page.description:
            header.append(components.lead(page.description))
        content.append(header)

        body = components.column(0)
        for section in page.sections:
            widget = self._build_section(section)
            if widget is not None:
                body.append(widget)
        content.append(body)

        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.add_css_class("page-shell")
        scrolled.set_child(components.reading_slot(content))
        scrolled.set_vexpand(True)

        actions = visible_actions(page.actions)
        if not actions:
            return scrolled

        # What the chapter offers stays in view while its prose scrolls: on a
        # short window the reader can still act without finding the bottom.
        bar = components.action_bar()
        for action in actions:
            bar.append(components.action_button(action, self._activator.activate))
        # Named so the group is announced as a whole before its buttons.
        a11y.name(bar, i18n.text("ui", "actions_label", default="Actions"))

        footing = components.column(0, "action-shelf")
        footing.append(components.reading_slot(bar))

        page_box = components.column(0)
        page_box.append(scrolled)
        page_box.append(footing)
        return page_box

    def _build_section(self, section: Section) -> Gtk.Widget | None:
        box = components.column(4, "section")
        box.append(components.section_heading(section.heading))
        if section.data:
            facts = system_info.DATA_READERS[section.data]()
            if not facts:
                return None
            box.append(components.fact_table(facts))
        else:
            box.append(components.prose(section.body))
        return box
