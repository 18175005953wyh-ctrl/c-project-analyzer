"""Classify physical lines using a small comment/string state machine."""

import re


def count_text(text):
    """Code wins over comments; whitespace-only physical lines are blank."""
    counts = {
        "total_lines": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "blank_lines": 0,
        "todo_count": len(re.findall(r"\bTODO\b", text)),
        "fixme_count": len(re.findall(r"\bFIXME\b", text)),
    }
    in_block = False
    quote = None
    # Only CR/LF are line separators; a final newline creates no extra line.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n") if normalized else []
    if lines and lines[-1] == "":
        lines.pop()

    for line in lines:
        counts["total_lines"] += 1
        if not line.strip():
            counts["blank_lines"] += 1
            continue

        has_code = False
        has_comment = False
        index = 0
        continued_quote = False
        while index < len(line):
            char = line[index]
            pair = line[index:index + 2]
            if in_block:
                has_comment = True
                if pair == "*/":
                    in_block = False
                    index += 2
                else:
                    index += 1
            elif quote is not None:
                has_code = True
                if char == "\\":
                    continued_quote = index == len(line) - 1
                    index += 2
                elif char == quote:
                    quote = None
                    index += 1
                else:
                    index += 1
            elif pair == "//":
                has_comment = True
                break
            elif pair == "/*":
                has_comment = True
                in_block = True
                index += 2
            elif char in ('"', "'"):
                quote = char
                has_code = True
                index += 1
            else:
                if not char.isspace():
                    has_code = True
                index += 1

        # Recover from an invalid unterminated literal instead of hiding later comments.
        if not continued_quote:
            quote = None
        if has_code:
            counts["code_lines"] += 1
        elif has_comment:
            counts["comment_lines"] += 1
        else:
            counts["blank_lines"] += 1
    return counts
