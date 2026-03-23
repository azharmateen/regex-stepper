"""Plain-English regex explainer."""

from __future__ import annotations

from typing import List

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


def _describe_charclass_members(members: str) -> str:
    """Describe character class members in English."""
    parts: List[str] = []
    i = 0
    while i < len(members):
        if i + 2 < len(members) and members[i + 1] == "-":
            parts.append(f"'{members[i]}' to '{members[i + 2]}'")
            i += 3
        elif members[i] == "\\" and i + 1 < len(members):
            esc_map = {
                "d": "any digit",
                "D": "any non-digit",
                "w": "any word character",
                "W": "any non-word character",
                "s": "any whitespace",
                "S": "any non-whitespace",
                "n": "newline",
                "t": "tab",
            }
            esc = members[i + 1]
            parts.append(esc_map.get(esc, f"'{esc}'"))
            i += 2
        else:
            parts.append(f"'{members[i]}'")
            i += 1
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " or " + parts[-1]


def _explain_node(node: Node, depth: int = 0) -> List[str]:
    """Generate English explanation lines for an AST node."""
    indent = "  " * depth
    lines: List[str] = []

    if isinstance(node, Literal):
        if node.char == " ":
            lines.append(f"{indent}Match a literal space")
        elif node.char in ".^$*+?{}[]()|\\":
            lines.append(f"{indent}Match the literal character '{node.char}'")
        else:
            lines.append(f"{indent}Match the character '{node.char}'")

    elif isinstance(node, Dot):
        lines.append(f"{indent}Match any single character (except newline)")

    elif isinstance(node, Anchor):
        descriptions = {
            "start": "Assert position at the start of the string",
            "end": "Assert position at the end of the string",
            "word_boundary": "Assert position at a word boundary",
            "non_word_boundary": "Assert position NOT at a word boundary",
        }
        lines.append(f"{indent}{descriptions.get(node.kind, 'Unknown anchor')}")

    elif isinstance(node, Shorthand):
        descriptions = {
            "digit": "Match any digit [0-9]",
            "non_digit": "Match any non-digit character",
            "word": "Match any word character [a-zA-Z0-9_]",
            "non_word": "Match any non-word character",
            "whitespace": "Match any whitespace character (space, tab, newline)",
            "non_whitespace": "Match any non-whitespace character",
        }
        lines.append(f"{indent}{descriptions.get(node.kind, 'Unknown shorthand')}")

    elif isinstance(node, CharClass):
        desc = _describe_charclass_members(node.members)
        if node.negated:
            lines.append(f"{indent}Match any character NOT in: {desc}")
        else:
            lines.append(f"{indent}Match one character from: {desc}")

    elif isinstance(node, Quantifier):
        target_desc = ""
        if node.target:
            target_lines = _explain_node(node.target, 0)
            if target_lines:
                target_desc = target_lines[0].strip()

        greedy = "greedy" if node.greedy else "lazy (as few as possible)"

        if node.min_count == 0 and node.max_count is None:
            lines.append(f"{indent}{target_desc} -- repeated zero or more times ({greedy})")
        elif node.min_count == 1 and node.max_count is None:
            lines.append(f"{indent}{target_desc} -- repeated one or more times ({greedy})")
        elif node.min_count == 0 and node.max_count == 1:
            lines.append(f"{indent}{target_desc} -- optionally ({greedy})")
        elif node.max_count is None:
            lines.append(f"{indent}{target_desc} -- repeated {node.min_count} or more times ({greedy})")
        elif node.min_count == node.max_count:
            lines.append(f"{indent}{target_desc} -- repeated exactly {node.min_count} times")
        else:
            lines.append(f"{indent}{target_desc} -- repeated {node.min_count} to {node.max_count} times ({greedy})")

    elif isinstance(node, Group):
        if node.capturing:
            if node.name:
                lines.append(f"{indent}Begin named capturing group '{node.name}' (group #{node.group_number}):")
            else:
                lines.append(f"{indent}Begin capturing group #{node.group_number}:")
        else:
            lines.append(f"{indent}Begin non-capturing group:")

        for child in node.children:
            lines.extend(_explain_node(child, depth + 1))

        lines.append(f"{indent}End group")

    elif isinstance(node, Alternation):
        lines.append(f"{indent}Match one of the following alternatives:")
        for idx, branch in enumerate(node.branches):
            lines.append(f"{indent}  Alternative {idx + 1}:")
            for child in branch:
                lines.extend(_explain_node(child, depth + 2))

    elif isinstance(node, Backreference):
        lines.append(f"{indent}Match the same text as captured by group #{node.ref}")

    return lines


def explain(pattern: str) -> str:
    """Generate a plain-English explanation of a regex pattern."""
    nodes = tokenize(pattern)

    lines = [f"Pattern: /{pattern}/", ""]
    lines.append("Explanation:")
    lines.append("-" * 40)

    for node in nodes:
        lines.extend(_explain_node(node))

    lines.append("-" * 40)
    lines.append("")

    # Add summary
    lines.append(_summarize(nodes))

    return "\n".join(lines)


def _summarize(nodes: List[Node]) -> str:
    """Generate a one-line summary of what the pattern matches."""
    parts: List[str] = []

    for node in nodes:
        if isinstance(node, Anchor):
            if node.kind == "start":
                parts.append("at start of string")
            elif node.kind == "end":
                parts.append("at end of string")
        elif isinstance(node, Literal):
            parts.append(f"'{node.char}'")
        elif isinstance(node, Dot):
            parts.append("any character")
        elif isinstance(node, Shorthand):
            short_map = {
                "digit": "a digit",
                "non_digit": "a non-digit",
                "word": "a word character",
                "non_word": "a non-word character",
                "whitespace": "whitespace",
                "non_whitespace": "non-whitespace",
            }
            parts.append(short_map.get(node.kind, node.raw))
        elif isinstance(node, CharClass):
            parts.append(f"[{node.members}]")
        elif isinstance(node, Quantifier):
            if node.target:
                target_parts = []
                if isinstance(node.target, Literal):
                    target_parts.append(f"'{node.target.char}'")
                elif isinstance(node.target, Dot):
                    target_parts.append("any char")
                else:
                    target_parts.append(node.target.raw)
                if node.min_count == 0 and node.max_count is None:
                    parts.append(f"zero or more {' '.join(target_parts)}")
                elif node.min_count == 1 and node.max_count is None:
                    parts.append(f"one or more {' '.join(target_parts)}")
                elif node.min_count == 0 and node.max_count == 1:
                    parts.append(f"optional {' '.join(target_parts)}")
                else:
                    parts.append(f"{node.raw} of {' '.join(target_parts)}")
        elif isinstance(node, Group):
            parts.append(f"group({node.raw})")
        elif isinstance(node, Alternation):
            branch_parts = [b[0].raw if b else "empty" for b in node.branches]
            parts.append(" or ".join(branch_parts))

    if parts:
        return "Summary: Match " + ", then ".join(parts)
    return "Summary: Empty pattern (matches everything)"
