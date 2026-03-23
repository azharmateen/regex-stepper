"""Regex stepper engine: simulate matching step by step with backtracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .tokenizer import (
    Alternation,
    Anchor,
    Backreference,
    CharClass,
    Dot,
    Group,
    Literal,
    Node,
    Quantifier,
    Shorthand,
    tokenize,
)


class EventType(Enum):
    MATCH = "match"
    FAIL = "fail"
    BACKTRACK = "backtrack"
    TRY = "try"
    GROUP_START = "group_start"
    GROUP_END = "group_end"
    BRANCH_TRY = "branch_try"
    COMPLETE = "complete"
    NO_MATCH = "no_match"


@dataclass
class StepEvent:
    """A single step in the regex execution."""
    event_type: EventType
    pattern_pos: int          # index into the pattern string
    pattern_end: int          # end index in pattern
    string_pos: int           # current position in test string
    string_end: int           # end position in test string (for match highlight)
    node: Optional[Node]      # the AST node being processed
    description: str          # human-readable description
    groups: dict = field(default_factory=dict)  # captured groups so far


@dataclass
class StepResult:
    """Result of stepping through the whole match."""
    events: List[StepEvent]
    matched: bool
    match_start: int = 0
    match_end: int = 0
    total_backtracks: int = 0


class RegexStepper:
    """Step through regex execution, recording each decision."""

    def __init__(self, pattern: str, text: str):
        self.pattern = pattern
        self.text = text
        self.events: List[StepEvent] = []
        self.groups: dict = {}
        self.backtrack_count = 0

        # Parse into AST
        self.nodes = tokenize(pattern)

        # Also get the real match for verification
        try:
            self._real_match = re.search(pattern, text)
        except re.error:
            self._real_match = None

    def run(self) -> StepResult:
        """Execute the full step-by-step simulation."""
        self.events = []
        self.groups = {}
        self.backtrack_count = 0

        # Try matching at each position in the string
        for start_pos in range(len(self.text) + 1):
            self.groups = {}
            success, end_pos = self._match_nodes(self.nodes, start_pos)
            if success:
                self._add_event(
                    EventType.COMPLETE, 0, len(self.pattern),
                    start_pos, end_pos, None,
                    f"Match found: '{self.text[start_pos:end_pos]}' at position {start_pos}-{end_pos}"
                )
                return StepResult(
                    events=self.events,
                    matched=True,
                    match_start=start_pos,
                    match_end=end_pos,
                    total_backtracks=self.backtrack_count,
                )
            # Reset for next start position if we had events
            if start_pos < len(self.text):
                self._add_event(
                    EventType.FAIL, 0, len(self.pattern),
                    start_pos, start_pos, None,
                    f"No match starting at position {start_pos}, trying next..."
                )

        self._add_event(
            EventType.NO_MATCH, 0, len(self.pattern),
            0, 0, None,
            "No match found in the entire string"
        )
        return StepResult(
            events=self.events,
            matched=False,
            total_backtracks=self.backtrack_count,
        )

    def _add_event(self, event_type: EventType, pat_pos: int, pat_end: int,
                   str_pos: int, str_end: int, node: Optional[Node],
                   description: str):
        self.events.append(StepEvent(
            event_type=event_type,
            pattern_pos=pat_pos,
            pattern_end=pat_end,
            string_pos=str_pos,
            string_end=str_end,
            node=node,
            description=description,
            groups=dict(self.groups),
        ))

    def _match_nodes(self, nodes: List[Node], pos: int) -> Tuple[bool, int]:
        """Try to match a list of nodes starting at pos. Returns (success, end_pos)."""
        current_pos = pos

        for i, node in enumerate(nodes):
            success, new_pos = self._match_node(node, current_pos)
            if not success:
                return False, current_pos
            current_pos = new_pos

        return True, current_pos

    def _match_node(self, node: Node, pos: int) -> Tuple[bool, int]:
        """Match a single AST node at the given string position."""

        if isinstance(node, Literal):
            return self._match_literal(node, pos)
        elif isinstance(node, Dot):
            return self._match_dot(node, pos)
        elif isinstance(node, Anchor):
            return self._match_anchor(node, pos)
        elif isinstance(node, CharClass):
            return self._match_charclass(node, pos)
        elif isinstance(node, Shorthand):
            return self._match_shorthand(node, pos)
        elif isinstance(node, Quantifier):
            return self._match_quantifier(node, pos)
        elif isinstance(node, Group):
            return self._match_group(node, pos)
        elif isinstance(node, Alternation):
            return self._match_alternation(node, pos)
        elif isinstance(node, Backreference):
            return self._match_backref(node, pos)
        else:
            return False, pos

    def _match_literal(self, node: Literal, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try matching literal '{node.char}' at string position {pos}"
        )
        if pos < len(self.text) and self.text[pos] == node.char:
            self._add_event(
                EventType.MATCH, node.start, node.end, pos, pos + 1, node,
                f"Matched '{node.char}' with '{self.text[pos]}'"
            )
            return True, pos + 1
        else:
            ch = repr(self.text[pos]) if pos < len(self.text) else "END"
            self._add_event(
                EventType.FAIL, node.start, node.end, pos, pos, node,
                f"Failed: expected '{node.char}', got {ch}"
            )
            return False, pos

    def _match_dot(self, node: Dot, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try matching any character at position {pos}"
        )
        if pos < len(self.text) and self.text[pos] != "\n":
            self._add_event(
                EventType.MATCH, node.start, node.end, pos, pos + 1, node,
                f"Matched any character with '{self.text[pos]}'"
            )
            return True, pos + 1
        self._add_event(
            EventType.FAIL, node.start, node.end, pos, pos, node,
            "Failed: no character available (or newline)"
        )
        return False, pos

    def _match_anchor(self, node: Anchor, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Check anchor {node.describe()} at position {pos}"
        )

        success = False
        if node.kind == "start":
            success = (pos == 0)
        elif node.kind == "end":
            success = (pos == len(self.text))
        elif node.kind == "word_boundary":
            before = self.text[pos - 1] if pos > 0 else ""
            after = self.text[pos] if pos < len(self.text) else ""
            b_word = bool(re.match(r"\w", before)) if before else False
            a_word = bool(re.match(r"\w", after)) if after else False
            success = b_word != a_word
        elif node.kind == "non_word_boundary":
            before = self.text[pos - 1] if pos > 0 else ""
            after = self.text[pos] if pos < len(self.text) else ""
            b_word = bool(re.match(r"\w", before)) if before else False
            a_word = bool(re.match(r"\w", after)) if after else False
            success = b_word == a_word

        if success:
            self._add_event(
                EventType.MATCH, node.start, node.end, pos, pos, node,
                f"Anchor {node.describe()} satisfied"
            )
            return True, pos  # anchors don't consume characters
        else:
            self._add_event(
                EventType.FAIL, node.start, node.end, pos, pos, node,
                f"Anchor {node.describe()} not satisfied"
            )
            return False, pos

    def _char_in_class(self, ch: str, members: str, negated: bool) -> bool:
        """Check if character matches a character class."""
        i = 0
        in_class = False
        while i < len(members):
            # Handle ranges like a-z
            if i + 2 < len(members) and members[i + 1] == "-":
                if members[i] <= ch <= members[i + 2]:
                    in_class = True
                    break
                i += 3
            # Handle escaped chars
            elif members[i] == "\\" and i + 1 < len(members):
                esc = members[i + 1]
                if esc == "d" and ch.isdigit():
                    in_class = True; break
                elif esc == "D" and not ch.isdigit():
                    in_class = True; break
                elif esc == "w" and (ch.isalnum() or ch == "_"):
                    in_class = True; break
                elif esc == "W" and not (ch.isalnum() or ch == "_"):
                    in_class = True; break
                elif esc == "s" and ch in " \t\n\r\f\v":
                    in_class = True; break
                elif esc == "S" and ch not in " \t\n\r\f\v":
                    in_class = True; break
                elif ch == esc:
                    in_class = True; break
                i += 2
            else:
                if ch == members[i]:
                    in_class = True
                    break
                i += 1

        return (not in_class) if negated else in_class

    def _match_charclass(self, node: CharClass, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try matching {node.describe()} at position {pos}"
        )
        if pos < len(self.text) and self._char_in_class(self.text[pos], node.members, node.negated):
            self._add_event(
                EventType.MATCH, node.start, node.end, pos, pos + 1, node,
                f"'{self.text[pos]}' is {node.describe()}"
            )
            return True, pos + 1
        ch = repr(self.text[pos]) if pos < len(self.text) else "END"
        self._add_event(
            EventType.FAIL, node.start, node.end, pos, pos, node,
            f"{ch} is not {node.describe()}"
        )
        return False, pos

    def _match_shorthand(self, node: Shorthand, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try matching {node.describe()} at position {pos}"
        )
        if pos >= len(self.text):
            self._add_event(
                EventType.FAIL, node.start, node.end, pos, pos, node,
                f"End of string, cannot match {node.describe()}"
            )
            return False, pos

        ch = self.text[pos]
        match = False
        if node.kind == "digit":
            match = ch.isdigit()
        elif node.kind == "non_digit":
            match = not ch.isdigit()
        elif node.kind == "word":
            match = ch.isalnum() or ch == "_"
        elif node.kind == "non_word":
            match = not (ch.isalnum() or ch == "_")
        elif node.kind == "whitespace":
            match = ch in " \t\n\r\f\v"
        elif node.kind == "non_whitespace":
            match = ch not in " \t\n\r\f\v"

        if match:
            self._add_event(
                EventType.MATCH, node.start, node.end, pos, pos + 1, node,
                f"'{ch}' matches {node.describe()}"
            )
            return True, pos + 1
        self._add_event(
            EventType.FAIL, node.start, node.end, pos, pos, node,
            f"'{ch}' does not match {node.describe()}"
        )
        return False, pos

    def _match_quantifier(self, node: Quantifier, pos: int) -> Tuple[bool, int]:
        target = node.target
        if target is None:
            return False, pos

        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try quantifier {node.describe()} on {target.describe()}"
        )

        if node.greedy:
            return self._match_quantifier_greedy(node, target, pos)
        else:
            return self._match_quantifier_lazy(node, target, pos)

    def _match_quantifier_greedy(self, node: Quantifier, target: Node,
                                  pos: int) -> Tuple[bool, int]:
        """Greedy: match as many as possible, then backtrack."""
        matches: List[int] = [pos]  # positions after each match
        count = 0
        current = pos
        max_c = node.max_count if node.max_count is not None else 10000

        # Consume as many as possible
        while count < max_c:
            success, new_pos = self._match_node(target, current)
            if not success or new_pos == current:
                break
            count += 1
            current = new_pos
            matches.append(current)

        # Check minimum
        if count < node.min_count:
            self._add_event(
                EventType.FAIL, node.start, node.end, pos, current, node,
                f"Only matched {count} times, need at least {node.min_count}"
            )
            return False, pos

        # Greedy: we matched count times at position matches[count]
        self._add_event(
            EventType.MATCH, node.start, node.end, pos, matches[count], node,
            f"Greedy matched {count} time(s)"
        )
        return True, matches[count]

    def _match_quantifier_lazy(self, node: Quantifier, target: Node,
                                pos: int) -> Tuple[bool, int]:
        """Lazy: match as few as possible."""
        count = 0
        current = pos
        max_c = node.max_count if node.max_count is not None else 10000

        # Match minimum required
        while count < node.min_count:
            success, new_pos = self._match_node(target, current)
            if not success:
                self._add_event(
                    EventType.FAIL, node.start, node.end, pos, current, node,
                    f"Only matched {count}, need at least {node.min_count}"
                )
                return False, pos
            count += 1
            current = new_pos

        self._add_event(
            EventType.MATCH, node.start, node.end, pos, current, node,
            f"Lazy matched {count} time(s) (minimum)"
        )
        return True, current

    def _match_group(self, node: Group, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.GROUP_START, node.start, node.end, pos, pos, node,
            f"Enter {node.describe()}"
        )

        success, end_pos = self._match_nodes(node.children, pos)

        if success and node.capturing:
            self.groups[node.group_number] = self.text[pos:end_pos]
            self._add_event(
                EventType.GROUP_END, node.start, node.end, pos, end_pos, node,
                f"Captured group #{node.group_number}: '{self.text[pos:end_pos]}'"
            )
        elif success:
            self._add_event(
                EventType.GROUP_END, node.start, node.end, pos, end_pos, node,
                f"End {node.describe()}"
            )
        else:
            self._add_event(
                EventType.FAIL, node.start, node.end, pos, pos, node,
                f"Group failed"
            )

        return success, end_pos if success else pos

    def _match_alternation(self, node: Alternation, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try {node.describe()}"
        )

        for idx, branch in enumerate(node.branches):
            self._add_event(
                EventType.BRANCH_TRY, node.start, node.end, pos, pos, node,
                f"Try branch {idx + 1} of {len(node.branches)}"
            )
            success, end_pos = self._match_nodes(branch, pos)
            if success:
                self._add_event(
                    EventType.MATCH, node.start, node.end, pos, end_pos, node,
                    f"Branch {idx + 1} matched"
                )
                return True, end_pos
            self.backtrack_count += 1
            self._add_event(
                EventType.BACKTRACK, node.start, node.end, pos, pos, node,
                f"Branch {idx + 1} failed, backtracking"
            )

        self._add_event(
            EventType.FAIL, node.start, node.end, pos, pos, node,
            "All branches failed"
        )
        return False, pos

    def _match_backref(self, node: Backreference, pos: int) -> Tuple[bool, int]:
        self._add_event(
            EventType.TRY, node.start, node.end, pos, pos, node,
            f"Try {node.describe()}"
        )
        captured = self.groups.get(node.ref, "")
        if not captured:
            self._add_event(
                EventType.FAIL, node.start, node.end, pos, pos, node,
                f"Group #{node.ref} not captured yet"
            )
            return False, pos

        if self.text[pos:pos + len(captured)] == captured:
            self._add_event(
                EventType.MATCH, node.start, node.end, pos, pos + len(captured), node,
                f"Backreference matched '{captured}'"
            )
            return True, pos + len(captured)

        self._add_event(
            EventType.FAIL, node.start, node.end, pos, pos, node,
            f"Backreference expected '{captured}', got '{self.text[pos:pos + len(captured)]}'"
        )
        return False, pos


def step_through(pattern: str, text: str) -> StepResult:
    """Convenience function to step through a regex match."""
    stepper = RegexStepper(pattern, text)
    return stepper.run()
