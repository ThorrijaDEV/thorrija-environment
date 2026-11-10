"""
Validador de manifiestos TOML según esquema formal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


@dataclass(frozen=True)
class ValidationError(Exception):
    """Error de validación con ubicación."""
    file: str
    message: str
    path: str = ""

    def __init__(self, file: str, message: str, path: str = ""):
        object.__setattr__(self, "file", file)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "path", path)
        super().__init__(f"{file}{':' + path + ' ' if path else ' '}{message}")


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de validación de un manifiesto."""
    file: str
    valid: bool
    errors: List[str]
    warnings: List[str]

    def __bool__(self) -> bool:
        return self.valid


class ManifestValidator:
    """Valida manifiestos contra el esquema formal (docs/MANIFESTS.md)."""

    NAME_REGEX = re.compile(r"^[a-z][a-z0-9-]*$")
    SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$")
    URL_REGEX = re.compile(r"^https?://")

    VALID_CATEGORIES = {"languages", "development", "editors", "ai", "security", "system"}
    VALID_PROFILE_VALUES = {"enabled", "optional", "excluded"}
    VALID_GPU_VALUES = {"none", "optional", "required"}
    VALID_SIZE_CLASSES = {"tiny", "small", "medium", "large", "auto"}
    VALID_INSTALL_METHODS = {"native", "binary_release", "git_clone", "script_official", "pipx"}
    NATIVE_PKG_FAMILIES = {"arch", "debian", "fedora", "void", "opensuse", "alpine", "gentoo"}

    def __init__(self):
        self.results: List[ValidationResult] = []

    def validate_file(self, path: Path) -> ValidationResult:
        """Valida un archivo de manifiesto."""
        errors = []
        warnings = []

        if tomllib is None:
            errors.append("tomllib/tomli no disponible")
            return ValidationResult(str(path), False, errors, warnings)

        # Parsear
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            errors.append(f"Error parseando TOML: {e}")
            return ValidationResult(str(path), False, errors, warnings)

        # Validaciones
        self._validate_schema_version(data, errors)
        self._validate_tool_section(data, errors, str(path))
        self._validate_requirements(data, errors)
        self._validate_profiles(data, errors)
        self._validate_install(data, errors, warnings, str(path))
        self._validate_verify(data, errors)
        self._validate_ai_models(data, errors, warnings)
        self._validate_name_consistency(data, path, errors)

        valid = len(errors) == 0
        result = ValidationResult(str(path), valid, errors, warnings)
        self.results.append(result)
        return result

    def validate_all(self, catalog_root: Path) -> List[ValidationResult]:
        """Valida todos los manifiestos en el catálogo."""
        self.results = []
        for category_dir in catalog_root.iterdir():
            if not category_dir.is_dir():
                continue
            for toml_file in category_dir.glob("*.toml"):
                self.validate_file(toml_file)
        return self.results

    def _validate_schema_version(self, data: Dict, errors: List[str]) -> None:
        sv = data.get("schema_version")
        if sv != 1:
            errors.append(f"schema_version debe ser 1 (encontrado: {sv})")

    def _validate_tool_section(self, data: Dict, errors: List[str], file: str) -> None:
        tool = data.get("tool")
        if not tool or not isinstance(tool, dict):
            errors.append("[tool] requerido y debe ser tabla")
            return

        name = tool.get("name")
        if not name or not isinstance(name, str):
            errors.append("[tool].name: requerido, string")
        elif not self.NAME_REGEX.match(name):
            errors.append(f"[tool].name: '{name}' no matchea ^[a-z][a-z0-9-]*$")

        category = tool.get("category")
        if not category or not isinstance(category, str):
            errors.append("[tool].category: requerido, string")
        elif category not in self.VALID_CATEGORIES:
            errors.append(f"[tool].category: '{category}' inválido. Válidos: {sorted(self.VALID_CATEGORIES)}")

        desc = tool.get("description")
        if not desc or not isinstance(desc, str):
            errors.append("[tool].description: requerido, string")
        elif len(desc) < 10 or len(desc) > 500:
            errors.append("[tool].description: longitud 10-500 chars")

        homepage = tool.get("homepage", "")
        if homepage and not self.URL_REGEX.match(homepage):
            errors.append(f"[tool].homepage: '{homepage}' no es URL válida")

        tags = tool.get("tags", [])
        if tags and not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
            errors.append("[tool].tags: debe ser array de strings")

    def _validate_requirements(self, data: Dict, errors: List[str]) -> None:
        req = data.get("requirements", {})
        if not isinstance(req, dict):
            errors.append("[requirements]: debe ser tabla")
            return

        # Validar enteros positivos
        for field, default in [
            ("ram_run_mb", 100), ("ram_optimal_mb", 200),
            ("disk_install_mb", 50), ("disk_run_mb", 50),
            ("cpu_cores_min", 1),
        ]:
            val = req.get(field, default)
            if not isinstance(val, int) or val <= 0:
                errors.append(f"[requirements].{field}: entero > 0 requerido")

        gpu = req.get("gpu", "none")
        if gpu not in self.VALID_GPU_VALUES:
            errors.append(f"[requirements].gpu: '{gpu}' inválido. Válidos: {sorted(self.VALID_GPU_VALUES)}")

        cpu_arch = req.get("cpu_arch", ["x86_64", "aarch64"])
        if not isinstance(cpu_arch, list) or not all(isinstance(a, str) for a in cpu_arch):
            errors.append("[requirements].cpu_arch: array de strings")

        priv = req.get("privileged", True)
        if not isinstance(priv, bool):
            errors.append("[requirements].privileged: boolean")

        size_cls = req.get("size_class", "auto")
        if size_cls not in self.VALID_SIZE_CLASSES:
            errors.append(f"[requirements].size_class: '{size_cls}' inválido. Válidos: {sorted(self.VALID_SIZE_CLASSES)}")

        net = req.get("network_required", True)
        if not isinstance(net, bool):
            errors.append("[requirements].network_required: boolean")

        py_min = req.get("python_min", "")
        if py_min and not isinstance(py_min, str):
            errors.append("[requirements].python_min: string")

    def _validate_profiles(self, data: Dict, errors: List[str]) -> None:
        profiles = data.get("profiles")
        if not profiles or not isinstance(profiles, dict):
            errors.append("[profiles]: requerido, tabla")
            return

        for key in ("low_end", "standard", "high_end"):
            val = profiles.get(key)
            if val is None:
                errors.append(f"[profiles].{key}: requerido")
            elif val not in self.VALID_PROFILE_VALUES:
                errors.append(f"[profiles].{key}: '{val}' inválido. Válidos: {sorted(self.VALID_PROFILE_VALUES)}")

        extra = set(profiles.keys()) - {"low_end", "standard", "high_end"}
        if extra:
            errors.append(f"[profiles]: claves extra no permitidas: {sorted(extra)}")

    def _validate_install(self, data: Dict, errors: List[str], warnings: List[str], file: str) -> None:
        install = data.get("install")
        if not install or not isinstance(install, dict):
            errors.append("[install]: requerido, tabla con al menos un método")
            return

        methods_present = set(install.keys()) & self.VALID_INSTALL_METHODS
        if not methods_present:
            errors.append(f"[install]: debe tener al menos uno de {sorted(self.VALID_INSTALL_METHODS)}")

        for method in methods_present:
            mdata = install[method]
            if not isinstance(mdata, dict):
                errors.append(f"[install.{method}]: debe ser tabla")
                continue

            if method == "native":
                families = set(mdata.keys()) & self.NATIVE_PKG_FAMILIES
                if not families:
                    errors.append("[install.native]: debe tener al menos una familia (arch, debian, fedora, void, opensuse, alpine, gentoo)")
                for fam, pkg in mdata.items():
                    if fam in self.NATIVE_PKG_FAMILIES:
                        if pkg is not None and not isinstance(pkg, str):
                            errors.append(f"[install.native].{fam}: string o null")
                    else:
                        warnings.append(f"[install.native].{fam}: familia no estándar (ignorada en validación)")

            elif method == "binary_release":
                for field in ("url_template", "version", "sha256"):
                    if field not in mdata:
                        errors.append(f"[install.binary_release].{field}: requerido")

                sha256 = mdata.get("sha256", {})
                if not isinstance(sha256, dict) or not sha256:
                    errors.append("[install.binary_release].sha256: tabla requerida con ≥1 entrada")
                else:
                    for arch, hash_val in sha256.items():
                        if not isinstance(hash_val, str):
                            errors.append(f"[install.binary_release].sha256.{arch}: string requerido")
                        elif hash_val.upper() == "PENDING-VERIFICATION":
                            warnings.append(f"{file}: binary_release.sha256.{arch} = PENDING-VERIFICATION (método deshabilitado hasta pinnear hash real)")
                        elif len(hash_val) != 64 or not all(c in "0123456789abcdef" for c in hash_val.lower()):
                            errors.append(f"[install.binary_release].sha256.{arch}: hash hex de 64 chars requerido")

                ver = mdata.get("version", "")
                if ver and not self.SEMVER_REGEX.match(ver):
                    errors.append(f"[install.binary_release].version: '{ver}' no es semver válido")

            elif method == "git_clone":
                for field in ("url", "build_system", "binary_path"):
                    if field not in mdata:
                        errors.append(f"[install.git_clone].{field}: requerido")
                build_sys = mdata.get("build_system", "")
                if build_sys not in {"make", "cargo", "go", "cmake", "meson", "custom"}:
                    errors.append(f"[install.git_clone].build_system: '{build_sys}' inválido")

            elif method == "script_official":
                for field in ("url", "sha256"):
                    if field not in mdata:
                        errors.append(f"[install.script_official].{field}: requerido")
                sha = mdata.get("sha256", "")
                if sha and sha.upper() != "PENDING-VERIFICATION" and (not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha.lower())):
                    errors.append("[install.script_official].sha256: hash hex de 64 chars requerido")
                if sha.upper() == "PENDING-VERIFICATION":
                    warnings.append(f"{file}: script_official.sha256 = PENDING-VERIFICATION (método deshabilitado hasta pinnear hash real)")

            elif method == "pipx":
                if "package" not in mdata:
                    errors.append("[install.pipx].package: requerido")
                pkg = mdata.get("package", "")
                if pkg and not isinstance(pkg, str):
                    errors.append("[install.pipx].package: string")

    def _validate_verify(self, data: Dict, errors: List[str]) -> None:
        verify = data.get("verify")
        if not verify or not isinstance(verify, dict):
            errors.append("[verify]: requerido, tabla")
            return

        for field in ("command", "pattern"):
            val = verify.get(field)
            if not val or not isinstance(val, str):
                errors.append(f"[verify].{field}: requerido, string no vacío")

        exit_code = verify.get("exit_code", 0)
        if not isinstance(exit_code, int):
            errors.append("[verify].exit_code: entero")

        timeout = verify.get("timeout_sec", 10)
        if not isinstance(timeout, int) or timeout <= 0:
            errors.append("[verify].timeout_sec: entero > 0")

    def _validate_ai_models(self, data: Dict, errors: List[str], warnings: List[str]) -> None:
        ai = data.get("ai_models")
        if ai is None:
            return

        if not isinstance(ai, dict):
            errors.append("[ai_models]: debe ser tabla")
            return

        auto = ai.get("automatic", False)
        if not isinstance(auto, bool):
            errors.append("[ai_models].automatic: boolean")
        elif auto is True:
            errors.append("[ai_models].automatic: debe ser false (el proyecto prohíbe descarga automática de modelos)")

        models = ai.get("default_models", [])
        if models and not (isinstance(models, list) and all(isinstance(m, str) for m in models)):
            errors.append("[ai_models].default_models: array de strings")

        req_conf = ai.get("requires_confirmation", True)
        if not isinstance(req_conf, bool):
            errors.append("[ai_models].requires_confirmation: boolean")

    def _validate_name_consistency(self, data: Dict, path: Path, errors: List[str]) -> None:
        tool_name = data.get("tool", {}).get("name")
        file_stem = path.stem
        if tool_name and tool_name != file_stem:
            errors.append(f"[tool].name ('{tool_name}') != nombre de archivo ('{file_stem}')")


def validate_manifest(path: Path) -> ValidationResult:
    """Función de conveniencia."""
    return ManifestValidator().validate_file(path)


__all__ = [
    "ManifestValidator",
    "ValidationResult",
    "ValidationError",
    "validate_manifest",
]