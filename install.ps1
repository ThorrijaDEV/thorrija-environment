<#>
.SYNOPSIS
    Thorrija Environment - Bootstrap Installer for Windows
.DESCRIPTION
    Universal, adaptive development environment provisioner for Windows 10/11.
    Detects OS/hardware, downloads verified release, executes Python engine.
.NOTES
    Version: 0.2.0-dev
    SHA256 del release tarball: ACTUALIZAR_EN_CI
#>

# Requiere PowerShell 5.1+ (incluido en Windows 10/11)
# Ejecutar como Administrador para instalaciones con winget/choco/scoop

# Configuración inmutable (actualizada por CI en cada release)
$REPO = "ThorrijaDEV/thorrija-environment"
$RELEASE_VERSION = "latest"
$SHA256_EXPECTED = "PENDING_RELEASE_HASH"
$BOOTSTRAP_VERSION = "0.2.0-dev"

# Colores para output (si terminal lo soporta)
if ($Host.UI.RawUI.WindowTitle -ne "") {
    $C_RESET = [char]27 + "[0m"
    $C_BOLD = [char]27 + "[1m"
    $C_RED = [char]27 + "[31m"
    $C_GREEN = [char]27 + "[32m"
    $C_YELLOW = [char]27 + "[33m"
    $C_BLUE = [char]27 + "[34m"
    $C_CYAN = [char]27 + "[36m"
} else {
    $C_RESET = $C_BOLD = $C_RED = $C_GREEN = $C_YELLOW = $C_BLUE = $C_CYAN = ""
}

function Log-Info { param($msg) Write-Host "${C_BLUE}[INFO]${C_RESET} $msg" }
function Log-Ok { param($msg) Write-Host "${C_GREEN}[OK]${C_RESET} $msg" }
function Log-Warn { param($msg) Write-Host "${C_YELLOW}[WARN]${C_RESET} $msg" }
function Log-Error { param($msg) Write-Error "${C_RED}[ERROR]${C_RESET} $msg" }
function Log-Debug { param($msg) if ($env:THORRIJA_DEBUG -eq "1") { Write-Host "${C_CYAN}[DEBUG]${C_RESET} $msg" } }

function Show-Help {
    @"
Thorrija Environment - Bootstrap Installer for Windows

Usage: .\install.ps1 [BOOTSTRAP_OPTIONS] -- [ENGINE_OPTIONS]

Bootstrap Options:
  -h, --help           Show this help
  -V, --version        Show bootstrap version
      --dev            Dev mode: use local code (no download/hash)
      --verify-only    Verify tarball hash only (release mode)
      --python PATH    Force specific Python executable
      --no-python-check Skip Python version check (dangerous)
      --debug          Enable debug logging

All other options are passed to the Python engine.
Examples:
  .\install.ps1 -- --detect
  .\install.ps1 -- --profile standard --plan
  .\install.ps1 -- --profile standard --yes
"@
}

# Parse bootstrap arguments
$BootstrapArgs = @()
$EngineArgs = @()
$Passthrough = $false
$ForcePython = $null
$SkipPythonCheck = $false
$DevMode = $false
$VerifyOnly = $false

foreach ($arg in $args) {
    if ($Passthrough) {
        $EngineArgs += $arg
    } elseif ($arg -eq "--") {
        $Passthrough = $true
    } elseif ($arg -in @("--help", "-h")) {
        Show-Help; exit 0
    } elseif ($arg -in @("--version", "-V")) {
        "thorrija-bootstrap $BOOTSTRAP_VERSION"; exit 0
    } elseif ($arg -eq "--dev") {
        $DevMode = $true
    } elseif ($arg -eq "--verify-only") {
        $VerifyOnly = $true
    } elseif ($arg -eq "--python") {
        $ForcePython = $args[($args.IndexOf($arg) + 1)]
        if (-not $ForcePython) { Log-Error "--python requiere argumento"; exit 1 }
    } elseif ($arg -eq "--no-python-check") {
        $SkipPythonCheck = $true
    } elseif ($arg -eq "--debug") {
        $env:THORRIJA_DEBUG = "1"
    } else {
        $EngineArgs += $arg
    }
}

# Validaciones iniciales
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Log-Warn "Se recomienda ejecutar como Administrador para instalaciones con winget/choco/scoop"
}

$requiredCmds = @("curl", "tar", "sha256sum", "python", "python3", "python3.11", "python3.10", "python3.9")
$missing = $requiredCmds | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) }
if ($missing.Count -gt 0 -and -not $DevMode) {
    Log-Warn "Comandos no encontrados (se intentará instalar): $($missing -join ', ')"
}

# ============================================================
# ETAPA 1: Asegurar Python >= 3.9
# ============================================================
function Find-Python {
    $candidates = @()
    if ($ForcePython) { $candidates += $ForcePython }
    $candidates += @("python", "python3", "python3.13", "python3.12", "python3.11", "python3.10", "python3.9")

    foreach ($py in $candidates) {
        if (Get-Command $py -ErrorAction SilentlyContinue) {
            try {
                $version = & $py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>$null
                if ($version) {
                    $parts = $version.Split('.')
                    $major = [int]$parts[0]; $minor = [int]$parts[1]
                    if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 9)) {
                        Log-Debug "Python encontrado: $py ($version)"
                        return $py
                    }
                    Log-Debug "Python $py versión $version < 3.9, descartado"
                }
            } catch { }
        }
    }
    return $null
}

$PYTHON_BIN = $null
if ($SkipPythonCheck) {
    $PYTHON_BIN = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command python3.11 -ErrorAction SilentlyContinue) ?? (Get-Command python3.10 -ErrorAction SilentlyContinue) ?? (Get-Command python3.9 -ErrorAction SilentlyContinue)
    if (-not $PYTHON_BIN) { Log-Error "No se encontró python3"; exit 1 }
    Log-Warn "Saltando verificación de versión Python (--no-python-check)"
} else {
    Log-Info "Buscando Python >= 3.9..."
    $PYTHON_BIN = Find-Python
    if (-not $PYTHON_BIN) {
        Log-Warn "Python >= 3.9 no encontrado en PATH."

        # Detectar gestores de paquetes disponibles
        $pkgManagers = @()
        if (Get-Command winget -ErrorAction SilentlyContinue) { $pkgManagers += "winget" }
        if (Get-Command choco -ErrorAction SilentlyContinue) { $pkgManagers += "chocolatey" }
        if (Get-Command scoop -ErrorAction SilentlyContinue) { $pkgManagers += "scoop" }

        if ($pkgManagers.Count -gt 0) {
            Log-Info "Se puede instalar automáticamente con:"
            foreach ($mgr in $pkgManagers) {
                switch ($mgr) {
                    "winget" { "  winget install --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements" }
                    "chocolatey" { "  choco install python3 --version 3.11.9 -y" }
                    "scoop" { "  scoop install python@3.11.9" }
                }
            }
            $confirm = Read-Host "¿Ejecutar instalación automática? [s/N]"
            if ($confirm -in @("s", "S", "y", "Y", "si", "Si", "SI")) {
                foreach ($mgr in $pkgManagers) {
                    switch ($mgr) {
                        "winget" { winget install --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements }
                        "chocolatey" { choco install python3 --version 3.11.9 -y }
                        "scoop" { scoop install python@3.11.9 }
                    }
                }
                $PYTHON_BIN = Find-Python
                if (-not $PYTHON_BIN) { Log-Error "Python instalado pero no detectable"; exit 1 }
                Log-Ok "Python disponible: $($PYTHON_BIN --version)"
            } else {
                Log-Error "Instalación cancelada. Instala manualmente Python 3.11+ y reintenta."
                exit 1
            }
        } else {
            Log-Error "No hay gestores de paquetes (winget/choco/scoop) disponibles."
            "Instala manualmente Python 3.11+ desde https://python.org/downloads/"
            exit 1
        }
    }
}

Log-Ok "Python detectado: $($PYTHON_BIN --version)"

# Verificar tomllib/tomli
$hasToml = $false
try { & $PYTHON_BIN -c "import tomllib" 2>$null; $hasToml = $true } catch { }
if (-not $hasToml) {
    try { & $PYTHON_BIN -c "import tomli" 2>$null; $hasToml = $true } catch { }
}
if (-not $hasToml) {
    Log-Warn "tomllib/tomli no disponible en Python del sistema; se usará vendor incluido"
}

# ============================================================
# ETAPA 2: Obtener y validar código fuente
# ============================================================
$WORKDIR = $null
$CLEANUP = @()

function Cleanup {
    foreach ($item in $CLEANUP) {
        if (Test-Path $item) { Remove-Item $item -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
# Register cleanup on exit
$script:cleanupAction = { Cleanup }
Register-EngineEvent -SourceIdentifier "PowerShell.Exiting" -Action $script:cleanupAction | Out-Null

if ($DevMode) {
    $SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
    if (Test-Path "$SCRIPT_DIR\src\thorrija" -and Test-Path "$SCRIPT_DIR\catalog") {
        $WORKDIR = $SCRIPT_DIR
        Log-Info "Modo desarrollo: usando código local en $WORKDIR"
    } else {
        Log-Error "--dev requiere ejecutarse desde la raíz del repo clonado (con src/ y catalog/)"
        exit 1
    }
} else {
    $TMPDIR = [IO.Path]::GetTempFileName().Replace(".tmp", "")
    Remove-Item $TMPDIR -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $TMPDIR | Out-Null
    $CLEANUP += $TMPDIR
    $TARBALL = Join-Path $TMPDIR "thorrija.tar.gz"

    if ($RELEASE_VERSION -eq "latest") {
        Log-Info "Resolviendo última versión desde GitHub..."
        $LATEST_URL = "https://api.github.com/repos/$REPO/releases/latest"
        $RELEASE_JSON = Invoke-RestMethod -Uri $LATEST_URL -TimeoutSec 10 -Headers @{"User-Agent"="ThorrijaEnvironment/0.1"}
        $TAG = $RELEASE_JSON.tag_name
        if (-not $TAG) { Log-Error "No se pudo obtener tag de GitHub API"; exit 1 }
        $RELEASE_VERSION = $TAG
        Log-Info "Última versión: $RELEASE_VERSION"
    }

    $TARBALL_URL = "https://github.com/${REPO}/releases/download/${RELEASE_VERSION}/thorrija-environment-${RELEASE_VERSION}.tar.gz"
    Log-Info "Descargando $TARBALL_URL ..."
    try {
        Invoke-RestMethod -Uri $TARBALL_URL -OutFile $TARBALL -TimeoutSec 60 -Headers @{"User-Agent"="ThorrijaEnvironment/0.2"}
    } catch {
        Log-Error "Falló descarga: $_"; exit 1
    }

    if ($VerifyOnly) {
        $ACTUAL_SHA = (Get-FileHash $TARBALL -Algorithm SHA256).Hash.ToLower()
        Write-Host "SHA256 actual: $ACTUAL_SHA"
        Write-Host "SHA256 esperado: $SHA256_EXPECTED"
        if ($ACTUAL_SHA -eq $SHA256_EXPECTED.ToLower()) { Log-Ok "Hash verificado"; exit 0 } else { Log-Error "Hash NO coincide"; exit 1 }
    }

    if ($SHA256_EXPECTED -ne "PENDING_RELEASE_HASH") {
        Log-Info "Verificando integridad (SHA-256)..."
        $ACTUAL_SHA = (Get-FileHash $TARBALL -Algorithm SHA256).Hash.ToLower()
        if ($ACTUAL_SHA -ne $SHA256_EXPECTED.ToLower()) {
            Log-Error "Integridad del instalador comprometida."
            "  Hash esperado: $SHA256_EXPECTED"
            "  Hash real:     $ACTUAL_SHA"
            "No continúes. Descarga manualmente desde: https://github.com/$REPO/releases"
            exit 1
        }
        Log-Ok "Hash verificado correctamente"
    } else {
        Log-Warn "SHA256_EXPECTED no configurado (build de desarrollo). Saltando verificación."
    }

    Log-Info "Extrayendo..."
    $EXTRACT_DIR = Join-Path $TMPDIR "thorrija-extracted"
    New-Item -ItemType Directory -Path $EXTRACT_DIR | Out-Null
    try {
        tar -xzf $TARBALL -C $EXTRACT_DIR --strip-components=1
    } catch {
        Log-Error "Falló extracción: $_"; exit 1
    }

    if (-not (Test-Path "$EXTRACT_DIR\src\thorrija") -or -not (Test-Path "$EXTRACT_DIR\catalog")) {
        Log-Error "Estructura de release inválida"; exit 1
    }

    $WORKDIR = $EXTRACT_DIR
    Log-Ok "Código fuente listo en $WORKDIR"
}

# ============================================================
# ETAPA 3: Delegar al motor Python
# ============================================================
Set-Location $WORKDIR
$env:THORRIJA_BOOTSTRAP = "1"
$env:THORRIJA_WORKDIR = $WORKDIR

Log-Info "Iniciando motor Python..."
& $PYTHON_BIN -m thorrija @EngineArgs