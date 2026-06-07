param(
    [string]$Message,
    [string]$Branch = "master",
    [switch]$SkipFlutterBuild,
    [switch]$SkipPythonCheck,
    [switch]$NoPush,
    [switch]$AllowSensitiveFiles
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Command '$Name' was not found. Install it or run this script from an environment where it is available."
    }
}

function Invoke-ProjectPython {
    param([string[]]$Arguments)

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        & $venvPython @Arguments
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @Arguments
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python @Arguments
    }
    else {
        throw "Python 3 was not found. Create .venv or install the Python launcher."
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python check failed with exit code $LASTEXITCODE."
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Require-Command git

Write-Step "Checking repository"
$insideWorkTree = git rev-parse --is-inside-work-tree
if ($insideWorkTree -ne "true") {
    throw "This script must be run inside a Git repository."
}

$currentBranch = git branch --show-current
if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    throw "Git is in a detached HEAD state. Switch to '$Branch' before deploying."
}

if ($currentBranch -ne $Branch) {
    throw "Current branch is '$currentBranch', but deploy branch is '$Branch'. Switch branches or pass -Branch <name>."
}

$remoteUrl = git remote get-url origin
if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
    throw "Git remote 'origin' is not configured."
}
Write-Host "Branch: $currentBranch"
Write-Host "Remote: $remoteUrl"

if (-not $SkipPythonCheck) {
    Write-Step "Checking Python files"
    Invoke-ProjectPython -Arguments @("-m", "compileall", "-q", "app", "main.py", "scripts")
    Invoke-ProjectPython -Arguments @("scripts/check_backend_workflows.py")
}

if (-not $SkipFlutterBuild) {
    Write-Step "Building Flutter web"
    Require-Command flutter
    Push-Location (Join-Path $RepoRoot "mobile_app")
    try {
        flutter pub get
        flutter build web --release
    }
    finally {
        Pop-Location
    }
}

Write-Step "Reviewing local changes"
$status = git status --short
if ($status) {
    $status | ForEach-Object { Write-Host $_ }
}
else {
    Write-Host "No local changes found."
}

Write-Step "Staging changes"
git add -A

$stagedFiles = @(git diff --cached --name-only)
if ($stagedFiles.Count -eq 0) {
    Write-Host "Nothing to commit."
}
else {
    if (-not $AllowSensitiveFiles) {
        $blocked = $stagedFiles | Where-Object {
            ($_ -match '(^|/)\.env(\..*)?$' -and $_ -ne ".env.example") -or
            ($_ -match '\.(db|sqlite|sqlite3)$') -or
            ($_ -match '\.db-(shm|wal|journal)$')
        }

        if ($blocked) {
            Write-Host ""
            Write-Host "Blocked sensitive files:" -ForegroundColor Yellow
            $blocked | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
            git restore --staged -- $blocked
            throw "Sensitive files are staged. Unstage/remove them, or rerun with -AllowSensitiveFiles if this is intentional."
        }
    }

    if ([string]::IsNullOrWhiteSpace($Message)) {
        $Message = Read-Host "Commit message"
    }
    if ([string]::IsNullOrWhiteSpace($Message)) {
        throw "Commit message is required when there are changes."
    }

    Write-Step "Creating commit"
    git commit -m $Message
}

if ($NoPush) {
    Write-Step "Push skipped"
    Write-Host "Run without -NoPush when you are ready to deploy."
    exit 0
}

Write-Step "Pushing to GitHub"
git push origin "HEAD:$Branch"

Write-Host ""
Write-Host "Done. GitHub Actions should now deploy the '$Branch' branch to the server." -ForegroundColor Green
