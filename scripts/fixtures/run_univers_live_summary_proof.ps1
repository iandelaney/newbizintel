param()

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$orchestrator = Join-Path $repoRoot 'scripts\run_newbiz2.ps1'
$brandFolder = 'C:\codex projects\output\univers'
$dataPath = Join-Path $brandFolder 'report-data.json'
$researchSummaryPath = Join-Path $brandFolder 'research-summary.json'

& $orchestrator `
    -Mode full `
    -DataPath $dataPath `
    -BrandFolder $brandFolder `
    -ResearchMode live-summary `
    -ResearchSummaryPath $researchSummaryPath
