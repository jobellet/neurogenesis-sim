"""Restricted safe mathematical and logical expression evaluator.

Provides AST whitelist evaluation of formulas, expressions, and conditions
without allowing arbitrary code execution (no eval, no exec, no dunder attribute
traversal, no unrestricted imports or globals).
"""
import ast
import operator as op
from typing import Any, Dict, Optional, Union, Callable
import numpy as np


# Whitelisted binary operators
_BIN_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.BitXor: op.pow,  # Map ^ to pow (standard mathematical notation in formula strings)
    ast.BitAnd: op.and_,
    ast.BitOr: op.or_,
}

# Whitelisted unary operators
_UNARY_OPS = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
    ast.Invert: op.invert,
}

# Whitelisted comparison operators
_COMP_OPS = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
}

# Standard mathematical built-in functions
_DEFAULT_FUNCS: Dict[str, Callable] = {
    "exp": np.exp,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "sqrt": np.sqrt,
    "log": np.log,
    "log10": np.log10,
    "log2": np.log2,
    "abs": np.abs,
    "clip": np.clip,
    "tanh": np.tanh,
    "maximum": np.maximum,
    "minimum": np.minimum,
    "sigmoid": lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0))),
    "norm": lambda x: np.linalg.norm(x, axis=-1),
}

# Standard mathematical constants
_DEFAULT_CONSTANTS: Dict[str, Any] = {
    "pi": np.pi,
    "e": np.e,
    "True": True,
    "False": False,
    "None": None,
}

_ALLOWED_NUMPY_ATTRS = {
    "exp", "sin", "cos", "tan", "sqrt", "log", "log10", "log2",
    "abs", "clip", "tanh", "maximum", "minimum", "pi", "e",
    "linalg", "norm"
}


def eval_expr(expr: str, variables: Optional[Dict[str, Any]] = None) -> Any:
    """Evaluates a formula or condition string using an AST whitelist.

    Supports:
    - Arithmetic: +, -, *, /, //, %, ** (and ^ mapped to power)
    - Unary ops: +, -, ~, not
    - Comparisons: ==, !=, <, <=, >, >=
    - Logical operators: and, or, & , |
    - Subscripting: expr[k], pos[:, 0]
    - Calls to whitelisted math ufuncs (exp, sin, cos, sqrt, abs, clip, tanh, etc.)
    - Named variables passed in `variables`.

    Raises:
    - SyntaxError on invalid syntax.
    - TypeError on disallowed AST nodes or invalid types.
    - ValueError on unknown variables or disallowed attribute lookups.
    """
    if not isinstance(expr, str):
        raise TypeError(f"Expression must be a string, got {type(expr).__name__}")
    
    expr = expr.strip()
    if not expr:
        raise ValueError("Expression string is empty")

    # Replace ^ with ** so mathematical expressions have standard power precedence
    # rather than bitwise XOR precedence
    if "^" in expr:
        expr = expr.replace("^", "**")

    ctx = dict(_DEFAULT_CONSTANTS)
    ctx.update(_DEFAULT_FUNCS)
    if variables:
        ctx.update(variables)

    parsed = ast.parse(expr, mode="eval")
    return _eval_node(parsed.body, ctx)


def _eval_node(node: ast.AST, ctx: Dict[str, Any]) -> Any:
    # 1. Constants and literals
    if isinstance(node, ast.Constant):
        return node.value

    # 2. Named identifiers
    if isinstance(node, ast.Name):
        if node.id in ctx:
            return ctx[node.id]
        raise ValueError(f"Variable or function '{node.id}' not found in expression context")

    # 3. Unary operations
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, ctx)
        op_type = type(node.op)
        if op_type is ast.Not:
            # Handle array negation elementwise
            if isinstance(operand, np.ndarray):
                return ~operand.astype(bool)
            return not operand
        if op_type in _UNARY_OPS:
            return _UNARY_OPS[op_type](operand)
        raise TypeError(f"Disallowed unary operator: {op_type.__name__}")

    # 4. Binary operations (+, -, *, /, **, ^, &, |, etc.)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        op_type = type(node.op)
        if op_type in _BIN_OPS:
            return _BIN_OPS[op_type](left, right)
        raise TypeError(f"Disallowed binary operator: {op_type.__name__}")

    # 5. Comparisons (==, !=, <, <=, >, >=)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        result = None
        current_left = left
        for cmp_op, comp_node in zip(node.ops, node.comparators):
            comp_type = type(cmp_op)
            if comp_type not in _COMP_OPS:
                raise TypeError(f"Disallowed comparison operator: {comp_type.__name__}")
            current_right = _eval_node(comp_node, ctx)
            cmp_result = _COMP_OPS[comp_type](current_left, current_right)
            if result is None:
                result = cmp_result
            else:
                # Combine chained comparisons (e.g. 0 < x < 10)
                if isinstance(result, np.ndarray) or isinstance(cmp_result, np.ndarray):
                    result = result & cmp_result
                else:
                    result = result and cmp_result
            current_left = current_right
        return result

    # 6. Boolean operations (and, or)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            vals = [_eval_node(val_node, ctx) for val_node in node.values]
            res = vals[0]
            for v in vals[1:]:
                if isinstance(res, np.ndarray) or isinstance(v, np.ndarray):
                    res = res & np.asarray(v, dtype=bool)
                else:
                    res = res and v
            return res
        elif isinstance(node.op, ast.Or):
            vals = [_eval_node(val_node, ctx) for val_node in node.values]
            res = vals[0]
            for v in vals[1:]:
                if isinstance(res, np.ndarray) or isinstance(v, np.ndarray):
                    res = res | np.asarray(v, dtype=bool)
                else:
                    res = res or v
            return res
        raise TypeError(f"Disallowed boolean operator: {type(node.op).__name__}")

    # 7. Function calls
    if isinstance(node, ast.Call):
        func = _eval_node(node.func, ctx)
        if not callable(func):
            raise TypeError(f"Object {func!r} is not callable")
        args = [_eval_node(arg, ctx) for arg in node.args]
        kwargs = {kw.arg: _eval_node(kw.value, ctx) for kw in node.keywords}
        return func(*args, **kwargs)

    # 8. Attribute access (strictly restricted to numpy ufuncs / safe modules)
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise ValueError(f"Access to private/dunder attribute '{node.attr}' is prohibited")
        val = _eval_node(node.value, ctx)
        if val is np or val is np.linalg:
            if node.attr in _ALLOWED_NUMPY_ATTRS:
                return getattr(val, node.attr)
            raise ValueError(f"Attribute '{node.attr}' is not an allowed numpy function")
        raise TypeError(f"Attribute access on {type(val).__name__} is not allowed")

    # 9. Subscripting and slicing (e.g. expr[0], pos[:, 1])
    if isinstance(node, ast.Subscript):
        val = _eval_node(node.value, ctx)
        slice_idx = _eval_slice(node.slice, ctx)
        return val[slice_idx]

    # 10. Tuples (used in multi-dimensional indexing, e.g. [:, 0])
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, ctx) for elt in node.elts)

    # 11. Slices (e.g. ':' in multi-dimensional subscripting)
    if isinstance(node, ast.Slice):
        lower = _eval_node(node.lower, ctx) if node.lower is not None else None
        upper = _eval_node(node.upper, ctx) if node.upper is not None else None
        step = _eval_node(node.step, ctx) if node.step is not None else None
        return slice(lower, upper, step)

    raise TypeError(f"Disallowed expression syntax: {type(node).__name__}")


def _eval_slice(slice_node: ast.AST, ctx: Dict[str, Any]) -> Any:
    """Evaluates slice nodes for subscripting."""
    if isinstance(slice_node, ast.Slice):
        lower = _eval_node(slice_node.lower, ctx) if slice_node.lower is not None else None
        upper = _eval_node(slice_node.upper, ctx) if slice_node.upper is not None else None
        step = _eval_node(slice_node.step, ctx) if slice_node.step is not None else None
        return slice(lower, upper, step)
    return _eval_node(slice_node, ctx)
