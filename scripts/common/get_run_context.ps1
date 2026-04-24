param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$loadRunState = Join-Path $repoRoot 'scripts\common\load_run_state.ps1'
$saveRunState = Join-Path $repoRoot 'scripts\common\save_run_state.ps1'
$initBrandWorkspace = Join-Path $repoRoot 'scripts\intake\init_brand_workspace.ps1'
$contractPath = Join-Path $repoRoot 'references\run-state.contract.json'

if (-not $DataPath) {
    if (-not $BrandName) {
        throw 'Provide either -DataPath or -BrandName.'
    }

    if (-not $BrandFolder) {
        $BrandFolder = Join-Path $repoRoot 'output'
    }

    if (-not (Test-Path -LiteralPath $BrandFolder)) {
        New-Item -ItemType Directory -Force -Path $BrandFolder | Out-Null
    }

    $initResult = & $initBrandWorkspace -BrandName $BrandName -RootPath $BrandFolder | ConvertFrom-Json
    $resolvedDataPath = $initResult.report_data_path
    $resolvedBrandFolder = $initResult.brand_path
}
else {
    $resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
    $resolvedBrandFolder = Split-Path -Parent $resolvedDataPath
}

$runStatePath = Join-Path $resolvedBrandFolder 'run-state.json'
if (Test-Path -LiteralPath $runStatePath) {
    $state = & $loadRunState -Path $runStatePath
}
else {
    $state = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
    $state.brand_folder = $resolvedBrandFolder
}

[pscustomobject]@{
    repo_root = $repoRoot
    data_path = $resolvedDataPath
    brand_folder = $resolvedBrandFolder
    run_state_path = $runStatePath
    state = $state
    save_run_state = $saveRunState
}
