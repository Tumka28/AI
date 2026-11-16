"""Native tools: plain Python functions, the fastest kind of tool."""

from __future__ import annotations

import ast
import datetime as dt
import math
import operator
from typing import Any, Dict

from bot_v.tools.registry import Tool, ToolRegistry

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
    "log10": math.log10, "exp": math.exp, "abs": abs, "round": round, "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic without eval(): numbers, + - * / // % **, a few math functions."""
    if len(expression) > 200:
        raise ValueError("expression is too long")

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
                raise ValueError("exponent too large")
            return _BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _FUNCS and not node.keywords):
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError(f"not allowed in a calculation: {ast.dump(node)[:60]}")

    return ev(ast.parse(expression.replace("^", "**"), mode="eval"))


def _calculate(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"expression": args["expression"], "value": safe_eval(args["expression"])}


def _now(args: Dict[str, Any]) -> Dict[str, Any]:
    now = dt.datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M"),
        "weekday": now.strftime("%A"),
        "timezone": now.tzname(),
    }


def register_native_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="calculate",
        description="Evaluate an arithmetic expression exactly, e.g. '(12.5*4)/3' or 'sqrt(2)'.",
        input_schema={"type": "object", "properties": {"expression": {"type": "string"}},
                      "required": ["expression"], "additionalProperties": False},
        handler=_calculate,
        keywords=("calculate", "тооцоол", "тооцоо"),
    ))
    registry.register(Tool(
        name="now",
        description="Current local date, time, weekday and timezone.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_now,
        keywords=("what time", "today's date", "хэдэн цаг", "өнөөдөр хэдэн", "огноо"),
    ))
