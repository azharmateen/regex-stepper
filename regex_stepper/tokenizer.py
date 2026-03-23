"""Regex tokenizer: parse regex pattern into AST nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """Base AST node for a regex token."""
    start: int  # position in original pattern
    end: int    # position end (exclusive)
    raw: str    # raw text from pattern

    def describe(self) -> str:
        return self.raw


@dataclass
class Literal(Node):
    char: str = ""

    def describe(self) -> str:
        if self.char == " ":
            return "literal space"
        return f"literal '{self.char}'"


@dataclass
class Dot(Node):
    def describe(self) -> str:
        return "any character (.)"


@dataclass
class Anchor(Node):
    kind: str = ""  # "start", "end", "word_boundary", "non_word_boundary"

    def describe(self) -> str:
        labels = {
            "start": "start of string (^)",
            "end": "end of string ($)",
            "word_boundary": "word boundary (\\b)",
            "non_word_boundary": "non-word boundary (\\B)",
        }
        return labels.get(self.kind, f"anchor {self.raw}")


@dataclass
class CharClass(Node):
    negated: bool = False
    members: str = ""  # simplified: the content inside []

    def describe(self) -> str:
        neg = "not in" if self.negated else "one of"
        return f"{neg} [{self.members}]"


@dataclass
class Shorthand(Node):
    """Shorthand character class like \\d, \\w, \\s and their negations."""
    kind: str = ""  # "digit", "non_digit", "word", "non_word", "whitespace", "non_whitespace"

    def describe(self) -> str:
        labels = {
            "digit": "digit (\\d)",
            "non_digit": "non-digit (\\D)",
            "word": "word char (\\w)",
            "non_word": "non-word char (\\W)",
            "whitespace": "whitespace (\\s)",
            "non_whitespace": "non-whitespace (\\S)",
        }
        return labels.get(self.kind, f"shorthand {self.raw}")


@dataclass
class Quantifier(Node):
    greedy: bool = True
    min_count: int = 0
    max_count: Optional[int] = None  # None = unlimited
    target: Optional[Node] = None

    def describe(self) -> str:
        g = "" if self.greedy else " (lazy)"
        if self.min_count == 0 and self.max_count is None:
            return f"zero or more{g} ({self.raw})"
        elif self.min_count == 1 and self.max_count is None:
            return f"one or more{g} ({self.raw})"
        elif self.min_count == 0 and self.max_count == 1:
            return f"optional{g} ({self.raw})"
        elif self.max_count is None:
            return f"{self.min_count} or more{g}"
        elif self.min_count == self.max_count:
            return f"exactly {self.min_count}{g}"
        else:
            return f"{self.min_count} to {self.max_count}{g}"


@dataclass
class Group(Node):
    capturing: bool = True
    group_number: int = 0
    children: List[Node] = field(default_factory=list)
    name: Optional[str] = None

    def describe(self) -> str:
        if self.capturing:
            if self.name:
                return f"named group '{self.name}' (#{self.group_number})"
            return f"capturing group #{self.group_number}"
        return "non-capturing group"


@dataclass
class Alternation(Node):
    branches: List[List[Node]] = field(default_factory=list)

    def describe(self) -> str:
        return f"alternation ({len(self.branches)} branches)"


@dataclass
class Backreference(Node):
    ref: int = 0

    def describe(self) -> str:
        return f"backreference to group #{self.ref}"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class RegexTokenizer:
    """Parse a regex pattern string into a list of AST nodes."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.pos = 0
        self.group_counter = 0

    def tokenize(self) -> List[Node]:
        """Return flat-ish list of AST nodes for the pattern."""
        nodes = self._parse_sequence()
        return nodes

    # -- internal -----------------------------------------------------------

    def _peek(self) -> Optional[str]:
        if self.pos < len(self.pattern):
            return self.pattern[self.pos]
        return None

    def _advance(self) -> str:
        ch = self.pattern[self.pos]
        self.pos += 1
        return ch

    def _parse_sequence(self, stop_chars: str = "") -> List[Node]:
        """Parse a sequence of tokens until EOF or a stop character."""
        nodes: List[Node] = []
        while self.pos < len(self.pattern):
            ch = self._peek()
            if ch in stop_chars:
                break
            node = self._parse_atom()
            if node is None:
                break
            # Check for alternation
            if self._peek() == "|":
                alt_start = node.start
                branches: List[List[Node]] = [nodes + [node]]
                while self._peek() == "|":
                    self._advance()  # consume |
                    branch_nodes = self._parse_branch(stop_chars)
                    branches.append(branch_nodes)
                alt_raw = self.pattern[alt_start:self.pos]
                return [Alternation(start=alt_start, end=self.pos, raw=alt_raw, branches=branches)]

            # Check for quantifier
            node = self._maybe_quantifier(node)
            nodes.append(node)
        return nodes

    def _parse_branch(self, stop_chars: str = "") -> List[Node]:
        """Parse one branch of an alternation."""
        nodes: List[Node] = []
        while self.pos < len(self.pattern):
            ch = self._peek()
            if ch in stop_chars or ch == "|":
                break
            node = self._parse_atom()
            if node is None:
                break
            node = self._maybe_quantifier(node)
            nodes.append(node)
        return nodes

    def _parse_atom(self) -> Optional[Node]:
        """Parse a single atom (literal, group, char class, anchor, etc.)."""
        if self.pos >= len(self.pattern):
            return None

        start = self.pos
        ch = self._advance()

        # Escaped characters
        if ch == "\\":
            return self._parse_escape(start)

        # Character class
        if ch == "[":
            return self._parse_char_class(start)

        # Group
        if ch == "(":
            return self._parse_group(start)

        # Anchors
        if ch == "^":
            return Anchor(start=start, end=self.pos, raw="^", kind="start")
        if ch == "$":
            return Anchor(start=start, end=self.pos, raw="$", kind="end")

        # Dot
        if ch == ".":
            return Dot(start=start, end=self.pos, raw=".")

        # Literal
        return Literal(start=start, end=self.pos, raw=ch, char=ch)

    def _parse_escape(self, start: int) -> Node:
        """Parse an escaped sequence starting after the backslash."""
        if self.pos >= len(self.pattern):
            return Literal(start=start, end=self.pos, raw="\\", char="\\")

        ch = self._advance()
        raw = f"\\{ch}"

        shorthand_map = {
            "d": "digit", "D": "non_digit",
            "w": "word", "W": "non_word",
            "s": "whitespace", "S": "non_whitespace",
        }
        if ch in shorthand_map:
            return Shorthand(start=start, end=self.pos, raw=raw, kind=shorthand_map[ch])

        if ch == "b":
            return Anchor(start=start, end=self.pos, raw=raw, kind="word_boundary")
        if ch == "B":
            return Anchor(start=start, end=self.pos, raw=raw, kind="non_word_boundary")

        # Backreference \1-\9
        if ch.isdigit() and ch != "0":
            return Backreference(start=start, end=self.pos, raw=raw, ref=int(ch))

        # Escaped literal (e.g. \. \* \+ etc.)
        return Literal(start=start, end=self.pos, raw=raw, char=ch)

    def _parse_char_class(self, start: int) -> Node:
        """Parse a character class [...] starting after the '['."""
        negated = False
        if self._peek() == "^":
            negated = True
            self._advance()

        members = ""
        # First char can be ] without closing
        if self._peek() == "]":
            members += self._advance()

        while self.pos < len(self.pattern) and self._peek() != "]":
            ch = self._advance()
            if ch == "\\" and self.pos < len(self.pattern):
                members += ch + self._advance()
            else:
                members += ch

        if self._peek() == "]":
            self._advance()

        raw = self.pattern[start:self.pos]
        return CharClass(start=start, end=self.pos, raw=raw, negated=negated, members=members)

    def _parse_group(self, start: int) -> Node:
        """Parse a group (...) starting after the '('."""
        capturing = True
        name = None

        # Check for non-capturing or named group
        if self._peek() == "?":
            self._advance()
            next_ch = self._peek()
            if next_ch == ":":
                capturing = False
                self._advance()
            elif next_ch == "P" or next_ch == "<":
                # Named group (?P<name>...) or (?<name>...)
                capturing = True
                if next_ch == "P":
                    self._advance()  # skip P
                    self._advance()  # skip <
                else:
                    self._advance()  # skip <
                name_chars = ""
                while self.pos < len(self.pattern) and self._peek() != ">":
                    name_chars += self._advance()
                if self._peek() == ">":
                    self._advance()
                name = name_chars
            else:
                # Other group modifiers - treat as non-capturing
                capturing = False

        group_number = 0
        if capturing:
            self.group_counter += 1
            group_number = self.group_counter

        children = self._parse_sequence(stop_chars=")")

        if self._peek() == ")":
            self._advance()

        raw = self.pattern[start:self.pos]
        return Group(
            start=start, end=self.pos, raw=raw,
            capturing=capturing, group_number=group_number,
            children=children, name=name,
        )

    def _maybe_quantifier(self, node: Node) -> Node:
        """If the next char is a quantifier, wrap the node."""
        if self.pos >= len(self.pattern):
            return node

        start = self.pos
        ch = self._peek()
        min_c, max_c = 0, 0

        if ch == "*":
            self._advance()
            min_c, max_c = 0, None
        elif ch == "+":
            self._advance()
            min_c, max_c = 1, None
        elif ch == "?":
            self._advance()
            min_c, max_c = 0, 1
        elif ch == "{":
            result = self._parse_brace_quantifier(start)
            if result is None:
                return node
            min_c, max_c = result
        else:
            return node

        greedy = True
        if self._peek() == "?":
            greedy = False
            self._advance()

        raw = self.pattern[start:self.pos]
        return Quantifier(
            start=start, end=self.pos, raw=raw,
            greedy=greedy, min_count=min_c, max_count=max_c,
            target=node,
        )

    def _parse_brace_quantifier(self, start: int) -> Optional[tuple]:
        """Parse {n}, {n,}, {n,m}. Returns (min, max) or None if invalid."""
        saved = self.pos
        self._advance()  # skip {

        num_str = ""
        while self.pos < len(self.pattern) and self._peek().isdigit():
            num_str += self._advance()

        if not num_str:
            self.pos = saved
            return None

        min_c = int(num_str)
        max_c = min_c

        if self._peek() == ",":
            self._advance()
            num2 = ""
            while self.pos < len(self.pattern) and self._peek().isdigit():
                num2 += self._advance()
            max_c = int(num2) if num2 else None

        if self._peek() == "}":
            self._advance()
            return (min_c, max_c)

        self.pos = saved
        return None


def tokenize(pattern: str) -> List[Node]:
    """Convenience function to tokenize a regex pattern."""
    return RegexTokenizer(pattern).tokenize()


def flatten_nodes(nodes: List[Node]) -> List[Node]:
    """Recursively flatten groups and alternations for step-by-step display."""
    result: List[Node] = []
    for node in nodes:
        if isinstance(node, Group):
            result.append(node)
            result.extend(flatten_nodes(node.children))
        elif isinstance(node, Alternation):
            result.append(node)
            for branch in node.branches:
                result.extend(flatten_nodes(branch))
        elif isinstance(node, Quantifier) and node.target:
            result.append(node.target)
            result.append(node)
        else:
            result.append(node)
    return result
