param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [ValidateSet('bootstrap', 'live-summary')]
    [string]$ResearchMode = 'bootstrap',
    [string]$ResearchSummaryPath,
    [switch]$UseSemrushApi,
    [ValidateSet('uk', 'us')]
    [string]$SemrushDatabase = 'uk',
    [ValidateSet('full','research-only','render-stack','qa-only','deploy-handoff','art-refresh','assets-refresh')]
    [string]$Mode = 'full'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Invoke-ModuleJson {
    param(
        [string]$ScriptPath,
        [hashtable]$Params
    )

    & $ScriptPath @Params | ConvertFrom-Json
}

function Sync-ContextFromResult {
    param(
        [hashtable]$Params,
        [object]$Result
    )

    if ($null -ne $Result.data -and [string]$Result.data) {
        $Params.DataPath = [string]$Result.data
    }

    if ($null -ne $Result.brand_folder -and [string]$Result.brand_folder) {
        $Params.BrandFolder = [string]$Result.brand_folder
    }

    if ($null -ne $Result.research_summary -and [string]$Result.research_summary) {
        $Params.ResearchSummaryPath = [string]$Result.research_summary
    }
}

$baseParams = @{}
if ($DataPath) { $baseParams.DataPath = $DataPath }
if ($BrandName) { $baseParams.BrandName = $BrandName }
if ($BrandFolder) { $baseParams.BrandFolder = $BrandFolder }
$baseParams.ResearchMode = $ResearchMode
if ($ResearchSummaryPath) { $baseParams.ResearchSummaryPath = $ResearchSummaryPath }
if ($UseSemrushApi) { $baseParams.UseSemrushApi = $true }
if ($SemrushDatabase) { $baseParams.SemrushDatabase = $SemrushDatabase }

$results = [ordered]@{
    mode = $Mode
}

switch ($Mode) {
    'full' {
        $results.intake = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\intake\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.intake
        $results.research = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\research\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.research
        $results.structure = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\structure\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.structure
        $results.assets = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\assets\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.assets
        $results.campaign_art = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\campaign-art\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.campaign_art
        $results.render = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\render\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.render
        $results.qa = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\qa\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.qa
        $results.deploy = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\deploy\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.deploy
    }
    'research-only' {
        $results.intake = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\intake\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.intake
        $results.research = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\research\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.research
    }
    'render-stack' {
        $results.intake = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\intake\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.intake
        $results.structure = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\structure\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.structure
        $results.assets = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\assets\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.assets
        $results.campaign_art = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\campaign-art\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.campaign_art
        $results.render = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\render\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.render
        $results.qa = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\qa\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.qa
    }
    'qa-only' {
        $results.qa = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\qa\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.qa
    }
    'deploy-handoff' {
        $results.deploy = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\deploy\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.deploy
    }
    'art-refresh' {
        $results.campaign_art = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\campaign-art\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.campaign_art
        $results.render = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\render\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.render
        $results.qa = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\qa\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.qa
    }
    'assets-refresh' {
        $results.assets = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\assets\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.assets
        $results.render = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\render\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.render
        $results.qa = Invoke-ModuleJson -ScriptPath (Join-Path $repoRoot 'scripts\qa\run_module.ps1') -Params $baseParams
        Sync-ContextFromResult -Params $baseParams -Result $results.qa
    }
}

[pscustomobject]$results | ConvertTo-Json -Depth 12 -Compress
