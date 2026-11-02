from __future__ import annotations

from dataclasses import dataclass
from typing import Union, List, Dict, Any, Optional, Tuple
import numpy as np

from neurogenesis.genome.genes import get_gene
from neurogenesis.expressions import eval_expr

def _clean_json_value(val: Any) -> Any:
    """Recursively converts tuple dictionary keys into 'src->dst' strings for JSON compatibility."""
    if isinstance(val, dict):
        return {
            ("->".join(map(str, k)) if isinstance(k, tuple) else (str(k) if not isinstance(k, str) else k)): _clean_json_value(v)
            for k, v in val.items()
        }
    if isinstance(val, (list, tuple)):
        return [_clean_json_value(x) for x in val]
    if isinstance(val, np.ndarray):
        return val.tolist()
    if isinstance(val, (np.integer, np.floating)):
        return val.item()
    return val


@dataclass
class Const:
    value: Union[float, int, str, list, dict]

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Const", "value": _clean_json_value(self.value)}


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

# Genome key holding fitted values of Fit params, {target: value}; absent = every Fit resolves to its init.
FIT_KEY = "__fit__"


# Keys of each Param source: (needed with an explicit "type", needed to read an untyped dict as this source, allowed).
_PARAM_KEYS = {
    "Const": ({"value"}, {"value"}, {"value"}),
    "Gene": ({"path"}, {"path", "lo", "hi"}, {"path", "lo", "hi", "integer"}),
    "Field": ({"name"}, {"name", "transform"}, {"name", "transform"}),
    "Fit": ({"target", "init", "lo", "hi"}, {"target", "init", "lo", "hi"}, {"target", "init", "lo", "hi"}),
    "Expr": ({"formula"}, {"formula"}, {"formula"}),
}


def _param_type(d: Dict[str, Any]) -> Optional[str]:
    """The Param source a dict describes: its "type" if that names a source, else the source whose key set the dict
    matches exactly (optional keys aside), else None (a plain value)."""
    if "type" in d:
        return d["type"] if isinstance(d["type"], str) and d["type"] in _PARAM_KEYS else None
    keys = set(d)
    for name, (_, needed, allowed) in _PARAM_KEYS.items():
        if needed <= keys <= allowed:
            return name
    return None


def param_from_dict(d: Union[Dict[str, Any], Any]) -> Param:
    """Converts a dictionary or primitive to a Param object.

    A dict is a Param source when its "type" is one of Const, Gene, Field, Fit, Expr, or, without "type", when its keys
    are exactly those of one source: {"value"}, {"path", "lo", "hi"[, "integer"]}, {"name", "transform"},
    {"target", "init", "lo", "hi"} or {"formula"}. Any other dict (e.g. a guidance dict with a "target" key) is a plain
    value, Const(d).
    """
    if not isinstance(d, dict):
        return Const(d)
    t = _param_type(d)
    if t is None:
        return Const(d)
    missing = _PARAM_KEYS[t][0] - set(d)
    if missing:
        raise ValueError(f"{t} param {d!r} is missing {sorted(missing)}")
    if t == "Const":
        return Const(d["value"])
    if t == "Gene":
        path = d["path"]
        if isinstance(path, list):
            path = tuple(path)
        return Gene(path=path, lo=float(d.get("lo", 0.0)), hi=float(d.get("hi", 1.0)), integer=bool(d.get("integer", False)))
    if t == "Field":
        return Field(name=d["name"], transform=d.get("transform"))
    if t == "Fit":
        return Fit(target=d["target"], init=float(d["init"]), lo=float(d["lo"]), hi=float(d["hi"]))
    return Expr(formula=d["formula"])


def worst_case(param: Any, default: Any) -> Any:
    """Value of a Param for cost estimates (declared before the genome is known).

    A Const gives its value, a Gene or Fit its upper bound `hi`, a Field or Expr (or None) gives `default`; a dict is
    read with `param_from_dict` first, and any other value is returned as is.
    """
    if isinstance(param, dict):
        param = param_from_dict(param)
    if isinstance(param, Const):
        return param.value
    if isinstance(param, (Gene, Fit)):
        return param.hi
    if param is None or isinstance(param, Param.__args__):
        return default
    return param


def param_to_dict(param: Union[Param, Any]) -> Dict[str, Any]:
    if hasattr(param, "to_dict"):
        return param.to_dict()
    return {"type": "Const", "value": _clean_json_value(param)}


def _eval_expr(expr: str, variables: Dict[str, Any]) -> Union[float, np.ndarray]:
    """Safe evaluation of mathematical formulas with named variables.
    
    Translates ^ to power (**) rather than bitwise XOR.
    """
    return eval_expr(expr, variables)


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
            
        if hasattr(field_obj, 'values') and pos_to_use is not None:
            val = field_obj.values(pos_to_use)
        elif hasattr(field_obj, 'sample') and pos_to_use is not None:
            val = field_obj.sample(pos_to_use)
        elif callable(field_obj) and pos_to_use is not None:
            val = field_obj(pos_to_use)
        else:
            val = field_obj
            
        return _apply_transform(val, param.transform)

    elif isinstance(param, Fit):
        # Fitted values live in the genome under FIT_KEY, keyed by the Fit's target name (neurogenesis.fitting)
        fitted = genome.get(FIT_KEY) if isinstance(genome, dict) else None
        if isinstance(fitted, dict) and param.target in fitted:
            return float(np.clip(float(fitted[param.target]), param.lo, param.hi))
        return float(param.init)

    elif isinstance(param, Expr):
        vars_dict = dict(context_vars or {})
        return _eval_expr(param.formula, vars_dict)

    else:
        return param


def _gene_path(path: Union[Tuple, List, str]) -> Tuple:
    if isinstance(path, (list, tuple)):
        return tuple(path)
    return tuple(path.split(".")) if "." in path else (path,)


def _walk_genes(value: Any, genes: Dict[Tuple, Tuple[Tuple, float, float, bool]]) -> None:
    """Adds every Gene inside a param value (nested dicts, lists and Const values included) to ``genes`` by path."""
    if isinstance(value, dict):
        param = param_from_dict(value)
        if isinstance(param, Const) and param.value is value:  # a plain dict: walk its values
            for v in value.values():
                _walk_genes(v, genes)
            return
        value = param
    if isinstance(value, Gene):
        path = _gene_path(value.path)
        genes.setdefault(path, (path, float(value.lo), float(value.hi), bool(value.integer)))
    elif isinstance(value, Const):
        _walk_genes(value.value, genes)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk_genes(v, genes)


def _sorted_genes(genes: Dict[Tuple, Tuple[Tuple, float, float, bool]]) -> List[Tuple[Tuple, float, float, bool]]:
    return [genes[p] for p in sorted(genes, key=str)]


def collect_genes(stage_configs: List[Dict[str, Any]]) -> List[Tuple[Tuple, float, float, bool]]:
    """All genes used by stage configs, nested params included, as (path, lo, hi, integer) tuples sorted by str(path).

    A path used several times is listed once, with the bounds of its first use in schedule order.
    """
    genes: Dict[Tuple, Tuple[Tuple, float, float, bool]] = {}
    for config in stage_configs:
        _walk_genes(list(config.get("params", {}).values()), genes)
    return _sorted_genes(genes)


def collect_project_genes(project: Dict[str, Any]) -> List[Tuple[Tuple, float, float, bool]]:
    """All genes of a Project: those of its schedule (as ``collect_genes``) and those inside its raw ``fields``
    definitions (e.g. layer thicknesses given as Gene dicts). Same format and order as ``collect_genes``."""
    genes: Dict[Tuple, Tuple[Tuple, float, float, bool]] = {}
    for config in project.get("schedule", []):
        _walk_genes(list(config.get("params", {}).values()), genes)
    _walk_genes(list(project.get("fields", {}).values()), genes)
    return _sorted_genes(genes)


def _walk_fits(value: Any, fits: Dict[str, Tuple[str, float, float, float]]) -> None:
    """Adds every Fit inside a param value (nested dicts, lists and Const values included) to ``fits`` by target."""
    if isinstance(value, dict):
        param = param_from_dict(value)
        if isinstance(param, Const) and param.value is value:
            for v in value.values():
                _walk_fits(v, fits)
            return
        value = param
    if isinstance(value, Fit):
        fits.setdefault(value.target, (value.target, float(value.init), float(value.lo), float(value.hi)))
    elif isinstance(value, Const):
        _walk_fits(value.value, fits)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk_fits(v, fits)


def collect_fits(project: Dict[str, Any]) -> List[Tuple[str, float, float, float]]:
    """All Fit params of a Project (schedule and field definitions) as (target, init, lo, hi), sorted by target.
    Fits sharing a target share one fitted value (bounds and init of the first use in schedule order)."""
    fits: Dict[str, Tuple[str, float, float, float]] = {}
    for config in project.get("schedule", []):
        _walk_fits(list(config.get("params", {}).values()), fits)
    _walk_fits(list(project.get("fields", {}).values()), fits)
    return [fits[k] for k in sorted(fits)]
