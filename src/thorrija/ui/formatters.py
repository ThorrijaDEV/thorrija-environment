"""
Formateadores de salida para CLI.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from ..plan import InstallationPlan, ToolPlanEntry, CompatibilityClass
from ..detect import HardwareReport, OSReport


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"

    @classmethod
    def enabled(cls) -> bool:
        import sys
        return sys.stdout.isatty()

    @classmethod
    def colorize(cls, text: str, color: str) -> str:
        if cls.enabled():
            return f"{color}{text}{cls.RESET}"
        return text


def format_hardware_report(hw: HardwareReport, os_report: OSReport) -> str:
    lines = []
    c = Colors

    lines.append(f"{c.BOLD}=== Hardware detectado ==={c.RESET}")
    lines.append(f"  Hostname:     {hw.hostname}")
    lines.append(f"  Kernel:       {hw.kernel}")
    lines.append(f"  Arquitectura: {hw.architecture}")
    lines.append("")
    lines.append(f"  CPU:          {hw.cpu.model}")
    lines.append(f"  Cores/Threads: {hw.cpu.cores} / {hw.cpu.threads}")
    lines.append(f"  Vendor:       {hw.cpu.vendor}")
    lines.append("")
    lines.append(f"  RAM total:    {hw.memory.total_mb} MB")
    lines.append(f"  RAM disponible: {hw.memory.available_mb} MB")
    lines.append(f"  Swap:         {hw.memory.swap_total_mb} MB")
    lines.append("")

    if hw.gpus and hw.gpus[0].vendor != "none":
        lines.append(f"  GPUs:")
        for gpu in hw.gpus:
            vram = f" ({gpu.vram_mb} MB VRAM)" if gpu.vram_mb > 0 else ""
            dedicated = " [DEDICADA]" if gpu.is_dedicated else ""
            lines.append(f"    - {gpu.vendor.upper()}: {gpu.model}{vram}{dedicated}")
    else:
        lines.append(f"  GPU:          No detectada / Integrada")
    lines.append("")

    if hw.disks:
        lines.append(f"  Discos:")
        for disk in hw.disks:
            ssd = " (SSD)" if disk.is_ssd else " (HDD)"
            lines.append(f"    {disk.path}: {disk.total_mb} MB total, {disk.free_mb} MB libre{ssd}")
    lines.append("")

    lines.append(f"{c.BOLD}=== Sistema Operativo ==={c.RESET}")
    lines.append(f"  Distro:       {os_report.pretty_name}")
    lines.append(f"  ID:           {os_report.id} ({os_report.version})")
    lines.append(f"  Gestor pkg:   {os_report.package_manager}")
    lines.append(f"  Familias:     {', '.join(os_report.package_families) if os_report.package_families else 'ninguna'}")
    lines.append(f"  Soporte:      {os_report.support_level.upper()}")

    return "\n".join(lines)


def format_plan(plan: InstallationPlan, show_all: bool = False) -> str:
    lines = []
    c = Colors

    lines.append(f"{c.BOLD}=== Plan de instalacion ==={c.RESET}")
    lines.append(f"  Perfil:           {plan.profile.upper()}")
    lines.append(f"  Total herramientas: {len(plan.entries)}")
    lines.append(f"  Descarga estimada:  {plan.total_download_mb} MB")
    lines.append(f"  Disco estimado:     {plan.total_disk_mb} MB")
    lines.append(f"  Requiere sudo:      {'Si' if plan.requires_sudo else 'No'}")
    lines.append(f"  Modo:             {'DRY-RUN' if plan.dry_run else 'EJECUCION REAL'}")
    lines.append("")

    if plan.sudo_operations:
        lines.append(f"{c.YELLOW}Operaciones que requieren sudo:{c.RESET}")
        for op in plan.sudo_operations:
            lines.append(f"  - {op}")
        lines.append("")

    if not show_all:
        entries = [e for e in plan.entries if e.status in ("will_install", "optional")]
        excluded_count = len([e for e in plan.entries if e.status == "excluded"])
        incompatible_count = len([e for e in plan.entries if e.compatibility == CompatibilityClass.INCOMPATIBLE])
        if excluded_count:
            lines.append(f"{c.GRAY}({excluded_count} herramientas excluidas por perfil ocultas){c.RESET}")
        if incompatible_count:
            lines.append(f"{c.RED}({incompatible_count} herramientas incompatibles ocultas){c.RESET}")
    else:
        entries = plan.entries

    if not entries:
        lines.append(f"{c.YELLOW}Sin herramientas para mostrar.{c.RESET}")
        return "\n".join(lines)

    headers = ["Herramienta", "Categoria", "Perfil", "Metodo", "Compat.", "Descarga", "Disco", "Sudo", "Estado"]
    col_widths = [20, 12, 8, 14, 10, 8, 6, 4, 12]

    def fmt_row(cells: List[str]) -> str:
        return "  ".join(f"{cell:<{w}}" for cell, w in zip(cells, col_widths))

    lines.append(fmt_row(headers))
    lines.append("-" * sum(w + 2 for w in col_widths))

    for entry in entries:
        tool = entry.tool
        compat_color = {
            CompatibilityClass.OPTIMAL: c.GREEN,
            CompatibilityClass.RECOMMENDED: c.CYAN,
            CompatibilityClass.COMPATIBLE: c.YELLOW,
            CompatibilityClass.INCOMPATIBLE: c.RED,
        }.get(entry.compatibility, c.RESET)

        status_color = {
            "will_install": c.GREEN,
            "optional": c.CYAN,
            "excluded": c.GRAY,
            "pending": c.YELLOW,
        }.get(entry.status, c.RESET)

        cells = [
            tool.name[:19],
            tool.category[:11],
            entry.tool.get_profile_status(plan.profile)[:7],
            entry.method[:13],
            c.colorize(entry.compatibility.value[:9], compat_color),
            f"{entry.estimated_download_mb}MB",
            f"{entry.estimated_disk_mb}MB",
            "Si" if entry.requires_sudo else "No",
            c.colorize(entry.status[:11], status_color),
        ]
        lines.append(fmt_row(cells))

        for warn in entry.warnings:
            lines.append(f"  {c.YELLOW}! {warn}{c.RESET}")

    lines.append("")
    lines.append(f"{c.BOLD}Leyenda:{c.RESET}")
    lines.append(f"  {c.GREEN}+{c.RESET} Optimo    {c.CYAN}+{c.RESET} Recomendado    {c.YELLOW}+{c.RESET} Compatible    {c.RED}+{c.RESET} Incompatible")
    lines.append(f"  {c.GREEN}+{c.RESET} Se instalara    {c.CYAN}+{c.RESET} Opcional    {c.GRAY}+{c.RESET} Excluido")

    return "\n".join(lines)


def format_audit_summary(entries: List[Dict]) -> str:
    lines = []
    c = Colors

    if not entries:
        return f"{c.YELLOW}Sin entradas de auditoria.{c.RESET}"

    lines.append(f"{c.BOLD}=== Resumen de auditoria ==={c.RESET}")
    lines.append(f"  Entradas totales: {len(entries)}")

    by_result = {}
    by_tool = {}
    for e in entries:
        by_result[e.get("result", "unknown")] = by_result.get(e.get("result", "unknown"), 0) + 1
        by_tool[e.get("tool", "unknown")] = by_tool.get(e.get("tool", "unknown"), 0) + 1

    lines.append(f"  Por resultado:")
    for result, count in sorted(by_result.items()):
        color = c.GREEN if result in ("installed", "already_installed", "configured") else c.RED if result == "failed" else c.YELLOW
        lines.append(f"    {color.colorize(result)}: {count}")

    lines.append(f"  Por herramienta:")
    for tool, count in sorted(by_tool.items()):
        lines.append(f"    {tool}: {count}")

    return "\n".join(lines)


def format_error(message: str) -> str:
    return f"{Colors.RED}Error: {message}{Colors.RESET}"


def format_warning(message: str) -> str:
    return f"{Colors.YELLOW}Advertencia: {message}{Colors.RESET}"


def format_info(message: str) -> str:
    return f"{Colors.BLUE}{message}{Colors.RESET}"


def format_success(message: str) -> str:
    return f"{Colors.GREEN}{message}{Colors.RESET}"