"""
Resolución de dependencias entre herramientas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque

from .loader import ToolManifest


@dataclass(frozen=True)
class DependencyEdge:
    """Arista de dependencia: tool_a requiere tool_b."""
    source: str      # herramienta que depende
    target: str      # herramienta requerida
    reason: str      # "build", "runtime", "plugin", etc.
    optional: bool = False


@dataclass
class ResolvedPlan:
    """Resultado de la resolución de dependencias."""
    # Orden topológico de instalación
    install_order: List[str]
    # Dependencias resueltas por herramienta
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    # Herramientas excluidas por conflictos/ciclos
    excluded: List[str] = field(default_factory=list)
    # Advertencias
    warnings: List[str] = field(default_factory=list)


class DependencyResolver:
    """
    Resuelve dependencias entre herramientas y genera orden de instalación.

    Las dependencias se declaran en el manifiesto como:
    [dependencies]
    runtime = ["python", "git"]
    build = ["rust", "cmake"]
    """

    def __init__(self, manifests: List[ToolManifest]):
        self.manifests = {m.name: m for m in manifests}
        self.edges: List[DependencyEdge] = []
        self._build_graph()

    def _build_graph(self) -> None:
        """Construye grafo de dependencias desde manifiestos."""
        for manifest in self.manifests.values():
            # Las dependencias pueden venir de metadatos extra o inferirse
            # Por ahora: inferir de category y requirements
            self._infer_dependencies(manifest)

    def _infer_dependencies(self, manifest: ToolManifest) -> None:
        """Infiere dependencias básicas basadas en categoría y requisitos."""
        name = manifest.name

        # Python tools necesitan python
        if manifest.category in ("ai", "development") and "python" in self.manifests:
            if manifest.name != "python":
                self.edges.append(DependencyEdge(name, "python", "runtime"))

        # Build tools
        build_deps = {
            "rust": ["cargo"],
            "go": [],
            "cmake": [],
            "make": [],
        }
        for tool, deps in build_deps.items():
            if tool in self.manifests and name != tool:
                for dep in deps:
                    if dep in self.manifests:
                        self.edges.append(DependencyEdge(name, dep, "build"))

        # Git para clonar
        if "git" in self.manifests and name != "git":
            # Solo si usa git_clone
            if "git_clone" in manifest.install_methods:
                self.edges.append(DependencyEdge(name, "git", "install"))

    def resolve(self, selected_tools: List[str]) -> ResolvedPlan:
        """
        Resuelve dependencias para las herramientas seleccionadas.
        Retorna orden topológico de instalación.
        """
        # Subgrafo relevante
        relevant = set(selected_tools)
        # Añadir dependencias transitivas
        queue = list(selected_tools)
        while queue:
            tool = queue.pop(0)
            for edge in self.edges:
                if edge.source == tool and edge.target not in relevant:
                    relevant.add(edge.target)
                    queue.append(edge.target)

        # Kahn's algorithm para orden topológico
        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in self.edges:
            if edge.source in relevant and edge.target in relevant:
                adj[edge.target].append(edge.source)
                in_degree[edge.source] += 1
                if edge.target not in in_degree:
                    in_degree[edge.target] = 0

        # Nodos sin dependencias
        zero_degree = deque([n for n in relevant if in_degree[n] == 0])
        order = []
        processed = set()

        while zero_degree:
            node = zero_degree.popleft()
            order.append(node)
            processed.add(node)

            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    zero_degree.append(neighbor)

        # Detectar ciclos
        if len(processed) != len(relevant):
            # Ciclo detectado: romper arbitrariamente
            remaining = relevant - processed
            warnings = [f"Ciclo detectado en dependencias: {', '.join(remaining)}. Orden parcial usado."]
            # Añadir restantes al final
            for node in remaining:
                if node not in order:
                    order.append(node)
        else:
            warnings = []

        # Construir mapa de dependencias por herramienta
        deps_map = defaultdict(list)
        for edge in self.edges:
            if edge.source in relevant:
                deps_map[edge.source].append(edge.target)

        return ResolvedPlan(
            install_order=order,
            dependencies=dict(deps_map),
            warnings=warnings,
        )

    def get_dependencies(self, tool: str, transitive: bool = True) -> List[str]:
        """Obtiene dependencias directas (y transitivas) de una herramienta."""
        if not transitive:
            return [e.target for e in self.edges if e.source == tool]

        # BFS para transitivas
        result = set()
        queue = [tool]
        while queue:
            current = queue.pop(0)
            for edge in self.edges:
                if edge.source == current and edge.target not in result:
                    result.add(edge.target)
                    queue.append(edge.target)
        return list(result)


def resolve_dependencies(manifests: List[ToolManifest], selected: List[str]) -> ResolvedPlan:
    """Función de conveniencia."""
    return DependencyResolver(manifests).resolve(selected)