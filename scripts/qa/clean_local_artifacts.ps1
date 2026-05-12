param(
    [string]$RepoRoot = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

$targets = @(
    'dist',
    'node_modules',
    'pptx_runtime',
    'pptx_runtime_env',
    'runtime',
    'examples\archive\newbizintel-report-portable.html',
    'examples\newbizintel-report.html',
    'examples\required-logo-manifest.json',
    'examples\run-state.json',
    'examples\source-badge-manifest.json',
    'scripts\__pycache__',
    'scripts\campaign-art\__pycache__',
    'scripts\python_modules\__pycache__',
    'scripts\qa\__pycache__',
    'scripts\render\__pycache__',
    'scripts\research\__pycache__',
    'companion-skills\slides\scripts\__pycache__'
)

$results = @()
foreach ($target in $targets) {
    $path = Join-Path $RepoRoot $target
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }

    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer) {
        $files = (Get-ChildItem -LiteralPath $path -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object).Count
        $bytes = (Get-ChildItem -LiteralPath $path -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    }
    else {
        $files = 1
        $bytes = $item.Length
    }

    if (-not $DryRun) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }

    $results += [pscustomobject]@{
        target = $target
        files = $files
        mb = [math]::Round(($bytes / 1MB), 2)
        action = if ($DryRun) { 'would_remove' } else { 'removed' }
    }
}

[pscustomobject]@{
    ok = $true
    repo_root = (Resolve-Path -LiteralPath $RepoRoot).Path
    dry_run = [bool]$DryRun
    removed_count = @($results).Count
    targets = $results
} | ConvertTo-Json -Depth 5
