param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'

$resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$patterns = @(
    'C:\\codex projects\\',
    'newbizintel-skill-repo',
    'output\\univers',
    'output\\vercel',
    'cinder-signal-8367'
)

$allowedPathFragments = @(
    '\README.md',
    '\references\duplication-map.md',
    '\scripts\fixtures\run_univers_live_summary_proof.ps1',
    '\scripts\qa\audit_portability.ps1',
    '\examples\research-summary.json',
    '\examples\run-state.json'
)

$ignoredPathFragments = @(
    '\node_modules\',
    '\pptx_runtime\',
    '\pptx_runtime_env\',
    '\runtime\',
    '\vendor\',
    '\dist\',
    '\__pycache__\'
)

$findings = @()

Get-ChildItem -LiteralPath $resolvedRepoRoot -File -Recurse | ForEach-Object {
    $path = $_.FullName
    if ((Split-Path -Leaf $path) -in @('source-badge-manifest.json', 'required-logo-manifest.json')) {
        return
    }

    foreach ($fragment in $ignoredPathFragments) {
        if ($path -like "*$fragment*") {
            return
        }
    }

    $allowed = $false

    foreach ($fragment in $allowedPathFragments) {
        if ($path -like "*$fragment") {
            $allowed = $true
            break
        }
    }

    if ($allowed) {
        return
    }

    $matches = Select-String -Path $path -Pattern $patterns -SimpleMatch -ErrorAction SilentlyContinue
    foreach ($match in @($matches)) {
        $findings += [pscustomobject]@{
            file = $match.Path
            line = $match.LineNumber
            text = $match.Line.Trim()
        }
    }
}

[pscustomobject]@{
    ok = (@($findings).Count -eq 0)
    repo_root = $resolvedRepoRoot
    findings = @($findings)
} | ConvertTo-Json -Depth 6 -Compress
