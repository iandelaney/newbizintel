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
    [ValidateSet('full','research-only','render-stack','qa-only','deploy-handoff','art-refresh','assets-refresh')]
    [string]$Mode = 'full'
)

$ErrorActionPreference = 'Stop'

$legacyScript = Join-Path $PSScriptRoot 'orchestrate_newbiz2.ps1'
$params = @{
    ResearchMode = $ResearchMode
    ComposioSemrushAvailable = $ComposioSemrushAvailable
    JinaFallbackAvailable = $JinaFallbackAvailable
    SemrushDatabase = $SemrushDatabase
    Mode = $Mode
}
if ($DataPath) { $params.DataPath = $DataPath }
if ($BrandName) { $params.BrandName = $BrandName }
if ($BrandFolder) { $params.BrandFolder = $BrandFolder }
if ($Website) { $params.Website = $Website }
if ($ResearchSummaryPath) { $params.ResearchSummaryPath = $ResearchSummaryPath }
if (@($SearchWorkpacks).Count -gt 0) { $params.SearchWorkpacks = $SearchWorkpacks }
if ($AllowResearchEscalation) { $params.AllowResearchEscalation = $true }
if ($SemrushApiKey) { $params.SemrushApiKey = $SemrushApiKey }
if ($UseSemrushApi) { $params.UseSemrushApi = $true }

& $legacyScript @params
