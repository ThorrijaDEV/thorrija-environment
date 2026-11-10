"""
Planificación de instalaciones: planner y grafo de dependencias.
"""

from .planner import (
    InstallationPlanner,
    InstallationPlan,
    ToolPlanEntry,
    CompatibilityClass,
    create_plan,
)
from .depgraph import DependencyGraph, build_dependency_graph

__all__ = [
    "InstallationPlanner",
    "InstallationPlan",
    "ToolPlanEntry",
    "CompatibilityClass",
    "create_plan",
    "DependencyGraph",
    "build_dependency_graph",
]