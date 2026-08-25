[CmdletBinding()]
param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)
$VenvDirectory = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
$PyprojectFile = Join-Path $ProjectRoot "pyproject.toml"
$FingerprintFile = Join-Path $VenvDirectory ".pyproject.sha256"

function New-ProjectVirtualEnvironment {
    $PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    $PythonExecutable = $null
    $PythonArguments = @()

    if ($null -ne $PyLauncher) {
        $LauncherIsUsable = $false

        try {
            & $PyLauncher.Source -3.11 -c "import sys" *> $null
            $LauncherIsUsable = $LASTEXITCODE -eq 0
        }
        catch {
            $LauncherIsUsable = $false
        }

        if ($LauncherIsUsable) {
            $PythonExecutable = $PyLauncher.Source
            $PythonArguments = @("-3.11")
        }
    }

    if ($null -eq $PythonExecutable) {
        $SystemPython = Get-Command "python" -ErrorAction SilentlyContinue

        if ($null -ne $SystemPython) {
            $SystemPythonIsUsable = $false

            try {
                & $SystemPython.Source -c (
                    "import sys; raise SystemExit(sys.version_info < (3, 11))"
                ) *> $null
                $SystemPythonIsUsable = $LASTEXITCODE -eq 0
            }
            catch {
                $SystemPythonIsUsable = $false
            }

            if ($SystemPythonIsUsable) {
                $PythonExecutable = $SystemPython.Source
            }
        }
    }

    if ($null -eq $PythonExecutable) {
        throw (
            "Python 3.11 or newer is unavailable. The existing environment " +
            "was preserved. Install Python 3.11+ or create " +
            "'$VenvDirectory' manually."
        )
    }

    if (Test-Path -LiteralPath $VenvDirectory) {
        Remove-Item -LiteralPath $VenvDirectory -Recurse -Force
    }

    $VenvArguments = $PythonArguments + @("-m", "venv", $VenvDirectory)
    & $PythonExecutable @VenvArguments

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        throw "Failed to create the virtual environment at '$VenvDirectory'."
    }
}

function Test-ProjectDependencies {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        return $false
    }

    try {
        & $VenvPython -c "import notebook_ta, pytest, mypy" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $PyprojectFile)) {
    throw "Could not find pyproject.toml at '$PyprojectFile'."
}

if ($Recreate -or -not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating the project virtual environment..."
    New-ProjectVirtualEnvironment
}
elseif (-not (Test-ProjectDependencies)) {
    Write-Host "The existing virtual environment is invalid; rebuilding it..."
    New-ProjectVirtualEnvironment
}

$CurrentFingerprint = (Get-FileHash -Algorithm SHA256 $PyprojectFile).Hash
$InstalledFingerprint = ""

if (Test-Path -LiteralPath $FingerprintFile) {
    $InstalledFingerprint = (Get-Content -Raw $FingerprintFile).Trim()
}

$DependenciesAreReady = Test-ProjectDependencies

if (
    -not $DependenciesAreReady -or
    $InstalledFingerprint -ne $CurrentFingerprint
) {
    Write-Host "Installing project development dependencies..."

    Push-Location $ProjectRoot
    try {
        & $VenvPython -m pip install `
            --quiet `
            --disable-pip-version-check `
            -e ".[dev]"

        if ($LASTEXITCODE -ne 0) {
            throw "Dependency installation failed."
        }
    }
    finally {
        Pop-Location
    }

    if (-not (Test-ProjectDependencies)) {
        throw "The environment was created, but required imports still fail."
    }

    Set-Content `
        -LiteralPath $FingerprintFile `
        -Value $CurrentFingerprint `
        -Encoding ASCII `
        -NoNewline
}

Write-Host "Python environment ready: $VenvPython"
