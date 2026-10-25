"""Guard: annotations evaluated at import time must not name a module-level
binding that appears LATER in the file.

Python 3.14 evaluates annotations lazily (PEP 649), so such a forward
reference passes the 3.14 suite yet raises NameError on 3.11/3.12 (the
package supports >=3.11). Files with `from __future__ import annotations`
are exempt; this repo's convention is otherwise eager annotations.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "emcee"


def _targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [n for e in node.elts for n in _targets(e)]
    if isinstance(node, ast.Starred):
        return _targets(node.value)
    return []


def _bound_by(stmt: ast.stmt) -> list[str]:
    """Module-level names a top-level statement binds (nested blocks included)."""
    names: list[str] = []
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.append(stmt.name)
    elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
        for a in stmt.names:
            names.append((a.asname or a.name).split(".")[0])
    elif isinstance(stmt, ast.Assign):
        for t in stmt.targets:
            names += _targets(t)
    elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
        names += _targets(stmt.target)
    elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.stmt):
                names += _bound_by(child)
            elif isinstance(child, ast.ExceptHandler):
                names += [n for s in child.body for n in _bound_by(s)]
    return names


def _eager_annotations(stmt: ast.stmt) -> list[ast.expr]:
    out: list[ast.expr] = []

    def from_def(fn):
        a = fn.args
        for arg in [*a.posonlyargs, *a.args, a.vararg, *a.kwonlyargs, a.kwarg]:
            if arg is not None and arg.annotation is not None:
                out.append(arg.annotation)
        if fn.returns is not None:
            out.append(fn.returns)

    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        from_def(stmt)
    elif isinstance(stmt, ast.ClassDef):
        for item in stmt.body:
            if isinstance(item, ast.AnnAssign):
                out.append(item.annotation)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                from_def(item)
    return out


def _names_in(expr: ast.expr) -> list[ast.Name]:
    """ast.Name nodes inside the expression; string constants are not parsed."""
    return [n for n in ast.walk(expr) if isinstance(n, ast.Name)]


def find_forward_annotation_refs(source: str, path: str) -> list[str]:
    tree = ast.parse(source)
    if "from __future__ import annotations" in source:
        return []
    all_bound: dict[str, int] = {}  # name -> index of the statement binding it first
    for i, stmt in enumerate(tree.body):
        for name in _bound_by(stmt):
            all_bound.setdefault(name, i)
    offenders = []
    for i, stmt in enumerate(tree.body):
        for ann in _eager_annotations(stmt):
            for n in _names_in(ann):
                first = all_bound.get(n.id)
                # bound only later (a def's own name is bound AFTER its
                # annotations evaluate, so first == i is also too late)
                if first is not None and first >= i:
                    offenders.append(f"{path}:{n.lineno} {n.id}")
    return offenders


def test_no_eager_annotation_references_a_later_module_binding():
    offenders: list[str] = []
    files = sorted(SRC.rglob("*.py"))
    assert files
    for f in files:
        offenders += find_forward_annotation_refs(f.read_text(), str(f.relative_to(SRC.parent)))
    assert not offenders, "forward annotation reference(s):\n" + "\n".join(offenders)


def test_the_guard_bites_on_a_synthetic_forward_reference():
    src = "def f(x: Later) -> None: ...\n\nclass Later: ...\n"
    assert find_forward_annotation_refs(src, "m.py") == ["m.py:1 Later"]
    ok = "class Early: ...\n\ndef f(x: Early) -> 'Late': ...\n\nclass Late: ...\n"
    assert find_forward_annotation_refs(ok, "m.py") == []
