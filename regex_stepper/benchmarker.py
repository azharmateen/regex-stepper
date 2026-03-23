"""Benchmark regex execution: timing, backtrack counting, catastrophic detection."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import List, Optional

from .engine import RegexStepper


@dataclass
class BenchmarkResult:
    """Result of benchmarking a regex pattern."""
    pattern: str
    test_string: str
    matched: bool
    match_text: Optional[str]
    python_time_ms: float
    stepper_time_ms: float
    total_steps: int
    total_backtracks: int
    catastrophic: bool
    warnings: List[str]


def benchmark(pattern: str, test_string: str, iterations: int = 1000) -> BenchmarkResult:
    """Benchmark a regex pattern against a test string.

    Runs the Python regex engine for timing and the stepper engine
    for backtrack analysis.

    Args:
        pattern: Regex pattern to benchmark.
        test_string: String to match against.
        iterations: Number of iterations for timing.

    Returns:
        BenchmarkResult with timing and analysis data.
    """
    warnings: List[str] = []

    # --- Python regex timing ---
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return BenchmarkResult(
            pattern=pattern,
            test_string=test_string,
            matched=False,
            match_text=None,
            python_time_ms=0.0,
            stepper_time_ms=0.0,
            total_steps=0,
            total_backtracks=0,
            catastrophic=False,
            warnings=[f"Invalid regex: {e}"],
        )

    # Warm up
    compiled.search(test_string)

    start = time.perf_counter()
    for _ in range(iterations):
        m = compiled.search(test_string)
    elapsed = time.perf_counter() - start
    python_time_ms = (elapsed / iterations) * 1000

    matched = m is not None
    match_text = m.group(0) if m else None

    # --- Stepper engine analysis ---
    stepper_start = time.perf_counter()
    stepper = RegexStepper(pattern, test_string)
    result = stepper.run()
    stepper_elapsed = time.perf_counter() - stepper_start
    stepper_time_ms = stepper_elapsed * 1000

    total_steps = len(result.events)
    total_backtracks = result.total_backtracks

    # --- Catastrophic backtracking detection ---
    catastrophic = False

    if total_backtracks > 1000:
        catastrophic = True
        warnings.append(
            f"CATASTROPHIC BACKTRACKING: {total_backtracks} backtracks detected! "
            "This pattern may hang on longer inputs."
        )
    elif total_backtracks > 100:
        warnings.append(
            f"HIGH BACKTRACKING: {total_backtracks} backtracks. "
            "Consider optimizing the pattern."
        )

    # Check for known dangerous patterns
    danger_patterns = _detect_dangerous_patterns(pattern)
    warnings.extend(danger_patterns)

    # Timing warnings
    if python_time_ms > 1.0:
        warnings.append(
            f"SLOW: Average match time is {python_time_ms:.3f}ms. "
            "Consider simplifying the pattern."
        )

    if python_time_ms > 10.0:
        catastrophic = True
        warnings.append(
            "EXTREMELY SLOW: Pattern takes >10ms per match. "
            "Likely catastrophic backtracking."
        )

    # Stepper step count analysis
    string_len = len(test_string) + 1
    if total_steps > string_len * 50:
        warnings.append(
            f"Excessive steps: {total_steps} steps for a {len(test_string)}-char string. "
            f"Ratio: {total_steps / max(string_len, 1):.0f}x string length."
        )

    return BenchmarkResult(
        pattern=pattern,
        test_string=test_string,
        matched=matched,
        match_text=match_text,
        python_time_ms=python_time_ms,
        stepper_time_ms=stepper_time_ms,
        total_steps=total_steps,
        total_backtracks=total_backtracks,
        catastrophic=catastrophic,
        warnings=warnings,
    )


def _detect_dangerous_patterns(pattern: str) -> List[str]:
    """Detect regex anti-patterns that may cause catastrophic backtracking."""
    warnings: List[str] = []

    # Nested quantifiers: (a+)+ or (a*)*
    if re.search(r"\([^)]*[+*][^)]*\)[+*]", pattern):
        warnings.append(
            "DANGER: Nested quantifiers detected (e.g., (a+)+). "
            "This is a common cause of catastrophic backtracking."
        )

    # Overlapping alternatives with quantifiers: (a|a)+
    if re.search(r"\([^)]*\|[^)]*\)[+*]", pattern):
        warnings.append(
            "WARNING: Alternation inside quantifier. "
            "If alternatives overlap, this can cause exponential backtracking."
        )

    # .* or .+ repeated multiple times
    dot_stars = re.findall(r"\.\*|\.\+", pattern)
    if len(dot_stars) >= 2:
        warnings.append(
            f"WARNING: Multiple greedy dot-star/dot-plus ({len(dot_stars)} found). "
            "Adjacent .* patterns compete for characters, causing backtracking."
        )

    # Repeated optional groups: (a?a?a?...)aaa
    if re.search(r"\?\w\?", pattern) and re.search(r"[+*]", pattern):
        warnings.append(
            "WARNING: Mixed optional and required patterns. "
            "May cause combinatorial explosion."
        )

    return warnings


def format_benchmark(result: BenchmarkResult) -> str:
    """Format a benchmark result as a human-readable string."""
    lines = [
        "=" * 60,
        "  REGEX BENCHMARK RESULTS",
        "=" * 60,
        f"  Pattern:  /{result.pattern}/",
        f"  String:   \"{result.test_string}\"",
        f"  Matched:  {'Yes' if result.matched else 'No'}",
    ]

    if result.match_text is not None:
        lines.append(f"  Match:    \"{result.match_text}\"")

    lines.extend([
        "",
        "  Timing:",
        f"    Python re:    {result.python_time_ms:.4f} ms/match",
        f"    Stepper sim:  {result.stepper_time_ms:.2f} ms",
        "",
        "  Complexity:",
        f"    Total steps:      {result.total_steps}",
        f"    Total backtracks: {result.total_backtracks}",
        f"    Catastrophic:     {'YES' if result.catastrophic else 'No'}",
    ])

    if result.warnings:
        lines.extend(["", "  Warnings:"])
        for w in result.warnings:
            lines.append(f"    ! {w}")

    lines.append("=" * 60)
    return "\n".join(lines)
