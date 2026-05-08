param(
    [string]$RepoRoot = '',
    [string]$Fixture = ''
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

$python = 'C:\Users\iande\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = 'py'
}

$scriptPath = Join-Path $RepoRoot 'scripts\qa\audit_research_quality_regressions.py'
$arguments = @($scriptPath, '--repo-root', $RepoRoot)
if ($Fixture) {
    $arguments += @('--fixture', $Fixture)
}

$output = & $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Research-quality regression audit failed: $output"
}

$output
