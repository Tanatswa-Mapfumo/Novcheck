"""Static capability controls; malicious source is parsed, never imported/executed."""

import ast
from importlib.util import resolve_name

BANNED = (
    "tests",
    "httpx",
    "requests",
    "openai",
    "anthropic",
    "google",
    "socket",
    "subprocess",
    "novelty_harness.providers",
    "novelty_harness.research",
    "novelty_harness.intake",
    "novelty_harness.application.research",
    "novelty_harness.application.evidence_phase6",
    "novelty_harness.application.phase6_fixture",
    "novelty_harness.application.phase7",
    "novelty_harness.domain.adjudication",
    "novelty_harness.ports.search",
)
UPSTREAM_WRITES = (
    "freeze_phase7",
    "begin_phase7",
    "record_phase7",
    "record_phase6",
    "commit_phase6",
    "publish_phase6",
    "put_source",
    "put_passage",
    "record_source",
    "record_passage",
)
SQL_CALLS = {"execute", "exec_driver_sql", "create_engine", "Session", "Connection"}
NUMERIC_NOVELTY = {"novelty_score", "confidence", "probability", "novelty_probability"}


def reporting_violations(source, package, *, pure=False, modules=None, _seen=None):
    tree = ast.parse(source)
    aliases = {}
    imports = []
    violations = []
    seen = set() if _seen is None else _seen

    def qualified(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return qualified(node.value) + "." + node.attr
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            return qualified(node.args[0]) + "." + node.args[1].value
        if isinstance(node, ast.Call) and qualified(node.func) == "re.compile":
            return "re.Pattern"
        return ""

    # Imports and simple binding aliases are resolved before call inspection.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = (
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            imports.append(base)
            for alias in node.names:
                full = base + "." + alias.name
                aliases[alias.asname or alias.name] = full
                imports.append(full)
        elif isinstance(node, ast.Assign):
            value = qualified(node.value)
            if value:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = value

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Tuple)
            and isinstance(node.iter, ast.Tuple)
        ):
            for index, target in enumerate(node.target.elts):
                values = [
                    qualified(row.elts[index])
                    for row in node.iter.elts
                    if isinstance(row, ast.Tuple) and len(row.elts) > index
                ]
                if (
                    isinstance(target, ast.Name)
                    and values
                    and len(values) == len(node.iter.elts)
                    and all(value == "re.Pattern" for value in values)
                ):
                    aliases[target.id] = "re.Pattern"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = qualified(node.func)
            tail = function.split(".")[-1]
            if function in {"__import__", "importlib.import_module"}:
                if (
                    not node.args
                    or not isinstance(node.args[0], ast.Constant)
                    or not isinstance(node.args[0].value, str)
                ):
                    violations.append("unresolved dynamic import")
                else:
                    name = node.args[0].value
                    if name.startswith(".") and function == "importlib.import_module":
                        package_node = (
                            node.args[1]
                            if len(node.args) > 1
                            else next(
                                (kw.value for kw in node.keywords if kw.arg == "package"), None
                            )
                        )
                        if isinstance(package_node, ast.Constant) and isinstance(
                            package_node.value, str
                        ):
                            try:
                                name = resolve_name(name, package_node.value)
                            except (ImportError, ValueError):
                                violations.append("unresolved dynamic import")
                        else:
                            violations.append("unresolved dynamic import")
                    imports.append(name)
            if tail in SQL_CALLS or tail.startswith(UPSTREAM_WRITES):
                violations.append("forbidden capability call: " + function)
            if (
                tail in {"search", "retrieve", "browse", "run_phase7", "run_phase6_evidence"}
                and function != "re.Pattern.search"
            ):
                violations.append("upstream/search call: " + function)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in NUMERIC_NOVELTY:
                violations.append("numeric novelty field: " + node.target.id)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in NUMERIC_NOVELTY
        ):
            violations.append("numeric novelty key: " + node.value)

    for name in imports:
        if any(name == prefix or name.startswith(prefix + ".") for prefix in BANNED):
            violations.append("forbidden import: " + name)
        if pure:
            if name.startswith(
                ("novelty_harness.application", "novelty_harness.ports", "sqlalchemy")
            ):
                violations.append("infrastructure in pure report contract: " + name)
            if name.startswith("novelty_harness.runtime") and not (
                name == "novelty_harness.runtime.tracing.hashing"
                or name.startswith("novelty_harness.runtime.tracing.hashing.")
            ):
                violations.append("runtime capability in pure report contract: " + name)
        if modules:
            candidates = [
                module for module in modules if name == module or name.startswith(module + ".")
            ]
            for module in candidates:
                if module not in seen:
                    seen.add(module)
                    violations.extend(
                        reporting_violations(
                            modules[module],
                            module.rsplit(".", 1)[0],
                            pure=pure,
                            modules=modules,
                            _seen=seen,
                        )
                    )
    return violations
