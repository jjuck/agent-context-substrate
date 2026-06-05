param(
  [string]$ProjectRoot,
  [string]$WikiRoot,
  [string]$CodexHome,
  [switch]$InstallMissingTools,
  [switch]$InstallObsidian,
  [switch]$CheckOnly,
  [switch]$NonInteractive
)

# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -CheckOnly
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
#
# Normal installs never use hook trust bypass flags. Review hooks with /hooks.

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[acs] $Message"
}

function Find-Command {
  param([string[]]$Names)
  foreach ($Name in $Names) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) {
      return $Command
    }
  }
  return $null
}

function Find-CodexAppCli {
  $Candidates = @()
  if ($env:LOCALAPPDATA) {
    $CodexBin = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
    $Candidates += Join-Path $CodexBin "codex.exe"
    if (Test-Path -LiteralPath $CodexBin) {
      $Candidates += Get-ChildItem -LiteralPath $CodexBin -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "codex.exe" }
    }
    $WindowsApps = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
    if (Test-Path -LiteralPath $WindowsApps) {
      $Candidates += Get-ChildItem -LiteralPath $WindowsApps -Directory -Filter "OpenAI.Codex_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "codex.exe" }
      $Candidates += Join-Path $WindowsApps "codex.exe"
    }
  }
  foreach ($Candidate in $Candidates) {
    if ($Candidate -and (Test-Path -LiteralPath $Candidate)) {
      return (Resolve-Path -LiteralPath $Candidate).Path
    }
  }
  return $null
}

function Test-CodexNpmShim {
  param([object]$Command)
  if (-not $Command) {
    return $false
  }
  $Source = [string]$Command.Source
  return ($Source -match "\\npm\\codex\.(ps1|cmd|bat)$")
}

function Install-WingetPackage {
  param(
    [string]$Id,
    [string]$Name
  )
  $Winget = Find-Command @("winget")
  if (-not $Winget) {
    throw "winget is not available. Install Windows Package Manager or install $Name manually."
  }
  Write-Step "Installing $Name with winget package $Id"
  & winget install --id $Id --exact --source winget --accept-package-agreements --accept-source-agreements
}

function Require-Tool {
  param(
    [string[]]$Commands,
    [string]$PackageId,
    [string]$DisplayName,
    [switch]$Optional
  )
  $Found = Find-Command $Commands
  if ($Found) {
    Write-Step "$DisplayName found: $($Found.Source)"
    return $Found
  }
  if ($Optional -and -not $InstallObsidian) {
    Write-Step "$DisplayName not found. Optional; skipping automatic install."
    return $null
  }
  if ($InstallMissingTools -or ($Optional -and $InstallObsidian)) {
    Install-WingetPackage -Id $PackageId -Name $DisplayName
    return Find-Command $Commands
  }
  if ($Optional) {
    Write-Step "$DisplayName not found. Optional install: winget install --id $PackageId --exact"
    return $null
  }
  throw "$DisplayName is required. Install it or rerun with -InstallMissingTools. winget package: $PackageId"
}

if (-not $ProjectRoot) {
  $ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
if (-not $WikiRoot) {
  $WikiRoot = Join-Path $env:USERPROFILE "Documents\LLM Wiki"
}
if (-not $CodexHome) {
  $CodexHome = Join-Path $env:USERPROFILE ".codex"
}

Write-Step "Project root: $ProjectRoot"
Write-Step "Codex SQLite: $CodexHome\state_5.sqlite"
Write-Step "Codex rollouts: $CodexHome\sessions\...\rollout-*.jsonl"
Write-Step "LLM Wiki root: $WikiRoot"
Write-Step "ACS artifacts: $ProjectRoot\data\..."

$Python = Require-Tool -Commands @("py", "python") -PackageId "Python.Python.3.13" -DisplayName "Python 3.13"
$Git = Require-Tool -Commands @("git") -PackageId "Git.Git" -DisplayName "Git"
$Obsidian = Require-Tool -Commands @("obsidian", "Obsidian") -PackageId "Obsidian.Obsidian" -DisplayName "Obsidian" -Optional
$Codex = Find-Command @("codex")
$CodexAppCli = Find-CodexAppCli
if ($Codex) {
  Write-Step "Codex CLI found: $($Codex.Source)"
  if (Test-CodexNpmShim $Codex) {
    Write-Step "WARNING: PATH codex appears to be an npm shim. Prefer the Windows Codex app CLI direct path for /hooks review."
  }
} else {
  Write-Step "Codex CLI was not found on PATH. The Codex app can still use installed files, but /hooks review needs Codex CLI or an equivalent Codex hook review surface."
}
if ($CodexAppCli) {
  Write-Step "Codex app CLI candidate: $CodexAppCli"
} else {
  Write-Step "Codex app CLI candidate not found under %LOCALAPPDATA%\OpenAI\Codex\bin."
}

if ($CheckOnly) {
  Write-Step "CheckOnly complete. No files were written by this script."
  exit 0
}

if (-not (Test-Path -LiteralPath $ProjectRoot)) {
  throw "ProjectRoot does not exist: $ProjectRoot"
}

Push-Location $ProjectRoot
try {
  $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
  $Cli = Join-Path $ProjectRoot ".venv\Scripts\agent-context-substrate.exe"
  if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Step "Creating Python virtual environment"
    if ((Find-Command @("py"))) {
      & py -3 -m venv .venv
    } else {
      & python -m venv .venv
    }
  }

  Write-Step "Installing Agent Context Substrate into the virtual environment"
  & $VenvPython -m pip install --upgrade pip
  & $VenvPython -m pip install -e .

  $SetupArgs = @(
    "setup-codex",
    "--codex-home", $CodexHome,
    "--project-root", $ProjectRoot,
    "--wiki-root", $WikiRoot,
    "--personal-marketplace-root", $env:USERPROFILE,
    "--yes"
  )
  if ($NonInteractive) {
    $SetupArgs += "--json"
  }

  Write-Step "Running ACS Codex setup"
  & $Cli @SetupArgs

  Write-Step "Run the Codex app CLI, then '/hooks', and trust the agent-context-substrate Stop hook. If a 'Hooks need review' modal appears, review the ACS hook command before choosing Trust all and continue."
  Write-Step "Default setup installs the plugin Stop hook only. Use the documented user hook fallback only if plugin hooks are unavailable, to avoid duplicate Stop hooks."
  Write-Step "Do not use hook trust bypass flags for normal installs."
  if ($Obsidian) {
    Write-Step "Open Obsidian and choose this vault folder: $WikiRoot"
  }
} finally {
  Pop-Location
}
