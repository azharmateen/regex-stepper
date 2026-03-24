# regex-stepper

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blue?logo=anthropic&logoColor=white)](https://claude.ai/code)


TUI debugger that lets you step through regex execution frame-by-frame. Understand exactly how your regex matches (or fails) by watching it process each character.

## Features

- **Step-by-step execution**: Watch your regex process each character with match/fail/backtrack events
- **Interactive TUI**: Navigate forward and backward through execution with arrow keys
- **Pattern explanation**: Get plain-English descriptions of what your regex does
- **Benchmarking**: Time your regex, count backtracks, detect catastrophic backtracking
- **AST tokenizer**: Full regex parser supporting literals, character classes, quantifiers, groups, alternation, anchors, and backreferences

## Installation

```bash
pip install -e .
```

## Usage

### Debug (Interactive TUI)

```bash
# Launch interactive step-through debugger
regex-stepper debug "\d+\.\d+" "Price: 42.99 dollars"

# Non-interactive mode (print all steps)
regex-stepper debug --no-tui "(a|b)+c" "aabbc"
```

**TUI Controls:**
- `Right` - Step forward
- `Left` - Step back
- `Home` - Jump to first step
- `End` - Jump to last step
- `R` - Reset
- `Q` - Quit

### Explain

```bash
regex-stepper explain "^[a-zA-Z_]\w*$"
regex-stepper explain "(\d{1,3}\.){3}\d{1,3}"
```

### Benchmark

```bash
regex-stepper benchmark "(a+)+b" "aaaaaaaaaaac"
regex-stepper benchmark "\d{3}-\d{3}-\d{4}" "555-123-4567" -n 5000
```

## How It Works

1. **Tokenizer** parses the regex into an AST (Abstract Syntax Tree)
2. **Engine** simulates the regex NFA, recording every decision: try, match, fail, backtrack
3. **TUI** lets you navigate through recorded events, highlighting the current position in both pattern and test string

## License

MIT
