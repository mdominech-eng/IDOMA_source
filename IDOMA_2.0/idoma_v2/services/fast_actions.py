"""Fast, deterministic local actions that should never call the language model."""
from __future__ import annotations

import ast
import math
import re


_ALLOWED_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_ALLOWED_UNARY = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = float(node.value)
        if not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("Numero fuori dai limiti consentiti.")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1e12):
            raise ValueError("Esponente troppo elevato.")
        result = _ALLOWED_BINARY[type(node.op)](left, right)
        if not math.isfinite(result) or abs(result) > 1e100:
            raise ValueError("Risultato fuori dai limiti consentiti.")
        return result
    raise ValueError("Espressione non consentita.")


def calculate_if_expression(message: str) -> str | None:
    """Calculate a plain arithmetic expression safely and locally; return None otherwise."""
    value = " ".join(str(message).strip().casefold().split())
    value = re.sub(r"^(?:quanto fa|calcola(?:mi)?|risolvi|esegui il calcolo di)\s*", "", value)
    value = value.strip(" =?!.")
    value = value.replace("×", "*").replace("÷", "/")
    value = re.sub(r"(?<=[0-9)])\s*[x]\s*(?=[0-9(])", "*", value)
    value = re.sub(r"\bper\b", "*", value)
    value = re.sub(r"\bdiviso(?:\s+per)?\b", "/", value)
    value = re.sub(r"\bpiu\b", "+", value)
    value = re.sub(r"\bmeno\b", "-", value)
    value = re.sub(r"(?<=\d),(?=\d)", ".", value)
    if len(value) > 120 or not re.fullmatch(r"[0-9\s.+\-*/()%]+", value):
        return None
    if not re.search(r"[+*/%]|-(?=.)", value):
        return None
    try:
        tree = ast.parse(value, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 40:
            return None
        result = _evaluate(tree)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None
    if result.is_integer():
        rendered = str(int(result))
    else:
        rendered = f"{result:.10f}".rstrip("0").rstrip(".")
    return f"Risultato: {rendered}"
