"""T-035: every loop of silent steps must end even when the code sandbox fails.

Live v20 (PUB-12, A+B): after one note, every code run failed ("Sandbox did not return a
parseable result"). ``note_state`` kept its last value, so ``note_next`` -> ``note_record`` ->
``note_next`` sent about 40 notes until the customer hung up. The engine does not count turns
on code steps; it does count the calls of an api step (``<node>_success_count`` /
``<node>_failure_count``, and the same with the tool name, F-067). A loop made only of code and
api steps therefore needs an exit whose condition reads only those counters: it holds after a
bounded number of calls whatever the code did.
"""

from __future__ import annotations

from typing import Any

COUNTER_SUFFIXES = ("_success_count", "_failure_count")
SILENT_TYPES = ("code", "api_request")


def _targets(node: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    edges = [(item.get("target_node", ""), item.get("condition") or {}) for item in node.get("transitions") or []]
    default = node.get("passthrough_default_transition")
    if default:
        edges.append((default, {"operator": "always"}))
    return edges


def silent_cycles(workflow: dict[str, Any]) -> list[list[str]]:
    """Strongly connected groups of code and api steps that contain a loop (Tarjan)."""
    steps = {**workflow.get("nodes", {}), **workflow.get("global_nodes", {})}
    silent = {key for key, node in steps.items() if node.get("node_type") in SILENT_TYPES}
    graph = {key: [target for target, _ in _targets(steps[key]) if target in silent] for key in silent}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[list[str]] = []
    counter = [0]

    def visit(start: str) -> None:
        # Iterative Tarjan: (step, next edge position).
        work = [(start, 0)]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            key, position = work[-1]
            if position < len(graph[key]):
                work[-1] = (key, position + 1)
                target = graph[key][position]
                if target not in index:
                    index[target] = low[target] = counter[0]
                    counter[0] += 1
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, 0))
                elif target in on_stack:
                    low[key] = min(low[key], index[target])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[key])
            if low[key] == index[key]:
                group = []
                while True:
                    item = stack.pop()
                    on_stack.discard(item)
                    group.append(item)
                    if item == key:
                        break
                if len(group) > 1 or key in graph[key]:
                    groups.append(sorted(group))

    for key in sorted(silent):
        if key not in index:
            visit(key)
    return groups


def _counter_names(steps: dict[str, Any], group: list[str]) -> set[str]:
    """The names the engine counts calls under for the api steps of ``group``: node and tool."""
    names = set()
    for key in group:
        node = steps[key]
        if node.get("node_type") != "api_request":
            continue
        names.add(key)
        for action in node.get("pre_actions") or []:
            name = (action.get("function") or {}).get("name") or action.get("name")
            if name:
                names.add(name)
    return names


def counter_guard(condition: dict[str, Any], names: set[str]) -> bool:
    """True when ``condition`` holds once an engine call counter of ``names`` grows: a counter
    leaf, an "or" with such a branch (routes to one target are merged into one "or"), or an
    "and" made only of them."""
    if "conditions" in condition:
        parts = [counter_guard(item, names) for item in condition["conditions"]]
        return any(parts) if condition.get("logic") == "or" else bool(parts) and all(parts)
    return (str(condition.get("operator") or "").startswith("greater_than") and any(
        str(condition.get("variable") or "") == name + suffix for name in names for suffix in COUNTER_SUFFIXES))


def code_cycle_gaps(workflow: dict[str, Any]) -> list[tuple[str, str]]:
    """(cycle, problem) for each loop of silent steps without an exit that holds on engine
    call counters alone (a loop with no api step can have none: the engine counts nothing)."""
    steps = {**workflow.get("nodes", {}), **workflow.get("global_nodes", {})}
    problems = []
    for group in silent_cycles(workflow):
        names = _counter_names(steps, group)
        guarded = any(target not in group and counter_guard(condition, names)
                      for key in group for target, condition in _targets(steps[key]))
        if not guarded:
            what = ("it has no api step, so the engine counts nothing in it" if not names else
                    "no exit holds on the engine's call counters (" + ", ".join(sorted(names)) + ")")
            problems.append(("+".join(group), "a loop of silent steps can run without end when the code sandbox "
                                              "fails: " + what))
    return problems


def sandbox_down_walk(workflow: dict[str, Any], group: list[str], limit: int = 500,
                      result: str = "failure") -> tuple[str, int]:
    """Walk the loop ``group`` with the code sandbox down, as badly as stale variables allow: a
    route that stays in the loop is taken whenever its condition does not hold on counters
    alone, a route out only when its counter part holds. Each api step counts one call under
    its node and tool names, as failed or as successful (``result``). Returns (the step reached outside the loop, or "" when the
    walk did not leave it within ``limit`` steps; the number of api calls)."""
    steps = {**workflow.get("nodes", {}), **workflow.get("global_nodes", {})}
    names_by_step = {key: _counter_names(steps, [key]) for key in group}
    counts: dict[str, int] = {}
    calls = 0
    key = group[0]
    for _ in range(limit):
        if key not in group:
            return key, calls
        node = steps[key]
        if node.get("node_type") == "api_request":
            calls += 1
            for name in names_by_step[key]:
                counts[f"{name}_{result}_count"] = counts.get(f"{name}_{result}_count", 0) + 1
        moved = ""
        for target, condition in _targets(node):
            if target in group:
                moved = target
                break
            if _counter_part_holds(condition, counts):
                moved = target
                break
        if not moved:
            return "", calls
        key = moved
    return "", calls


def _counter_part_holds(condition: dict[str, Any], counts: dict[str, int]) -> bool:
    """Whether ``condition`` holds on the counters alone (every other leaf is taken as false)."""
    if "conditions" in condition:
        parts = [_counter_part_holds(item, counts) for item in condition["conditions"]]
        return any(parts) if condition.get("logic") == "or" else bool(parts) and all(parts)
    variable = str(condition.get("variable") or "")
    if not variable.endswith(COUNTER_SUFFIXES):
        return False
    value = counts.get(variable, 0)
    operand = condition.get("operand")
    try:
        operand = int(operand)
    except (TypeError, ValueError):
        return False
    operator = str(condition.get("operator") or "")
    return value > operand if operator == "greater_than" else value >= operand if operator.startswith("greater_than") else False


def sandbox_down_chain(workflow: dict[str, Any], start: str, limit: int = 2000,
                       result: str = "failure") -> tuple[str, dict[str, int]]:
    """From the silent step ``start`` to the first step that is not silent (``end_call`` or a
    conversation step) with the code sandbox down: inside a loop as ``sandbox_down_walk``, and
    between loops by the first route that holds without code (always, or on counters), else the
    last route. Returns (the step reached, or "" when ``limit`` steps were not enough; api calls
    by step name)."""
    steps = {**workflow.get("nodes", {}), **workflow.get("global_nodes", {})}
    groups = {key: group for group in silent_cycles(workflow) for key in group}
    counts: dict[str, int] = {}
    calls: dict[str, int] = {}
    key = start
    for _ in range(limit):
        node = steps.get(key)
        if node is None or node.get("node_type") not in SILENT_TYPES:
            return key, calls
        if node.get("node_type") == "api_request":
            calls[key] = calls.get(key, 0) + 1
            for name in _counter_names(steps, [key]):
                counts[f"{name}_{result}_count"] = counts.get(f"{name}_{result}_count", 0) + 1
        edges = _targets(node)
        group = groups.get(key)
        moved = ""
        for target, condition in edges:
            if group and target in group:
                moved = target
                break
            if condition.get("operator") == "always" or _counter_part_holds(condition, counts):
                moved = target
                break
        key = moved or (edges[-1][0] if edges else "")
    return "", calls
