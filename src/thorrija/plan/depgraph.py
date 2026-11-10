"""
Grafo de dependencias para planificación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from collections import defaultdict, deque

from ..catalog import ToolManifest, DependencyEdge, ResolvedPlan


@dataclass
class DependencyGraph:
    """Grafo dirigido de dependencias entre herramientas."""
    nodes: Set[str] = field(default_factory=set)
    edges: List[DependencyEdge] = field(default_factory=list)
    _adj: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    _rev_adj: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    def add_node(self, name: str) -> None:
        self.nodes.add(name)

    def add_edge(self, edge: DependencyEdge) -> None:
        self.add_node(edge.source)
        self.add_node(edge.target)
        self.edges.append(edge)
        self._adj[edge.target].append(edge.source)
        self._rev_adj[edge.source].append(edge.target)

    def get_dependencies(self, tool: str, transitive: bool = True) -> List[str]:
        """Dependencias de una herramienta (directas + transitivas)."""
        if not transitive:
            return list(self._rev_adj.get(tool, []))

        visited = set()
        stack = [tool]
        while stack:
            current = stack.pop()
            for dep in self._rev_adj.get(current, []):
                if dep not in visited:
                    visited.add(dep)
                    stack.append(dep)
        return list(visited)

    def get_dependents(self, tool: str, transitive: bool = True) -> List[str]:
        """Herramientas que dependen de esta (directas + transitivas)."""
        if not transitive:
            return list(self._adj.get(tool, []))

        visited = set()
        stack = [tool]
        while stack:
            current = stack.pop()
            for dep in self._adj.get(current, []):
                if dep not in visited:
                    visited.add(dep)
                    stack.append(dep)
        return list(visited)

    def topological_order(self, subset: Optional[Set[str]] = None) -> List[str]:
        """Orden topológico (Kahn). Si subset, solo esos nodos + sus dependencias."""
        relevant = subset or self.nodes.copy()
        # Expandir con dependencias transitivas
        expanded = set(relevant)
        for node in relevant:
            expanded.update(self.get_dependencies(node))

        in_degree = defaultdict(int)
        for node in expanded:
            for dep in self._rev_adj.get(node, []):
                if dep in expanded:
                    in_degree[node] += 1
            if node not in in_degree:
                in_degree[node] = 0

        queue = deque([n for n in expanded if in_degree[n] == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in self._adj.get(node, []):
                if neighbor in expanded:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if len(order) != len(expanded):
            # Ciclo: añadir restantes
            remaining = expanded - set(order)
            order.extend(sorted(remaining))

        return order

    def has_cycles(self) -> bool:
        """Detecta ciclos en el grafo."""
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in self._adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for node in self.nodes:
            if node not in visited:
                if dfs(node):
                    return True
        return False

    def find_cycles(self) -> List[List[str]]:
        """Encuentra todos los ciclos (para diagnóstico)."""
        cycles = []
        visited = set()
        path = []
        path_set = set()

        def dfs(node: str):
            visited.add(node)
            path.append(node)
            path_set.add(node)

            for neighbor in self._adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in path_set:
                    # Ciclo encontrado
                    idx = path.index(neighbor)
                    cycles.append(path[idx:] + [neighbor])

            path.pop()
            path_set.remove(node)

        for node in self.nodes:
            if node not in visited:
                dfs(node)
        return cycles


def build_dependency_graph(manifests: List[ToolManifest]) -> DependencyGraph:
    """Construye grafo desde lista de manifiestos."""
    graph = DependencyGraph()
    # Los edges ya vienen del resolver, pero podemos reconstruir aquí
    name_to_manifest = {m.name: m for m in manifests}

    for manifest in manifests:
        graph.add_node(manifest.name)
        # Inferir dependencias básicas
        if manifest.category in ("ai", "development") and "python" in name_to_manifest:
            if manifest.name != "python":
                graph.add_edge(DependencyEdge(manifest.name, "python", "runtime"))

    return graph