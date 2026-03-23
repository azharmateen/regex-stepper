"""Click CLI for regex-stepper."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .engine import EventType, step_through
from .explainer import explain
from .benchmarker import benchmark, format_benchmark

console = Console()

EVENT_COLORS = {
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


@click.group()
@click.version_option(version="1.0.0", prog_name="regex-stepper")
def main():
    """TUI debugger for stepping through regex execution frame-by-frame."""
    pass


@main.command()
@click.argument("pattern")
@click.argument("test_string")
@click.option("--tui/--no-tui", default=True, help="Use interactive TUI (default) or print all steps.")
@click.option("--max-steps", default=500, help="Maximum steps to display in non-TUI mode.")
def debug(pattern: str, test_string: str, tui: bool, max_steps: int):
    """Step through regex execution frame by frame.

    PATTERN is the regex pattern to debug.
    TEST_STRING is the string to match against.
    """
    if tui:
        try:
            from .app import run_tui
            run_tui(pattern, test_string)
        except Exception as e:
            console.print(f"[red]TUI error: {e}[/red]")
            console.print("[dim]Falling back to non-interactive mode...[/dim]")
            _print_steps(pattern, test_string, max_steps)
    else:
        _print_steps(pattern, test_string, max_steps)


def _print_steps(pattern: str, test_string: str, max_steps: int):
    """Print all steps in non-interactive mode."""
    console.print(f"\n[bold]Pattern:[/bold] /{pattern}/")
    console.print(f"[bold]String:[/bold]  \"{test_string}\"\n")

    result = step_through(pattern, test_string)

    table = Table(title="Execution Steps", show_lines=False)
    table.add_column("#", justify="right", style="dim", width=5)
    table.add_column("Event", width=12)
    table.add_column("Pat Pos", justify="center", width=8)
    table.add_column("Str Pos", justify="center", width=8)
    table.add_column("Description", min_width=40)

    displayed = 0
    for i, event in enumerate(result.events):
        if displayed >= max_steps:
            console.print(f"\n[dim]... truncated at {max_steps} steps (total: {len(result.events)})[/dim]")
            break

        color = EVENT_COLORS.get(event.event_type, "white")
        table.add_row(
            str(i + 1),
            Text(event.event_type.value.upper(), style=color),
            f"{event.pattern_pos}-{event.pattern_end}",
            f"{event.string_pos}-{event.string_end}",
            event.description,
        )
        displayed += 1

    console.print(table)

    # Summary
    console.print()
    if result.matched:
        console.print(
            f"[bold green]MATCH[/bold green] at position "
            f"{result.match_start}-{result.match_end}: "
            f"\"{test_string[result.match_start:result.match_end]}\""
        )
    else:
        console.print("[bold red]NO MATCH[/bold red]")

    console.print(f"[dim]Total steps: {len(result.events)} | Backtracks: {result.total_backtracks}[/dim]")


@main.command()
@click.argument("pattern")
def explain_cmd(pattern: str):
    """Explain a regex pattern in plain English.

    PATTERN is the regex pattern to explain.
    """
    output = explain(pattern)
    console.print(f"\n{output}")


# Register 'explain' as the command name
explain_cmd.name = "explain"


@main.command()
@click.argument("pattern")
@click.argument("test_string")
@click.option("--iterations", "-n", default=1000, help="Number of timing iterations.")
def benchmark_cmd(pattern: str, test_string: str, iterations: int):
    """Benchmark a regex pattern for performance and backtracking.

    PATTERN is the regex pattern to benchmark.
    TEST_STRING is the string to match against.
    """
    console.print(f"\n[dim]Running benchmark ({iterations} iterations)...[/dim]\n")
    result = benchmark(pattern, test_string, iterations=iterations)
    output = format_benchmark(result)
    console.print(output)


# Register 'benchmark' as the command name
benchmark_cmd.name = "benchmark"


if __name__ == "__main__":
    main()
