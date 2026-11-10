"""
Interfaz de línea de comandos (CLI) principal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from ..detect import (
    detect_os, detect_hardware, classify_hardware,
    detect_windows_os, detect_windows_hardware,
    OSReport, HardwareReport,
)
from ..catalog import load_catalog, ManifestValidator
from ..plan import create_plan, InstallationPlan
from ..state import AuditLog, StateStore, BackupManager
from .formatters import (
    format_hardware_report, format_plan, format_audit_summary,
    format_error, format_warning, format_info, format_success,
    Colors,
)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thorrija",
        description="Thorrija Environment — Provisionador universal de entorno de desarrollo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  thorrija --detect                    # Detecta HW/SO y sugiere perfil
  thorrija --profile standard --plan   # Genera plan (dry-run)
  thorrija --profile standard --yes    # Ejecuta instalación real
  thorrija --category ai --plan        # Solo herramientas de IA
  thorrija --audit                     # Muestra auditoría última sesión
        """,
    )

    # Acciones principales (mutuamente excluyentes)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--detect", action="store_true",
        help="Detecta hardware, SO y clasifica perfil (no instala)"
    )
    action_group.add_argument(
        "--plan", action="store_true",
        help="Genera plan de instalación (dry-run)"
    )
    action_group.add_argument(
        "--yes", action="store_true",
        help="Ejecuta instalación real (requiere confirmación si no se usa --force)"
    )
    action_group.add_argument(
        "--audit", action="store_true",
        help="Muestra resumen de auditoría de la última ejecución"
    )
    action_group.add_argument(
        "--validate", action="store_true",
        help="Valida todos los manifiestos del catálogo"
    )
    action_group.add_argument(
        "--update", action="store_true",
        help="Actualiza catálogo desde GitHub (no implementado en FASE 2)"
    )

    # Filtros
    parser.add_argument(
        "--profile", choices=["low_end", "standard", "high_end", "minimal"],
        help="Forza perfil (por defecto: auto-detectar)"
    )
    parser.add_argument(
        "--category", action="append", choices=["all", "languages", "development", "editors", "ai", "security", "system"],
        help="Filtra por categoría (se puede repetir)"
    )
    parser.add_argument(
        "--include-optional", action="store_true",
        help="Incluye herramientas marcadas como 'optional' en el perfil"
    )
    parser.add_argument(
        "--force-excluded", action="store_true",
        help="Fuerza inclusión de herramientas 'excluded' (peligroso)"
    )

    # Opciones de ejecución
    parser.add_argument(
        "--force", action="store_true",
        help="Omite confirmaciones interactivas (usar con --yes)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fuerza modo dry-run (incompatible con --yes)"
    )
    parser.add_argument(
        "--catalog", type=str, default="catalog",
        help="Ruta al directorio del catálogo (por defecto: ./catalog)"
    )
    parser.add_argument(
        "--profiles-dir", type=str,
        help="Directorio con perfiles TOML personalizados"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Salida verbose"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Salida en JSON (para scripting)"
    )

    return parser


class ThorrijaCLI:
    """Aplicación CLI principal."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.catalog_path = Path(args.catalog).resolve()
        self.profiles_dir = Path(args.profiles_dir).resolve() if args.profiles_dir else None

        # Estado compartido
        self.os_report: Optional[OSReport] = None
        self.hw_report: Optional[HardwareReport] = None
        self.profile: str = ""
        self.manifests: List = []
        self.plan: Optional[InstallationPlan] = None

        # Componentes de estado
        self.audit_log = AuditLog()
        self.state_store = StateStore()
        self.backup_manager = BackupManager()

    def run(self) -> int:
        """Ejecuta la acción solicitada."""
        try:
            # Inicialización común
            self._initialize()

            # Despachar acción
            if self.args.detect:
                return self._cmd_detect()
            elif self.args.plan:
                return self._cmd_plan()
            elif self.args.yes:
                return self._cmd_install()
            elif self.args.audit:
                return self._cmd_audit()
            elif self.args.validate:
                return self._cmd_validate()
            elif self.args.update:
                return self._cmd_update()
            return 1
        except KeyboardInterrupt:
            print(format_warning("\nInterrumpido por usuario"))
            return 130
        except Exception as e:
            print(format_error(f"Error inesperado: {e}"))
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return 1

    def _initialize(self) -> None:
        """Inicialización común: detecta HW/SO, carga catálogo."""
        print(format_info("Inicializando Thorrija Environment..."))

        import sys
        is_windows = sys.platform == "win32"

        # Detectar SO y HW según plataforma
        if is_windows:
            self.os_report = detect_windows_os()
            self.hw_report = detect_windows_hardware()
        else:
            self.os_report = detect_os()
            self.hw_report = detect_hardware()

        # Clasificar perfil
        if self.args.profile:
            self.profile = self.args.profile
        else:
            self.profile = classify_hardware(self.hw_report, profiles_dir=str(self.profiles_dir) if self.profiles_dir else None)

        # Cargar catálogo
        self.manifests = load_catalog(str(self.catalog_path))
        if not self.manifests:
            print(format_warning(f"Catálogo vacío o no encontrado en {self.catalog_path}"))

    def _cmd_detect(self) -> int:
        """Muestra detección de hardware y perfil sugerido."""
        print(format_hardware_report(self.hw_report, self.os_report))
        print()
        print(format_info(f"Perfil sugerido: {self.profile.upper()}"))

        # Explicar clasificación
        from ..detect import ProfileClassifier
        classifier = ProfileClassifier(str(self.profiles_dir) if self.profiles_dir else None)
        explanations = classifier.explain_classification(self.hw_report)

        print(f"\n{format_info('Detalle de clasificacion:')}")
        for name, info in explanations.items():
            status = "Coincide" if info["matches"] else "No coincide"
            color = Colors.GREEN if info["matches"] else Colors.RED
            print(f"  {color}{status}{Colors.RESET} {name}: {', '.join(info['reasons'][:2])}")

        return 0

    def _cmd_plan(self) -> int:
        """Genera y muestra plan de instalación (dry-run)."""
        self._generate_plan()
        print(format_plan(self.plan, show_all=self.args.verbose))
        return 0

    def _cmd_install(self) -> int:
        """Ejecuta instalación real."""
        if self.args.dry_run:
            print(format_error("--yes y --dry-run son incompatibles"))
            return 1

        self._generate_plan()

        # Mostrar plan
        print(format_plan(self.plan))

        # Confirmación
        if not self.args.force and not self.args.yes:
            enabled = len(self.plan.get_enabled_entries())
            optional = len(self.plan.get_optional_entries())
            print(f"\n{format_warning('Resumen:')} {enabled} herramientas se instalarán, {optional} opcionales.")
            if self.plan.requires_sudo:
                print(format_warning("Esta operación requiere sudo."))
            confirm = input("¿Continuar? [s/N]: ").strip().lower()
            if confirm not in ("s", "si", "sí", "y", "yes"):
                print(format_info("Cancelado por usuario"))
                return 0

        # Iniciar sesión de auditoría
        self.audit_log.start_session()
        self.backup_manager.start_session()

        # Ejecutar instalación
        print(format_info("\nIniciando instalación..."))
        return self._execute_plan()

    def _generate_plan(self) -> None:
        """Genera plan de instalación."""
        categories = self.args.category or ["all"]
        if "all" in categories:
            categories = None

        self.plan = create_plan(
            manifests=self.manifests,
            hw=self.hw_report,
            os_report=self.os_report,
            profile=self.profile,
            categories=categories,
            include_optional=self.args.include_optional,
            force_excluded=self.args.force_excluded,
        )
        self.plan.dry_run = not self.args.yes

    def _execute_plan(self) -> int:
        """Ejecuta el plan usando el motor de instalación."""
        from ..install import InstallationEngine, driver_registry

        # Registrar drivers
        from ..install.drivers import native, binary_release, git_clone, script_official, pipx  # noqa

        engine = InstallationEngine(
            driver_registry=driver_registry,
            audit_log=self.audit_log,
            backup_manager=self.backup_manager,
            state_store=self.state_store,
        )

        results = engine.execute_plan(self.plan)

        # Guardar manifiesto de backup
        self.backup_manager.save_manifest()

        # Resumen final
        success = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        skipped = sum(1 for r in results if r.success and r.method == "already_installed")

        print(f"\n{format_success('=== Instalación completada ===')}")
        print(f"  Exitosas:     {success}")
        print(f"  Fallidas:     {failed}")
        print(f"  Ya instaladas: {skipped}")

        if failed > 0:
            print(f"\n{format_error('Herramientas fallidas:')}")
            for r in results:
                if not r.success:
                    print(f"  - {r.tool_name} ({r.method}): {r.error}")
            return 1

        return 0

    def _cmd_audit(self) -> int:
        """Muestra auditoría."""
        sessions = self.audit_log.list_sessions()
        if not sessions:
            print(format_warning("No hay sesiones de auditoría registradas"))
            return 0

        latest = sessions[0]
        entries = self.audit_log.read_session(latest)
        print(format_audit_summary(entries))

        if self.args.verbose:
            print(f"\n{format_info('Últimas 20 entradas:')}")
            for e in entries[-20:]:
                status_color = format_success if e.get("result") in ("installed", "already_installed") else format_error
                print(f"  {e['ts']} | {e['tool']:15} | {status_color(e['result']):20} | {e['method']}")
        return 0

    def _cmd_validate(self) -> int:
        """Valida manifiestos."""
        print(format_info(f"Validando manifiestos en {self.catalog_path}..."))
        validator = ManifestValidator()
        results = validator.validate_all(self.catalog_path)

        total = len(results)
        valid = sum(1 for r in results if r.valid)
        invalid = total - valid

        print(f"\nTotal: {total} | Válidos: {format_success(str(valid))} | Inválidos: {format_error(str(invalid))}")

        for r in results:
            if not r.valid:
                print(f"\n{format_error(r.file)}:")
                for err in r.errors:
                    print(f"  - {err}")
            for warn in r.warnings:
                print(f"  {format_warning(r.file)}: {warn}")

        return 0 if invalid == 0 else 1

    def _cmd_update(self) -> int:
        print(format_warning("Actualización de catálogo no implementada en FASE 2"))
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    cli = ThorrijaCLI(args)
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())