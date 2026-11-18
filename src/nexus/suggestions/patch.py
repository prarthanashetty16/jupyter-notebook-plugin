"""Minimal textual patches of a cell, by AST node position (comments and layout are kept)."""

from __future__ import annotations

import ast


def _offsets(source: str) -> list[int]:
    """Character offset of the start of each line (ast columns are UTF-8 byte offsets)."""
    out, pos = [], 0
    for line in source.splitlines(keepends=True):
        out.append(pos)
        pos += len(line)
    return out


def _char_pos(source: str, starts: list[int], lineno: int, byte_col: int) -> int:
    line = source[starts[lineno - 1] :].split("\n", 1)[0]
    return starts[lineno - 1] + len(line.encode("utf-8")[:byte_col].decode("utf-8", "ignore"))


def span(source: str, node: ast.AST) -> tuple[int, int] | None:
    if getattr(node, "end_lineno", None) is None:
        return None
    starts = _offsets(source)
    a = _char_pos(source, starts, node.lineno, node.col_offset)
    b = _char_pos(source, starts, node.end_lineno, node.end_col_offset)
    return (a, b) if a <= b else None


def replace_nodes(source: str, edits: list[tuple[ast.AST, str]]) -> str | None:
    """Replace each node's source text; None if a node has no position or edits overlap."""
    spans = []
    for node, text in edits:
        s = span(source, node)
        if s is None:
            return None
        spans.append((s[0], s[1], text))
    spans.sort()
    out, last = [], 0
    for a, b, text in spans:
        if a < last:
            return None
        out += [source[last:a], text]
        last = b
    out.append(source[last:])
    result = "".join(out)
    try:
        ast.parse(result)
    except SyntaxError:
        return None
    return result


def insert_keywords(source: str, call: ast.Call, text: str) -> str | None:
    """Append ``text`` (e.g. ``usecols=['a']``) as the last argument of ``call``."""
    s = span(source, call)
    if s is None or not source[s[0] : s[1]].endswith(")"):
        return None
    end = s[1] - 1
    inner = source[s[0] : end].rstrip()
    sep = "" if inner.endswith("(") else ", "
    result = source[: len(inner) + s[0]] + sep + text + source[end:]
    try:
        ast.parse(result)
    except SyntaxError:
        return None
    return result
