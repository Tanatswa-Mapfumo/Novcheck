"""Deterministic strongly-connected components for provenance analysis.

Internal helper shared by lineage clustering and circularity diagnostics.
"""

from collections.abc import Mapping, Sequence


def strongly_connected_components(
    nodes: Sequence[str], edges: Mapping[str, Sequence[str]]
) -> list[tuple[str, ...]]:
    """Tarjan's algorithm with deterministic ordering and no recursion limits.

    ``edges`` maps a node to its outgoing neighbours. Nodes referenced only as
    neighbours are ignored unless they appear in ``nodes``; callers pass the
    complete node set.
    """

    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[tuple[str, ...]] = []
    counter = 0

    def iterate(node: str) -> None:
        nonlocal counter
        # Iterative Tarjan: the stack holds (node, neighbour iterator).
        work: list[tuple[str, int]] = [(node, 0)]
        index_of[node] = counter
        lowlink[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)

        while work:
            current, position = work[-1]
            neighbours = edges.get(current, ())
            if position < len(neighbours):
                work[-1] = (current, position + 1)
                neighbour = neighbours[position]
                if neighbour not in nodes:
                    continue
                if neighbour not in index_of:
                    index_of[neighbour] = counter
                    lowlink[neighbour] = counter
                    counter += 1
                    stack.append(neighbour)
                    on_stack.add(neighbour)
                    work.append((neighbour, 0))
                elif neighbour in on_stack:
                    lowlink[current] = min(lowlink[current], index_of[neighbour])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[current])
                if lowlink[current] == index_of[current]:
                    component: list[str] = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == current:
                            break
                    components.append(tuple(sorted(component)))

    ordered_nodes = list(dict.fromkeys(nodes))
    for node in sorted(ordered_nodes):
        if node not in index_of:
            iterate(node)
    return sorted(components, key=lambda component: component[0])
