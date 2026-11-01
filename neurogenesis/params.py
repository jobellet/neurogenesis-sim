from __future__ import annotations

import ast
import operator as op
from dataclasses import dataclass
from typing import Union, List, Dict, Any, Optional
import numpy as np


@dataclass
class Const:
    value: float


@dataclass
class Gene:
    path: str
    lo: float
    hi: float
    integer: bool = False


@dataclass
class Field:
    name: str
    transform: Optional[str] = None


@dataclass
class Fit:
    target: str
    init: float
    lo: float
    hi: float


@dataclass
class Expr:
    formula: str


Param = Union[Const, Gene, Field, Fit, Expr]


def _eval_expr(expr: str) -> float:
    operators = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
        ast.Div: op.truediv, ast.Pow: op.pow, ast.BitXor: op.xor,
        ast.USub: op.neg
    }

    def eval_node(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            return operators[type(node.op)](eval_node(node.left), eval_node(node.right))
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](eval_node(node.operand))
        else:
            raise TypeError(f"Unsupported expression node: {type(node)}")
            
    return float(eval_node(ast.parse(expr, mode='eval').body))


def resolve(param: Param, genome: Dict[str, Any], fields: Dict[str, Any], positions: np.ndarray, cell_indices: Optional[np.ndarray] = None) -> Union[float, np.ndarray]:
    if isinstance(param, Const):
        return param.value
    elif isinstance(param, Gene):
        keys = param.path.split('.')
        val = genome
        for k in keys:
            val = val.get(k)
            if val is None:
                raise ValueError(f"Gene path '{param.path}' not found in genome")
        mapped = param.lo + float(val) * (param.hi - param.lo)
        if param.integer:
            return float(int(round(mapped)))
        return float(mapped)
    elif isinstance(param, Field):
        if param.name not in fields:
            raise ValueError(f"Field '{param.name}' not found")
        field_obj = fields[param.name]
        pos_to_use = positions if cell_indices is None else positions[cell_indices]
        if hasattr(field_obj, 'sample'):
            val = field_obj.sample(pos_to_use)
        elif callable(field_obj):
            val = field_obj(pos_to_use)
        else:
            raise ValueError(f"Field '{param.name}' must be callable or have a 'sample' method")
        return val
    elif isinstance(param, Fit):
        return param.init
    elif isinstance(param, Expr):
        return _eval_expr(param.formula)
    else:
        raise ValueError(f"Unknown param type: {type(param)}")


def collect_genes(stage_configs: List[Dict[str, Any]]) -> List[str]:
    genes = set()
    for config in stage_configs:
        params = config.get("params", {})
        for k, p in params.items():
            if isinstance(p, dict):
                if p.get("type") == "Gene" or "path" in p:
                    genes.add(p["path"])
            elif isinstance(p, Gene):
                genes.add(p.path)
    return sorted(list(genes))
