param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$Website
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$loadRunState = Join-Path $repoRoot 'scripts\common\load_run_state.ps1'
$saveRunState = Join-Path $repoRoot 'scripts\common\save_run_state.ps1'
$initBrandWorkspace = Join-Path $repoRoot 'scripts\intake\init_brand_workspace.ps1'
$resolveOutputRoot = Join-Path $repoRoot 'scripts\common\resolve_output_root.ps1'
$contractPath = Join-Path $repoRoot 'references\run-state.contract.json'
. (Join-Path $repoRoot 'scripts\common\task_list.ps1')

if (-not $DataPath) {
    if (-not $BrandName) {
        throw 'Provide either -DataPath or -BrandName.'
    }

    $BrandFolder = & $resolveOutputRoot -ExplicitRoot $BrandFolder -RepoRoot $repoRoot

    if (-not (Test-Path -LiteralPath $BrandFolder)) {
        New-Item -ItemType Directory -Force -Path $BrandFolder | Out-Null
    }

    $initParams = @{
        BrandName = $BrandName
        RootPath = $BrandFolder
    }
    if ($Website) { $initParams.Website = $Website }
    $initResult = & $initBrandWorkspace @initParams | ConvertFrom-Json
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

Ensure-NewBizTaskList -State $state
Sync-NewBizTaskStatusFromGates -State $state

[pscustomobject]@{
    repo_root = $repoRoot
    data_path = $resolvedDataPath
    brand_folder = $resolvedBrandFolder
    run_state_path = $runStatePath
    state = $state
    save_run_state = $saveRunState
}
