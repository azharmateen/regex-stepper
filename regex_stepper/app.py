"""Textual TUI application for stepping through regex execution."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, RichLog
from rich.text import Text
from rich.panel import Panel

from .engine import EventType, StepEvent, step_through


class PatternPanel(Static):
    """Top panel showing the regex pattern with cursor."""

    def __init__(self, pattern: str, **kwargs):
        super().__init__(**kwargs)
        self.pattern = pattern
        self.highlight_start = -1
        self.highlight_end = -1

    def render(self) -> Text:
        text = Text()
        text.append("Pattern: /", style="bold")
        for i, ch in enumerate(self.pattern):
            if self.highlight_start <= i < self.highlight_end:
                text.append(ch, style="bold white on green")
            else:
                text.append(ch, style="cyan")
        text.append("/", style="bold")
        return text

    def set_highlight(self, start: int, end: int) -> None:
        self.highlight_start = start
        self.highlight_end = end
        self.refresh()


class StringPanel(Static):
    """Middle panel showing the test string with match highlighting."""

    def __init__(self, test_string: str, **kwargs):
        super().__init__(**kwargs)
        self.test_string = test_string
        self.cursor_pos = -1
        self.match_start = -1
        self.match_end = -1

    def render(self) -> Text:
        text = Text()
        text.append("String:  \"", style="bold")
        for i, ch in enumerate(self.test_string):
            if self.match_start <= i < self.match_end:
                text.append(ch, style="bold white on blue")
            elif i == self.cursor_pos:
                text.append(ch, style="bold white on yellow")
            else:
                text.append(ch, style="white")
        text.append("\"", style="bold")

        # Show cursor indicator
        if self.cursor_pos >= 0:
            text.append(f"  (pos: {self.cursor_pos})", style="dim")

        return text

    def set_state(self, cursor: int, match_start: int = -1, match_end: int = -1) -> None:
        self.cursor_pos = cursor
        self.match_start = match_start
        self.match_end = match_end
        self.refresh()


class StepInfo(Static):
    """Status bar showing current step info."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._text = "Press Right arrow to step forward, Left to step back"

    def update_info(self, text: str) -> None:
        self._text = text
        self.refresh()

    def render(self) -> Text:
        return Text(self._text, style="bold")


EVENT_STYLES = {
    EventType.MATCH: "green",
    EventType.FAIL: "red",
    EventType.BACKTRACK: "yellow",
    EventType.TRY: "cyan",
    EventType.GROUP_START: "magenta",
    EventType.GROUP_END: "magenta",
    EventType.BRANCH_TRY: "blue",
    EventType.COMPLETE: "bold green",
    EventType.NO_MATCH: "bold red",
}


class RegexStepperApp(App):
    """TUI for stepping through regex execution."""

    CSS = """
    #pattern-panel {
        height: 3;
        padding: 0 1;
        background: $surface;
        border: solid $primary;
    }

    #string-panel {
        height: 3;
        padding: 0 1;
        background: $surface;
        border: solid $primary;
    }

    #step-info {
        height: 3;
        padding: 0 1;
        background: $surface;
        border: solid $accent;
    }

    #step-log {
        height: 1fr;
        border: solid $primary;
    }

    #groups-panel {
        height: auto;
        max-height: 5;
        padding: 0 1;
        background: $surface;
        border: solid $secondary;
    }
    """

    BINDINGS = [
        Binding("right", "step_forward", "Step Forward"),
        Binding("left", "step_back", "Step Back"),
        Binding("home", "first_step", "First Step"),
        Binding("end", "last_step", "Last Step"),
        Binding("r", "reset", "Reset"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, pattern: str, test_string: str):
        super().__init__()
        self.pattern = pattern
        self.test_string = test_string
        self.current_step = -1
        self.events: list[StepEvent] = []
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield PatternPanel(self.pattern, id="pattern-panel")
        yield StringPanel(self.test_string, id="string-panel")
        yield StepInfo(id="step-info")
        yield Static("Groups: (none)", id="groups-panel")
        yield RichLog(id="step-log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "regex-stepper"
        self.sub_title = f"/{self.pattern}/"

        # Run the stepper engine
        self.result = step_through(self.pattern, self.test_string)
        self.events = self.result.events

        log = self.query_one("#step-log", RichLog)
        log.write(f"[bold]Loaded {len(self.events)} steps. Use arrow keys to navigate.[/bold]")
        log.write(f"[dim]Match result: {'MATCH' if self.result.matched else 'NO MATCH'}[/dim]")
        log.write(f"[dim]Backtracks: {self.result.total_backtracks}[/dim]")
        log.write("")

    def _update_display(self) -> None:
        if self.current_step < 0 or self.current_step >= len(self.events):
            return

        event = self.events[self.current_step]

        # Update pattern highlight
        pattern_panel = self.query_one("#pattern-panel", PatternPanel)
        pattern_panel.set_highlight(event.pattern_pos, event.pattern_end)

        # Update string panel
        string_panel = self.query_one("#string-panel", StringPanel)
        string_panel.set_state(
            cursor=event.string_pos,
            match_start=event.string_pos if event.event_type == EventType.MATCH else -1,
            match_end=event.string_end if event.event_type == EventType.MATCH else -1,
        )

        # Update step info
        step_info = self.query_one("#step-info", StepInfo)
        step_info.update_info(
            f"Step {self.current_step + 1}/{len(self.events)} | "
            f"{event.event_type.value.upper()} | "
            f"Pattern pos: {event.pattern_pos} | String pos: {event.string_pos}"
        )

        # Update groups
        groups_panel = self.query_one("#groups-panel", Static)
        if event.groups:
            groups_str = ", ".join(f"${k}='{v}'" for k, v in event.groups.items())
            groups_panel.update(f"Groups: {groups_str}")
        else:
            groups_panel.update("Groups: (none)")

    def action_step_forward(self) -> None:
        if self.current_step < len(self.events) - 1:
            self.current_step += 1
            event = self.events[self.current_step]
            style = EVENT_STYLES.get(event.event_type, "white")
            log = self.query_one("#step-log", RichLog)
            log.write(
                f"[{style}]#{self.current_step + 1} "
                f"[{event.event_type.value.upper()}] "
                f"{event.description}[/{style}]"
            )
            self._update_display()

    def action_step_back(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            log = self.query_one("#step-log", RichLog)
            log.write(f"[dim]<< Stepped back to #{self.current_step + 1}[/dim]")
            self._update_display()

    def action_first_step(self) -> None:
        self.current_step = 0
        self._update_display()
        log = self.query_one("#step-log", RichLog)
        log.write("[dim]<< Jumped to first step[/dim]")

    def action_last_step(self) -> None:
        self.current_step = len(self.events) - 1
        self._update_display()
        log = self.query_one("#step-log", RichLog)
        log.write("[dim]>> Jumped to last step[/dim]")

    def action_reset(self) -> None:
        self.current_step = -1
        pattern_panel = self.query_one("#pattern-panel", PatternPanel)
        pattern_panel.set_highlight(-1, -1)
        string_panel = self.query_one("#string-panel", StringPanel)
        string_panel.set_state(-1)
        step_info = self.query_one("#step-info", StepInfo)
        step_info.update_info("Reset. Press Right arrow to begin stepping.")
        log = self.query_one("#step-log", RichLog)
        log.write("[dim]-- Reset --[/dim]")


def run_tui(pattern: str, test_string: str) -> None:
    """Launch the TUI debugger."""
    app = RegexStepperApp(pattern, test_string)
    app.run()
