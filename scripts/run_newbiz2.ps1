param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$Website,
    [ValidateSet('bootstrap', 'live-summary', 'workpacks')]
    [string]$ResearchMode = 'bootstrap',
    [string]$ResearchSummaryPath,
    [string[]]$SearchWorkpacks = @(),
    [switch]$AllowResearchEscalation,
    [bool]$ComposioSemrushAvailable = $false,
    [bool]$JinaFallbackAvailable = $true,
    [string]$SemrushApiKey,
    [switch]$UseSemrushApi,
    [ValidateSet('uk', 'us')]
    [string]$SemrushDatabase = 'uk',
    [ValidateSet('full', 'research-only', 'render-stack', 'qa-only', 'deploy-handoff', 'art-refresh', 'assets-refresh')]
    [string]$Mode = 'render-stack'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$orchestrator = Join-Path $repoRoot 'scripts\orchestrate_newbiz2.ps1'

$orchestratorMode = switch ($Mode) {
    'full' { 'full' }
    'research-only' { 'research-only' }
    'render-stack' { 'render-stack' }
    'qa-only' { 'qa-only' }
    'deploy-handoff' { 'deploy-handoff' }
    'art-refresh' { 'art-refresh' }
    'assets-refresh' { 'assets-refresh' }
}

$params = @{
    Mode = $orchestratorMode
    ResearchMode = $ResearchMode
}
if ($DataPath) { $params.DataPath = $DataPath }
if ($BrandName) { $params.BrandName = $BrandName }
if ($BrandFolder) { $params.BrandFolder = $BrandFolder }
if ($Website) { $params.Website = $Website }
if ($ResearchSummaryPath) { $params.ResearchSummaryPath = $ResearchSummaryPath }
if (@($SearchWorkpacks).Count -gt 0) { $params.SearchWorkpacks = $SearchWorkpacks }
if ($AllowResearchEscalation) { $params.AllowResearchEscalation = $true }
$params.ComposioSemrushAvailable = $ComposioSemrushAvailable
$params.JinaFallbackAvailable = $JinaFallbackAvailable
if ($SemrushApiKey) { $params.SemrushApiKey = $SemrushApiKey }
if ($UseSemrushApi) { $params.UseSemrushApi = $true }
if ($SemrushDatabase) { $params.SemrushDatabase = $SemrushDatabase }

& $orchestrator @params
