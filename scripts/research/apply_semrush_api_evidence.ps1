param(
    [Parameter(Mandatory = $true)]
    [string]$ResearchSummaryPath,

    [Parameter(Mandatory = $true)]
    [string]$SemrushEvidencePath
)

$ErrorActionPreference = 'Stop'

function Ensure-Property {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
    else {
        $Object.$Name = $Value
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$writeJsonUtf8 = Join-Path $repoRoot 'scripts\common\write_json_utf8.ps1'
$summaryPath = (Resolve-Path -LiteralPath $ResearchSummaryPath).Path
$evidencePath = (Resolve-Path -LiteralPath $SemrushEvidencePath).Path

$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json -Depth 100
$semrush = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json -Depth 100

Ensure-Property -Object $summary -Name 'seo' -Value ([pscustomobject]@{})
Ensure-Property -Object $summary.seo -Name 'semrush_evidence' -Value @()
Ensure-Property -Object $summary.seo -Name 'priority_issues' -Value @()
Ensure-Property -Object $summary -Name 'status' -Value ([pscustomobject]@{})
Ensure-Property -Object $summary -Name 'notes' -Value @()
Ensure-Property -Object $summary -Name 'semrush_plan' -Value ([pscustomobject]@{})

if (@($semrush.seo.semrush_evidence).Count -gt 0) {
    Ensure-Property -Object $summary.seo -Name 'semrush_evidence' -Value @($semrush.seo.semrush_evidence)
}

if (@($semrush.seo.priority_issues).Count -gt 0) {
    Ensure-Property -Object $summary.seo -Name 'priority_issues' -Value @($semrush.seo.priority_issues)
}

Ensure-Property -Object $summary.status -Name 'semrush' -Value ([string]$semrush.status)
Ensure-Property -Object $summary -Name 'semrush_direct_api' -Value $semrush

$summaryNotes = @($summary.notes)
if ([string]$semrush.status -eq 'passed') {
    $summaryNotes += 'SEMrush direct API evidence was collected and merged into the research summary.'
}
elseif ([string]$semrush.status -eq 'partial') {
    $summaryNotes += 'SEMrush direct API returned partial evidence; supplement with Tavily/Jina/direct site inspection.'
}
else {
    $summaryNotes += 'SEMrush direct API was blocked; do not fabricate SEMrush evidence.'
}
Ensure-Property -Object $summary -Name 'notes' -Value @($summaryNotes | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)

& $writeJsonUtf8 -Path $summaryPath -InputObject $summary

[pscustomobject]@{
    ok = $true
    research_summary = $summaryPath
    semrush_evidence = $evidencePath
    semrush_status = [string]$semrush.status
    semrush_evidence_count = @($summary.seo.semrush_evidence).Count
} | ConvertTo-Json -Depth 8 -Compress
