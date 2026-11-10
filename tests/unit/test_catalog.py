"""
Tests unitarios para catálogo: loader, validator, resolver.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from thorrija.catalog import (
    load_catalog, ManifestLoader, ToolManifest,
    ManifestValidator, validate_manifest,
    DependencyResolver, resolve_dependencies,
)


CATALOG_DIR = Path(__file__).parent.parent.parent / "catalog"


def test_load_catalog_finds_manifests():
    """Carga catálogo y encuentra los 3 manifiestos de ejemplo."""
    manifests = load_catalog(str(CATALOG_DIR))
    assert len(manifests) == 3

    names = {m.name for m in manifests}
    assert names == {"git", "python", "ollama"}


def test_manifest_structure_git():
    """Estructura del manifiesto git."""
    manifests = load_catalog(str(CATALOG_DIR))
    git = next(m for m in manifests if m.name == "git")

    assert git.category == "development"
    assert git.description
    assert git.ram_run_mb == 50
    assert git.gpu == "none"
    assert git.privileged is True

    # Perfiles
    assert git.get_profile_status("low_end") == "enabled"
    assert git.get_profile_status("standard") == "enabled"
    assert git.get_profile_status("high_end") == "enabled"

    # Métodos
    assert "native" in git.install_methods
    native = git.install_methods["native"]
    assert native["arch"] == "git"
    assert native["debian"] == "git"
    assert native["fedora"] == "git"
    assert native["void"] == "git"

    # Verificación
    assert git.verify_command == "git --version"
    assert git.verify_pattern == "git version"


def test_manifest_structure_python():
    """Estructura del manifiesto python."""
    manifests = load_catalog(str(CATALOG_DIR))
    python = next(m for m in manifests if m.name == "python")

    assert python.category == "languages"
    assert python.python_min == "3.9"
    assert python.get_profile_status("low_end") == "enabled"

    native = python.install_methods["native"]
    assert native["arch"] == "python"
    assert native["debian"] == "python3"
    assert native["fedora"] == "python3"
    assert native["void"] == "python3.11"  # assumed


def test_manifest_structure_ollama():
    """Estructura del manifiesto ollama."""
    manifests = load_catalog(str(CATALOG_DIR))
    ollama = next(m for m in manifests if m.name == "ollama")

    assert ollama.category == "ai"
    assert ollama.ram_run_mb == 8192
    assert ollama.ram_optimal_mb == 24576
    assert ollama.gpu == "optional"
    assert ollama.privileged is False
    assert ollama.size_class == "large"

    # Perfiles
    assert ollama.get_profile_status("low_end") == "excluded"
    assert ollama.get_profile_status("standard") == "optional"
    assert ollama.get_profile_status("high_end") == "enabled"

    # Métodos
    assert "native" in ollama.install_methods
    assert ollama.install_methods["native"].get("arch") == "ollama"
    assert ollama.install_methods["native"].get("debian") is None

    assert "binary_release" in ollama.install_methods
    br = ollama.install_methods["binary_release"]
    assert "sha256" in br
    assert br["sha256"]["x86_64"] == "PENDING-VERIFICATION"

    # AI models
    assert ollama.ai_automatic is False
    assert ollama.ai_requires_confirmation is True


def test_validate_all_manifests_pass():
    """Validador: todos los manifiestos pasan (warnings esperados para ollama)."""
    validator = ManifestValidator()
    results = validator.validate_all(CATALOG_DIR)

    assert len(results) == 3
    for r in results:
        assert r.valid is True, f"Manifiesto inválido: {r.file} - {r.errors}"

    # Verificar warnings de ollama
    ollama_result = next(r for r in results if "ollama" in r.file)
    assert len(ollama_result.warnings) == 2
    for w in ollama_result.warnings:
        assert "PENDING-VERIFICATION" in w


def test_filter_by_category():
    """Filtrado por categoría."""
    manifests = load_catalog(str(CATALOG_DIR))
    loader = ManifestLoader(str(CATALOG_DIR))

    dev_tools = loader.filter_by_category(manifests, "development")
    assert len(dev_tools) == 1
    assert dev_tools[0].name == "git"

    ai_tools = loader.filter_by_category(manifests, "ai")
    assert len(ai_tools) == 1
    assert ai_tools[0].name == "ollama"

    lang_tools = loader.filter_by_category(manifests, "languages")
    assert len(lang_tools) == 1
    assert lang_tools[0].name == "python"


def test_filter_by_profile():
    """Filtrado por perfil."""
    manifests = load_catalog(str(CATALOG_DIR))
    loader = ManifestLoader(str(CATALOG_DIR))

    # low_end: solo git y python (ollama excluded)
    low = loader.filter_by_profile(manifests, "low_end")
    names = {m.name for m in low}
    assert names == {"git", "python"}

    # standard: git, python, ollama (optional)
    std = loader.filter_by_profile(manifests, "standard")
    names = {m.name for m in std}
    assert names == {"git", "python", "ollama"}

    # high_end: todos
    high = loader.filter_by_profile(manifests, "high_end")
    names = {m.name for m in high}
    assert names == {"git", "python", "ollama"}


def test_dependency_resolver_basic():
    """Resolver de dependencias básico."""
    manifests = load_catalog(str(CATALOG_DIR))
    resolver = DependencyResolver(manifests)

    # git no debería tener dependencias inferidas
    plan = resolver.resolve(["git"])
    assert "git" in plan.install_order

    # python como dependencia
    # (actualmente el resolver infiere python para ai/development)
    plan = resolver.resolve(["ollama"])
    assert "ollama" in plan.install_order
    # python puede o no estar según inferencia actual


def test_resolve_dependencies_convenience():
    """Función de conveniencia resolve_dependencies."""
    manifests = load_catalog(str(CATALOG_DIR))
    plan = resolve_dependencies(manifests, ["git", "python"])
    assert isinstance(plan.install_order, list)
    assert set(plan.install_order) >= {"git", "python"}


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])