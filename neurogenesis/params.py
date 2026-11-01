from __future__ import annotations

import ast
import operator as op
import zlib
from dataclasses import dataclass
from typing import Union, List, Dict, Any, Optional, Tuple
import numpy as np

from neurogenesis.genome.genes import get_gene

@dataclass
class Const:
    value: Union[float, int, str, list]

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Const", "value": self.value}


@dataclass
class Gene:
    path: Union[Tuple, List, str]
    lo: float = 0.0
    hi: float = 1.0
    integer: bool = False

    def __post_init__(self):
        if isinstance(self.path, list):
            self.path = tuple(self.path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Gene",
            "path": list(self.path) if isinstance(self.path, tuple) else self.path,
            "lo": self.lo,
            "hi": self.hi,
            "integer": self.integer
        }


@dataclass
class Field:
    name: str
    transform: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": "Field", "name": self.name}
        if self.transform is not None:
            d["transform"] = self.transform
        return d


@dataclass
class Fit:
    target: str
    init: float
    lo: float
    hi: float

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Fit", "target": self.target, "init": self.init, "lo": self.lo, "hi": self.hi}


@dataclass
class Expr:
    formula: str

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Expr", "formula": self.formula}


Param = Union[Const, Gene, Field, Fit, Expr]


def param_from_dict(d: Union[Dict[str, Any], Any]) -> Param:
    """Converts a dictionary or primitive to a Param object."""
    if not isinstance(d, dict):
        return Const(d)
    
    t = d.get("type")
    if t == "Const" or "value" in d:
        return Const(d["value"])
    elif t == "Gene" or "path" in d:
        path = d["path"]
        if isinstance(path, list):
            path = tuple(path)
        return Gene(path=path, lo=float(d.get("lo", 0.0)), hi=float(d.get("hi", 1.0)), integer=bool(d.get("integer", False)))
    elif t == "Field" or ("name" in d and ("transform" in d or len(d) <= 2)):
        return Field(name=d["name"], transform=d.get("transform"))
    elif t == "Fit" or "target" in d:
        return Fit(target=d["target"], init=float(d["init"]), lo=float(d["lo"]), hi=float(d["hi"]))
    elif t == "Expr" or "formula" in d:
        return Expr(formula=d["formula"])
    else:
        # Default fallback to Const
        return Const(d)


def param_to_dict(param: Union[Param, Any]) -> Dict[str, Any]:
    if hasattr(param, "to_dict"):
        return param.to_dict()
    return {"type": "Const", "value": param}


def _eval_expr(expr: str, variables: Dict[str, Any]) -> Union[float, np.ndarray]:
    """Safe evaluation of mathematical formulas with named variables.
    
    Translates ^ to power (**) rather than bitwise XOR.
    """
    operators = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
        ast.Div: op.truediv, ast.Pow: op.pow, ast.BitXor: op.pow,  # Map ^ to pow!
        ast.USub: op.neg
    }

    def eval_node(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Variable '{node.id}' not found in formula context")
            return variables[node.id]
        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            return operators[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](eval_node(node.operand))
        else:
            raise TypeError(f"Unsupported expression node: {type(node)}")
            
    return eval_node(ast.parse(expr, mode='eval').body)


def _apply_transform(val: Union[float, np.ndarray], transform: Optional[str]) -> Union[float, np.ndarray]:
    if transform is None:
        return val
    t = transform.strip()
    if t == "abs":
        return np.abs(val)
    elif t == "sigmoid":
        return 1.0 / (1.0 + np.exp(-np.clip(val, -30.0, 30.0)))
    elif t == "tanh":
        return np.tanh(val)
    elif t == "norm":
        return np.linalg.norm(val, axis=-1)
    elif t.startswith("clip(") and t.endswith(")"):
        parts = t[5:-1].split(",")
        lo, hi = float(parts[0]), float(parts[1])
        return np.clip(val, lo, hi)
    else:
        # Safe expression on 'x'
        return _eval_expr(t, {"x": val, "np": np})


def resolve(
    param: Union[Param, Dict[str, Any], Any],
    genome: Dict[str, Any],
    fields: Dict[str, Any],
    positions: Optional[np.ndarray] = None,
    cell_indices: Optional[np.ndarray] = None,
    context_vars: Optional[Dict[str, Any]] = None
) -> Union[float, int, np.ndarray, str]:
    if isinstance(param, dict):
        param = param_from_dict(param)

    if isinstance(param, Const):
        return param.value

    elif isinstance(param, Gene):
        path = param.path
        if isinstance(path, str):
            # If path contains a dot and isn't a complex tuple path, convert to tuple
            path = tuple(path.split(".")) if "." in path else (path,)
        val = get_gene(genome, path)
        if param.integer:
            return int(round(val))
        return float(val)

    elif isinstance(param, Field):
        if param.name not in fields:
            raise ValueError(f"Field '{param.name}' not found")
        field_obj = fields[param.name]
        pos_to_use = positions
        if positions is not None and cell_indices is not None:
            pos_to_use = positions[cell_indices]
            
        if hasattr(field_obj, 'sample') and pos_to_use is not None:
            val = field_obj.sample(pos_to_use)
        elif callable(field_obj) and pos_to_use is not None:
            val = field_obj(pos_to_use)
        else:
            val = field_obj
            
        return _apply_transform(val, param.transform)

    elif isinstance(param, Fit):
        return float(param.init)

    elif isinstance(param, Expr):
        vars_dict = dict(context_vars or {})
        return _eval_expr(param.formula, vars_dict)

    else:
        return param


def collect_genes(stage_configs: List[Dict[str, Any]]) -> List[Tuple[Tuple, float, float, bool]]:
    """Extracts all genes required by stage configs as (path, lo, hi, integer) tuples."""
    genes = {}
    for config in stage_configs:
        params = config.get("params", {})
        for k, p in params.items():
            param_obj = param_from_dict(p) if isinstance(p, dict) else p
            if isinstance(param_obj, Gene):
                path = param_obj.path
                if isinstance(path, list):
                    path = tuple(path)
                elif isinstance(path, str):
                    path = tuple(path.split(".")) if "." in path else (path,)
                genes[path] = (path, float(param_obj.lo), float(param_obj.hi), bool(param_obj.integer))
                
    # Sort deterministically by str(path)
    return [genes[p] for p in sorted(genes.keys(), key=lambda x: str(x))]
