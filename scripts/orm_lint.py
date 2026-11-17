#!/usr/bin/env python3
"""orm_lint: static Django ORM checks for the Celery task paths of MrMap (#1398).

Run it as `python3 scripts/orm_lint.py` from the repository root. Standard
library only: no network, no database, no Django import, no gh. It parses the
backend with the `ast` module of the running CPython and answers the
architecture questions of the task-sql epic (#1387) that no off-the-shelf rule
answers - why each rule is custom and what the existing tools already cover
is the coverage matrix in `docs/source/development/orm-static-analysis.rst`:

  MRMAP-ORM-001  manager-first query plans     (blocking)
                 An inline select_related()/prefetch_related()/Prefetch(...)
                 plan inside a Celery task body (or a helper only the task
                 calls) belongs on the QuerySet of the owning model as a
                 for_<consumer>() method - the contract of #1397
                 (docs: queryset-manager-conventions).
  MRMAP-ORM-004  query inside a loop           (advisory)
                 A manager/queryset call inside a loop or comprehension in
                 task scope. A flag marks a CANDIDATE for N+1, never proof:
                 confirmation belongs in the test-time SQL capture of #1395.
  MRMAP-ORM-005  possible lazy relation access (advisory)
                 Iterating a queryset whose model is resolvable and then
                 touching a forward FK/O2O/M2M attribute that the loop
                 expression does not eager-load. Also a candidate, not proof.
  MRMAP-ORM-SUP  suppression hygiene           (blocking)
                 An `orm-lint: ignore` comment must name one specific rule ID
                 and carry a justification after `--` (#1398 rule 5).

What the scope is, and why it is drawn this way (#1398 rule 1: "match actual
Celery-decorated tasks/known call sites; don't flag all Python helpers by file
name alone"): every decorated Celery task function is an entry point, and the
scope of the task rules is its transitive closure over *same-module* function
calls - statically resolvable without an import graph and without pretending
to resolve `module.helper()` across modules. Manager and QuerySet classes are
the destination of rule 001, never its target, so class bodies whose name or
bases end in QuerySet/Manager are read for their eager-loading plans (so a
cross-module `for_<consumer>()` call site knows its own plan) but are never
flagged themselves.

A finding is a syntactic fact, never a measured cost. The message of every
suspicion rule says so and points at #1395; the tool never claims a SQL
speedup. Existing code is grandfathered through scripts/orm_lint_baseline.json
(keyed by rule + file + a fingerprint of the expression, so it survives line
moves); only NEW findings of the blocking rules fail the gate.

Exit codes: 0 clean (or advisory-only unless --fail-on advisory), 1 new
blocking findings, 2 the tool itself could not run (unreadable source).
"""

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ENGINE_ID = "mrmap-orm-lint"

# The excluded paths mirror sonar.exclusions/sonar.test.exclusions of
# sonar-project.properties: a finding the analyzer reports but the Sonar scan
# does not analyse would be dropped silently by the external-issues import.
EXCLUDED_DIR_NAMES = {
    "migrations", "tests", "fixtures", "__pycache__", "node_modules",
    "locale", "static", "templates", "behave", ".venv", ".git",
}

# Methods whose call on a receiver produces a queryset (lazy, chainable).
QUERYSET_METHODS = {
    "all", "filter", "exclude", "order_by", "distinct", "annotate",
    "alias", "values", "values_list", "iterator", "select_related",
    "prefetch_related", "only", "defer", "using", "none", "difference",
    "intersection", "union", "select_for_update", "reverse",
}
# Terminal methods that hit the database (directly or per call).
EVALUATING_METHODS = {
    "get", "count", "exists", "aggregate", "first", "last", "create",
    "update", "delete", "save", "bulk_create", "bulk_update", "in_bulk",
    "latest", "earliest", "get_or_create", "update_or_create",
}
# Methods of the 004 vocabulary: building OR evaluating per iteration.
LOOP_QUERY_METHODS = QUERYSET_METHODS | EVALUATING_METHODS
# Methods that never return a queryset even on a manager (so a chain ending
# in them is an instance, not something 005 can keep tracing).
INSTANCE_METHODS = {"get", "first", "last", "create", "get_or_create",
                    "update_or_create", "in_bulk", "latest", "earliest"}

PLAN_METHOD_PREFIXES = ("for_", "with_")

RULES = {
    "MRMAP-ORM-001": {
        "name": "manager-first query plan built inline in a Celery task",
        "type": "CODE_SMELL",
        "sonarSeverity": "MAJOR",
        "textSeverity": "warning",
        "blocking": True,
        "description": (
            "Query plans (select_related/prefetch_related/Prefetch) built "
            "inline in task code hide what the task reads. Move the plan "
            "into a for_<consumer>() method on the QuerySet of the owning "
            "model (docs: queryset-manager-conventions, #1397)."
        ),
    },
    "MRMAP-ORM-004": {
        "name": "database access inside a loop in task code",
        "type": "CODE_SMELL",
        "sonarSeverity": "MINOR",
        "textSeverity": "notice",
        "blocking": False,
        "description": (
            "A manager/queryset call inside a loop or comprehension is a "
            "candidate for an N+1 pattern. This is a static suspicion, not "
            "a proven cost: verify with the SQL capture of #1395 before "
            "changing the query plan (docs: celery-task-sql-regression)."
        ),
    },
    "MRMAP-ORM-005": {
        "name": "possible lazy relation access in task iteration",
        "type": "CODE_SMELL",
        "sonarSeverity": "INFO",
        "textSeverity": "notice",
        "blocking": False,
        "description": (
            "The loop reads an instance of a model whose queryset expression "
            "does not eager-load the related attribute it then accesses. "
            "One relation fetch per row is a candidate for an N+1 pattern; "
            "the eager load may also be genuinely unnecessary. Verify with "
            "the SQL capture of #1395 before adding a join (docs: "
            "celery-task-sql-regression, and the do-not-prefetch-the-"
            "backlog rule of queryset-manager-conventions)."
        ),
    },
    "MRMAP-ORM-SUP": {
        "name": "orm-lint suppression without a specific rule ID and justification",
        "type": "CODE_SMELL",
        "sonarSeverity": "MINOR",
        "textSeverity": "warning",
        "blocking": True,
        "description": (
            "A suppression comment must name one rule ID and carry a "
            "justification: `# orm-lint: ignore MRMAP-ORM-001 -- <why>` "
            "(#1398 rule 5). Blanket suppressions defeat the grandfathered "
            "baseline, which is the documented home of accepted findings."
        ),
    },
}

SUPPRESSION_RE = re.compile(
    r"#\s*orm-lint:\s*ignore(?P<rest>[^\n]*)"
)


class Finding:
    __slots__ = ("rule_id", "path", "line", "col", "end_line", "end_col",
                 "message", "secondaries", "fingerprint", "function",
                 "grandfathered")

    def __init__(self, rule_id, path, line, col, end_line, end_col, message,
                 secondary=(), fingerprint="", function=""):
        self.rule_id = rule_id
        self.path = path
        self.line = line
        self.col = col
        self.end_line = end_line
        self.end_col = end_col
        self.message = message
        self.secondaries = list(secondary)
        self.fingerprint = fingerprint
        self.function = function
        self.grandfathered = False

    def sort_key(self):
        return (str(self.path), self.line, self.col, self.rule_id, self.message)

    def as_dict(self):
        return {
            "ruleId": self.rule_id,
            "filePath": str(self.path),
            "line": self.line,
            "column": self.col + 1,
            "endLine": self.end_line,
            "endColumn": self.end_col,
            "message": self.message,
            "function": self.function,
            "fingerprint": self.fingerprint,
            "grandfathered": self.grandfathered,
            "secondaries": [{"filePath": str(p), "line": l, "message": m}
                            for p, l, m in self.secondaries],
        }


def fp(*parts):
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


def call_chain(node):
    """Flatten `A.b(...).c(...)` into (root_expr, [method, ...])."""
    methods = []
    cur = node
    while isinstance(cur, ast.Call):
        if not isinstance(cur.func, ast.Attribute):
            return None, None
        methods.append(cur.func.attr)
        cur = cur.func.value
        # stop between chained calls, continue through plain attribute hops
        while isinstance(cur, ast.Attribute) and not isinstance(cur.value, ast.Call):
            # e.g. Model.objects.filter -> the 'objects' hop belongs to root
            methods.append("<attr:%s>" % cur.attr)
            cur = cur.value
    methods.reverse()
    return cur, methods


def root_model_of(node, model_names):
    """Model class name if the chain roots at `Model.objects`/`Model._default_manager`."""
    if isinstance(node, ast.Attribute) and node.attr in ("objects", "_default_manager"):
        base = node.value
        if isinstance(base, ast.Name) and base.id in model_names:
            return base.id
    if isinstance(node, ast.Name) and node.id in model_names:
        return node.id
    return None


def eager_fields_of(call_node, plan_index, model_names):
    """Eager-loading field strings this queryset expression applies, or None
    when an unresolvable custom manager method makes the answer unknown.

    None means "unknown" and callers must treat the expression as possibly
    eager-loading anything (no 005 flag). A concrete set means: these and
    only these, as far as the syntax shows.
    """
    fields = set()
    cur = call_node
    saw_custom = False
    while True:
        if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            attr = cur.func.attr
            if attr in ("select_related", "prefetch_related"):
                for arg in cur.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        fields.add(arg.value)
                for kw in cur.keywords:
                    if kw.arg == "prefetch_object" or isinstance(kw.value, ast.Call):
                        pf = prefetch_name(kw.value)
                        if pf:
                            fields.add(pf)
            elif attr == "Prefetch" or (isinstance(cur.func, ast.Name) and cur.func.id == "Prefetch"):
                pf = prefetch_name(cur)
                if pf:
                    fields.add(pf)
            elif attr in QUERYSET_METHODS:
                pass
            elif attr in INSTANCE_METHODS:
                return None  # chain materialises: instance, not a queryset
            else:
                # custom manager/queryset method: resolvable through the
                # plan index (every QuerySet/Manager class of the backend was
                # read), unknown if absent from it
                seen = plan_index.get(attr)
                if seen is None:
                    if attr.startswith(PLAN_METHOD_PREFIXES):
                        return None
                    saw_custom = True
                else:
                    fields |= seen
            cur = cur.func.value
            continue
        break
    root_model = root_model_of(cur, model_names)
    if root_model is None and saw_custom:
        return None
    return fields


def prefetch_name(call):
    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "Prefetch":
        call = call
    elif isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "Prefetch":
        pass
    else:
        return None
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def is_queryset_call(node, model_names, plan_index):
    """True when the expression denotes a queryset by syntax."""
    return queryset_info(node, model_names, plan_index) is not None


class QInfo:
    __slots__ = ("root_model", "eager", "materialises")

    def __init__(self, root_model, eager, materialises=False):
        self.root_model = root_model
        self.eager = eager          # None == unknown
        self.materialises = materialises


def queryset_info(node, model_names, plan_index):
    """QInfo for a Call expression, or None when it is not queryset-shaped."""
    if not isinstance(node, ast.Call):
        return None
    root, methods = call_chain(node)
    if not methods:
        return None
    model = root_model_of(root, model_names)
    terminal = methods[-1] if methods else None
    if terminal in INSTANCE_METHODS:
        return QInfo(model, None, materialises=True)
    every_method_known_qs = all(
        m in QUERYSET_METHODS or m.startswith(PLAN_METHOD_PREFIXES) or m in plan_index.get("<all>", ())
        for m in methods if not m.startswith("<attr:")
    )
    if not every_method_known_qs:
        return None
    eager = eager_fields_of(node, plan_index, model_names)
    return QInfo(model, eager)


def unparse(node):
    try:
        return ast.unparse(node)
    except (ValueError, RecursionError):
        return "<expr>"


class RelationMap:
    """model class name -> {field: ("fk"|"o2o"|"m2m", target)}, one level of
    base-class merge across the parsed files."""

    def __init__(self):
        self.relations = {}
        self.bases = {}
        self.model_names = set()


class PlanIndex(dict):
    """method name -> eager fields applied in its body; '<all>' -> all names."""

    def __init__(self):
        super().__init__()
        self["<all>"] = set()


RELATION_FACTORIES = {"ForeignKey": "fk", "OneToOneField": "o2o",
                      "ManyToManyField": "m2m"}


def parse_tree(path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None


def discover_files(root):
    backend = root / "backend"
    out = []
    for path in sorted(backend.rglob("*.py")):
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in EXCLUDED_DIR_NAMES for p in parts):
            continue
        out.append(path)
    return out


def read_relations_and_plans(files):
    """One pass over all files: model relations, model names, plan index."""
    rmap = RelationMap()
    plan = PlanIndex()
    for path in files:
        tree = parse_tree(path)
        if tree is None:
            continue
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            is_model = any(
                (isinstance(b, ast.Name) and (b.id.endswith("Model") or b.id.endswith("ModelMixin")))
                or (isinstance(b, ast.Attribute) and b.attr.endswith(("Model", "ModelMixin")))
                for b in cls.bases
            )
            base_names = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                          for b in cls.bases}
            qs_class = any(
                (isinstance(b, ast.Name) and (b.id.endswith("QuerySet") or b.id.endswith("Manager")))
                or (isinstance(b, ast.Attribute) and b.attr.endswith(("QuerySet", "Manager")))
                for b in cls.bases
            ) or cls.name.endswith(("QuerySet", "Manager"))
            if is_model:
                rmap.model_names.add(cls.name)
                rels = {}
                for stmt in cls.body:
                    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                        fname = (stmt.value.func.id if isinstance(stmt.value.func, ast.Name)
                                 else getattr(stmt.value.func, "attr", ""))
                        kind = RELATION_FACTORIES.get(fname)
                        if kind is None:
                            continue
                        for target in stmt.targets:
                            if isinstance(target, ast.Name):
                                rels[target.id] = (kind, "")
                rmap.relations[cls.name] = rels
                rmap.bases[cls.name] = base_names
            if qs_class:
                for fn in cls.body:
                    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    eager = set()
                    for sub in ast.walk(fn):
                        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                                and sub.func.attr in ("select_related", "prefetch_related"):
                            for arg in sub.args:
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                    eager.add(arg.value)
                        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                                and sub.func.id == "Prefetch":
                            pf = prefetch_name(sub)
                            if pf:
                                eager.add(pf)
                    plan.setdefault(fn.name, set()).update(eager)
                    plan["<all>"].add(fn.name)
    # one level of base merging for abstract mixins
    for model, bases in list(rmap.bases.items()):
        for base in bases:
            if base in rmap.relations and base != model:
                merged = dict(rmap.relations[base])
                merged.update(rmap.relations[model])
                rmap.relations[model] = merged
                rmap.model_names.add(base)
    return rmap, plan


class ModuleScope:
    """A parsed module: celery tasks, and their same-module transitive closure."""

    def __init__(self, path, tree, root):
        self.path = path
        self.rel = path.relative_to(root)
        self.tree = tree
        self.module_functions = {}
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.module_functions[stmt.name] = stmt
        self.celery_aliases = self._celery_names(tree)
        self.entry_points = []
        for name, fn in self.module_functions.items():
            if self._is_task_decorator(fn.decorator_list, self.celery_aliases):
                self.entry_points.append(fn)
        self.scoped_names = set()

    @staticmethod
    def _celery_names(tree):
        """Names this module can use to decorate a Celery task."""
        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top == "celery":
                    # `from celery import shared_task`, `from .celery import app`
                    for alias in node.names:
                        aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "celery" or alias.name.startswith("celery."):
                        for nm in ("shared_task", "task"):
                            aliases.add("celery.%s" % nm)
        return aliases

    @staticmethod
    def _is_task_decorator(decorators, aliases):
        for dec in decorators:
            node = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(node, ast.Name) and node.id in aliases:
                return True
            if isinstance(node, ast.Attribute) and node.attr in ("shared_task", "task"):
                # dotted form: `@celery.shared_task`, `@app.task`
                if node.attr == "shared_task" or "task" in aliases \
                        or "celery.task" in aliases or unparse(node.value) in aliases:
                    return True
        return False

    def task_scope(self):
        """Entry points plus everything they call in this same module."""
        scoped = set(id(fn) for fn in self.entry_points)
        queue = list(self.entry_points)
        visited_names = set()
        while queue:
            fn = queue.pop()
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    callee = node.func.id if isinstance(node.func, ast.Name) else None
                    if callee and callee in self.module_functions \
                            and callee not in visited_names:
                        visited_names.add(callee)
                        helper = self.module_functions[callee]
                        scoped.add(id(helper))
                        queue.append(helper)
        self.scoped_names = visited_names
        return scoped, self.entry_points, self.module_functions


def enclosing_class_stack(tree):
    """map id(function) -> list of enclosing class names (for QuerySet detection)"""
    result = {}

    def visit(node, stack):
        for child in ast.iter_child_nodes(node):
            child_stack = stack
            if isinstance(child, ast.ClassDef):
                child_stack = stack + [child.name]
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[id(child)] = child_stack
                visit(child, child_stack)
                continue
            visit(child, child_stack)

    visit(tree, [])
    return result


ORM_TERMS = ("objects", "select_related", "prefetch_related", "filter", "exclude", "all")


def contains_orm_term(text, model_names):
    if ".objects" in text or "_default_manager" in text:
        return True
    for term in ORM_TERMS:
        if ".%s(" % term in text:
            return True
    first = text.split(".")[0].split("(")[0].strip()
    return first in model_names


class FunctionWalker(ast.NodeVisitor):
    """Runs 001/004/005 inside one function that lies in task scope."""

    def __init__(self, module, func, rmap, plan, classes_of_fn, findings, in_class):
        self.module = module
        self.func = func
        self.rmap = rmap
        self.plan = plan
        self.classes = classes_of_fn
        self.findings = findings
        self.in_qs_class = in_class
        self.loop_depth = 0
        self.loop_stack = []
        self.bindings = {}          # name -> QInfo (single assignment tracking)
        self.iterated_instances = {}  # name -> model name (loop targets)
        self.seen_suppressions = set()

    def add(self, rule_id, node, message, secondary=(), fingerprint_expr=None):
        self.findings.append(Finding(
            rule_id, self.module.rel, node.lineno, node.col_offset,
            getattr(node, "end_lineno", node.lineno),
            getattr(node, "end_col_offset", node.col_offset),
            message, secondary=secondary,
            fingerprint=fp(rule_id, str(self.module.rel), self.func.name,
                           unparse(fingerprint_expr if fingerprint_expr is not None else node)),
            function=self.func.name,
        ))

    # -- queryset-shaped expressions -------------------------------------

    def qinfo(self, node):
        """QInfo for an expression, following one local assignment, a slice
        or `.iterator()` wrapping if needed."""
        if isinstance(node, ast.Subscript):
            return self.qinfo(node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "iterator":
            return self.qinfo(node.func.value)
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id)
        if not isinstance(node, ast.Call):
            return None
        return queryset_info(node, self.rmap.model_names, self.plan)

    # -- statements ------------------------------------------------------

    def visit_Assign(self, node):
        info = self.qinfo(node.value)
        if info is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.bindings[target.id] = info
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self.visit_Assign(ast.Assign(targets=[node.target] if node.target else [],
                                     value=node.value))

    def visit_For(self, node):
        # the iterable is evaluated where the loop sits: at THIS depth (an
        # inner loop's queryset inside an outer loop IS one access per outer
        # iteration; its own loop body is the one level deeper)
        self.visit(node.iter)
        if node.orelse:
            for stmt in node.orelse:
                self._run(stmt)
        info = self.qinfo(node.iter)
        targets = []
        for t in ast.walk(node.target):
            if isinstance(t, ast.Name):
                targets.append(t.id)
        if info is not None and info.root_model and not info.materialises:
            eager = info.eager
            for name in targets:
                self.iterated_instances[name] = (info.root_model, eager)
        self.loop_depth += 1
        self.loop_stack.append(node)
        for stmt in node.body:
            self._run(stmt)
        self.loop_stack.pop()
        self.loop_depth -= 1
        # 005 on the loop itself, after the body analysis collected nothing extra
        if info is not None and info.root_model and not info.materialises:
            self.check_lazy_relations(node, targets, info)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.loop_depth += 1
        self.loop_stack.append(node)
        for stmt in node.body + node.orelse:
            self._run(stmt)
        self.loop_stack.pop()
        self.loop_depth -= 1

    def visit_ListComp(self, node):
        self._comprehension(node)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def _comprehension(self, node):
        # the outermost iterable is evaluated where the comprehension sits;
        # every later iterable and the element expression run per iteration
        gens = node.generators
        if gens:
            self.visit(gens[0].iter)
            for gen in gens:
                self.visit(gen.target)
                for cond in gen.ifs:
                    self.visit(cond)
            self.loop_depth += 1
            self.loop_stack.append(node)
            if isinstance(node, ast.DictComp):
                self.visit(node.key)
                self.visit(node.value)
            else:
                self.visit(node.elt)
            self.loop_stack.pop()
            self.loop_depth -= 1
        return

    def _run(self, stmt):
        self.visit(stmt)

    # -- expressions -----------------------------------------------------

    def visit_Call(self, node):
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else None

        # 001: inline plan
        if not self.in_qs_class and attr in ("select_related", "prefetch_related"):
            plan_fields = [a.value for a in node.args
                           if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            shape = ("(%s)" % ", ".join(repr(f) for f in plan_fields)) if plan_fields else "()"
            self.add(
                "MRMAP-ORM-001", node,
                "`.%s%s` builds a query plan inline in task code `%s`. Per the "
                "conventions of #1397 a nontrivial plan belongs on the "
                "QuerySet of the owning model (e.g. `for_<consumer>()`); the "
                "plan is then reviewable and countable where it is written. "
                "Suppress with a justification only for a genuine one-off "
                "(see docs: queryset-manager-conventions)."
                % (attr, shape, self.func.name),
                fingerprint_expr=node.func,
            )
        if not self.in_qs_class and isinstance(node.func, ast.Name) and node.func.id == "Prefetch":
            self.add(
                "MRMAP-ORM-001", node,
                "`Prefetch(...)` built inline in task code `%s`: relation "
                "loading plans belong on the QuerySet of the owning model "
                "(#1397, docs: queryset-manager-conventions)." % self.func.name,
                fingerprint_expr=node.func,
            )

        # 004: db access inside a loop
        if self.loop_depth > 0 and attr in LOOP_QUERY_METHODS \
                and not self.in_qs_class:
            recv = node.func.value
            if self.is_orm_receiver(recv):
                loop = self.loop_stack[-1]
                self.add(
                    "MRMAP-ORM-004", node,
                    "`.%s(...)` runs inside a loop in task code `%s`: one "
                    "statement per iteration. This is a CANDIDATE for an N+1 "
                    "pattern, not a proven cost - verify with the SQL "
                    "capture of #1395 (docs: celery-task-sql-regression) "
                    "before re-shaping the query." % (attr, self.func.name),
                    secondary=[(self.module.rel, loop.lineno,
                                "the loop this access sits in")],
                    fingerprint_expr=node.func,
                )

        # keep tracing queryset chains
        self.generic_visit(node)

    def is_orm_receiver(self, recv):
        if isinstance(recv, ast.Name):
            if recv.id in self.rmap.model_names:
                return True
            if recv.id in self.iterated_instances:
                return True
            bound = self.bindings.get(recv.id)
            if bound is not None:
                return True
            return False
        if isinstance(recv, ast.Call):
            return is_queryset_call(recv, self.rmap.model_names, self.plan) \
                or contains_orm_term(unparse(recv), self.rmap.model_names)
        if isinstance(recv, ast.Attribute):
            return contains_orm_term(unparse(recv), self.rmap.model_names)
        return False

    # -- 005 -------------------------------------------------------------

    def check_lazy_relations(self, for_node, targets, info):
        if info.eager is None:
            return  # an unresolvable custom method made the plan unknown
        for stmt in for_node.body + for_node.orelse:
            for node in ast.walk(stmt):
                if not isinstance(node, ast.Attribute):
                    continue
                if not isinstance(node.value, ast.Name) or node.value.id not in targets:
                    continue
                field = node.attr
                if field in INSTANCE_METHODS or field in ("pk", "id") \
                        or field.endswith("_id"):
                    continue
                rels = self.rmap.relations.get(info.root_model, {})
                if field not in rels:
                    continue  # plain column, reverse name (unknown here), or method
                path = field.split("__")
                if any(p in info.eager for p in path) or field in info.eager:
                    continue
                kind = rels[field][0]
                suggestion = "select_related" if kind in ("fk", "o2o") else "prefetch_related"
                self.add(
                    "MRMAP-ORM-005", node,
                    "the loop over `%s` reads `.%s` (%s relation of `%s`) per "
                    "row and the queryset does not eager-load it. CANDIDATE "
                    "for lazy relation access - one query per row is possible "
                    "but unproven: measure with #1395 before deciding whether "
                    "`%s(\"%s\")` is right at all (the do-not-prefetch-the-"
                    "backlog rule of queryset-manager-conventions may prefer "
                    "leaving it lazy)."
                    % (unparse(for_node.iter)[:80], field, kind, info.root_model,
                       suggestion, field),
                    secondary=[(self.module.rel, for_node.lineno,
                                "iterating a queryset of %s" % info.root_model)],
                    fingerprint_expr=node,
                )

    # -- containers we must descend into manually (loop scoping) ---------

    def _visit_block_container(self, node):
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    visit_FunctionDef = _visit_block_container
    visit_AsyncFunctionDef = _visit_block_container
    visit_If = _visit_block_container
    visit_Try = _visit_block_container
    visit_TryStar = _visit_block_container
    visit_With = _visit_block_container
    visit_AsyncWith = _visit_block_container


def analyze_file(module, rmap, plan, findings):
    classes = enclosing_class_stack(module.tree)
    scoped_ids, entries, module_functions = module.task_scope()
    if not entries:
        return
    before = len(findings)
    scoped_functions = [fn for name, fn in sorted(module_functions.items())
                        if id(fn) in scoped_ids]
    for fn in scoped_functions:
        walker = FunctionWalker(module, fn, rmap, plan, classes.get(id(fn), []),
                                findings,
                                any(n.endswith(("QuerySet", "Manager"))
                                    for n in classes.get(id(fn), [])))
        walker.visit(fn)
    # a chained statement `X.filter(..).order_by(..)` visits every chain
    # member at the same start position; keep one finding per position,
    # preferring the evaluating method of the chain
    grouped = {}
    for f in findings[before:]:
        if f.rule_id != "MRMAP-ORM-004":
            continue
        key = (f.path, f.function, f.line, f.col)
        method = re.search(r"`\.(\w+)\(", f.message)
        rank = (0 if (method and method.group(1) in EVALUATING_METHODS) else 1,
                method.group(1) if method else "", f.message)
        cur = grouped.get(key)
        if cur is None or rank < cur[0]:
            grouped[key] = (rank, f)
    losers = set()
    for key, (_, winner) in grouped.items():
        for f in findings[before:]:
            if f.rule_id == "MRMAP-ORM-004" \
                    and (f.path, f.function, f.line, f.col) == key \
                    and f is not winner:
                losers.add(id(f))
    findings[:] = [f for f in findings if id(f) not in losers]


def find_suppressions(root, files, findings):
    """Validate suppression comments; return a map (path,line)->rule ids ignored."""
    ignored = {}
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel = path.relative_to(root)
        for idx, line in enumerate(lines, start=1):
            m = SUPPRESSION_RE.search(line)
            if not m:
                continue
            rest = m.group("rest").strip()
            parts = re.split(r"--", rest, maxsplit=1)
            rule_part = parts[0].strip()
            why = parts[1].strip() if len(parts) > 1 else ""
            problems = []
            if not rule_part:
                problems.append("names no rule ID")
            elif rule_part == "all":
                problems.append("suppresses all rules; name the specific rule ID")
            elif rule_part not in RULES:
                problems.append("rule ID `%s` is unknown" % rule_part)
            if not why:
                problems.append("carries no justification after `--`")
            if problems:
                findings.append(Finding(
                    "MRMAP-ORM-SUP", rel, idx, line.index("#"),
                    idx, len(line),
                    "suppression comment `%s` %s; the form is "
                    "`# orm-lint: ignore MRMAP-ORM-001 -- <why>` (#1398 rule 5)."
                    % (line.strip(), " and ".join(problems)),
                    fingerprint=fp("MRMAP-ORM-SUP", str(rel), str(idx), rule_part),
                ))
            else:
                ignored.setdefault((str(rel), idx), set()).add(rule_part)
                ignored.setdefault((str(rel), idx + 1), set()).add(rule_part)
    return ignored


def load_baseline(root):
    path = root / "scripts" / "orm_lint_baseline.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("orm_lint: %s is not readable JSON: %s" % (path, exc))
    return data.get("findings", [])


def to_sonar(findings, root):
    issues = []
    for f in findings:
        rule = RULES[f.rule_id]
        loc = {
            "message": f.message,
            "filePath": str(f.path),
            "textRange": {"startLine": f.line, "startColumn": f.col,
                          "endLine": f.end_line, "endColumn": f.end_col},
        }
        issue = {
            "engineId": ENGINE_ID,
            "ruleId": f.rule_id,
            "severity": rule["sonarSeverity"],
            "type": rule["type"],
            "primaryLocation": loc,
            "effortMinutes": 30 if f.rule_id == "MRMAP-ORM-001" else 15,
        }
        if f.secondaries:
            issue["secondaryLocations"] = [
                {"message": msg, "filePath": str(p),
                 "textRange": {"startLine": ln}}
                for p, ln, msg in f.secondaries
            ]
        issues.append(issue)
    return {
        "issues": issues,
        "rules": [
            {"id": rid, "name": r["name"], "severity": r["sonarSeverity"],
             "type": r["type"], "description": r["description"]}
            for rid, r in sorted(RULES.items())
        ],
    }


def to_sarif(findings):
    rule_index = sorted(RULES)
    results = []
    for f in findings:
        results.append({
            "ruleId": f.rule_id,
            "level": {"warning": "warning", "notice": "note",
                      "error": "error"}[RULES[f.rule_id]["textSeverity"]],
            "message": {"text": f.message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": str(f.path).replace("\\", "/")},
                    "region": {"startLine": f.line, "startColumn": f.col + 1},
                }
            }],
            "fingerprints": {"mrmapFingerprint/v1": f.fingerprint},
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": ENGINE_ID,
                "version": "1",
                "informationUri": "https://github.com/mrmap-community/mrmap/"
                                  "issues/1398",
                "rules": [
                    {"id": rid, "name": RULES[rid]["name"],
                     "shortDescription": {"text": RULES[rid]["description"]}}
                    for rid in rule_index
                ],
            }},
            "results": results,
        }],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="orm_lint",
        description="Static Django ORM checks over the Celery task scope (#1398).")
    ap.add_argument("--root", default=".", help="repository root (default: cwd)")
    ap.add_argument("--format", choices=("text", "json", "sonar", "sarif", "github"),
                    default="text")
    ap.add_argument("--output", "-o", default=None,
                    help="write the report to this file instead of stdout")
    ap.add_argument("--fail-on", choices=("blocking", "advisory", "nothing"),
                    default="blocking",
                    help="fail on new blocking findings (default), on any new "
                         "finding, or never")
    ap.add_argument("--no-baseline", action="store_true",
                    help="ignore the grandfather baseline")
    ap.add_argument("--update-baseline", action="store_true",
                    help="rewrite scripts/orm_lint_baseline.json with the "
                         "current findings (grandfather them)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "backend").is_dir():
        print("orm_lint: no backend/ below %s - run it from the repository root"
              % root, file=sys.stderr)
        return 2

    files = discover_files(root)
    rmap, plan = read_relations_and_plans(files)

    findings = []
    unreadable = 0
    for path in files:
        tree = parse_tree(path)
        if tree is None:
            unreadable += 1
            continue
        analyze_file(ModuleScope(path, tree, root), rmap, plan, findings)

    suppressions = find_suppressions(root, files, findings)
    findings = [f for f in findings
                if f.rule_id not in suppressions.get((str(f.path), f.line), ())]

    baseline = [] if args.no_baseline else load_baseline(root)
    baseline_keys = {(b["ruleId"], b["file"], b["fingerprint"]) for b in baseline}
    for f in findings:
        if (f.rule_id, str(f.path), f.fingerprint) in baseline_keys:
            f.grandfathered = True

    findings.sort(key=lambda f: f.sort_key())

    new_findings = [f for f in findings if not f.grandfathered]
    new_blocking = [f for f in new_findings if RULES[f.rule_id]["blocking"]]

    if args.update_baseline:
        entries = [f for f in findings if f.rule_id != "MRMAP-ORM-SUP"]
        data = {
            "_comment": [
                "Grandfathered findings of scripts/orm_lint.py (#1398). An",
                "entry is the accepted state of the code at migration time;",
                "new findings of a blocking rule fail the gate. Keyed by rule,",
                "file and a fingerprint of the expression, so moving code",
                "around does not hide a finding and fixing code retires the",
                "entry on the next --update-baseline.",
            ],
            "findings": [
                {"ruleId": f.rule_id, "file": str(f.path),
                 "function": f.function, "line": f.line,
                 "fingerprint": f.fingerprint}
                for f in sorted(entries, key=lambda f: f.sort_key())
            ],
        }
        target = root / "scripts" / "orm_lint_baseline.json"
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("orm_lint: wrote %d baseline entries to %s"
              % (len(entries), target.relative_to(root)))

    if args.format == "text" or args.update_baseline:
        for f in findings:
            sev = RULES[f.rule_id]["textSeverity"]
            tag = " [grandfathered]" if f.grandfathered else ""
            print("%s:%d:%d: %s %s: %s%s"
                  % (f.path, f.line, f.col + 1, sev, f.rule_id, f.message, tag))
        n = lambda r: sum(1 for f in findings if f.rule_id == r)  # noqa: E731
        print("orm_lint: %d findings (%d new) - 001: %d, 004: %d, 005: %d, SUP: %d"
              % (len(findings), len(new_findings),
                 n("MRMAP-ORM-001"), n("MRMAP-ORM-004"),
                 n("MRMAP-ORM-005"), n("MRMAP-ORM-SUP")))
        if unreadable:
            print("orm_lint: %d files could not be parsed and were skipped" % unreadable,
                  file=sys.stderr)
            return 2
    else:
        if args.format == "github":
            lines = []
            for f in new_findings:
                level = RULES[f.rule_id]["textSeverity"]
                lines.append("::%s file=%s,line=%d,col=%d,title=%s::%s"
                             % (level, f.path, f.line, f.col + 1, f.rule_id,
                                f.message.replace("%", "%25").replace("\n", "%0A")))
            payload = "\n".join(lines)
        elif args.format == "sonar":
            payload = json.dumps(to_sonar(new_findings, root), indent=2)
        elif args.format == "sarif":
            payload = json.dumps(to_sarif(new_findings), indent=2)
        else:
            payload = json.dumps({"findings": [f.as_dict() for f in findings]},
                                 indent=2)
        if args.output:
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)

    if args.fail_on == "nothing":
        return 0
    if args.fail_on == "advisory" and new_findings:
        return 1
    return 1 if new_blocking else 0


if __name__ == "__main__":
    sys.exit(main())
