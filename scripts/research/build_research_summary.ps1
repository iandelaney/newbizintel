param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$writeJsonUtf8 = Join-Path $repoRoot 'scripts\common\write_json_utf8.ps1'

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json

if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $resolvedDataPath) 'research-summary.json'
}
else {
    $parent = Split-Path -Parent $OutputPath
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
}

$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

$competitors = @()
$seenCompetitors = New-Object 'System.Collections.Generic.HashSet[string]'

foreach ($name in @($data.cover.competitors)) {
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    $trimmed = [string]$name
    if ($seenCompetitors.Add($trimmed.ToLowerInvariant())) {
        $competitors += [pscustomobject]@{
            name = $trimmed
            website = $null
            why_it_matters = $null
        }
    }
}

foreach ($row in @($data.competitive_landscape.table)) {
    $name = [string]$row.competitor
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    $key = $name.ToLowerInvariant()
    if (-not $seenCompetitors.Contains($key)) {
        $seenCompetitors.Add($key) | Out-Null
        $competitors += [pscustomobject]@{
            name = $name
            website = [string]$row.website
            why_it_matters = [string]$row.why_it_matters
        }
    }
    else {
        $existing = $competitors | Where-Object { $_.name.ToLowerInvariant() -eq $key } | Select-Object -First 1
        if ($existing) {
            if (-not $existing.website -and $row.website) { $existing.website = [string]$row.website }
            if (-not $existing.why_it_matters -and $row.why_it_matters) { $existing.why_it_matters = [string]$row.why_it_matters }
        }
    }
}

$news = @()
foreach ($item in @($data.brand_reputation.influential_news)) {
    $news += [pscustomobject]@{
        date = [string]$item.date
        headline = [string]$item.headline
        source = [string]$item.source
        url = [string]$item.url
        why_it_matters = [string]$item.why_it_matters
    }
}

$semrushEvidence = @()
foreach ($item in @($data.seo_audit.semrush_evidence)) {
    $semrushEvidence += [pscustomobject]@{
        title = [string]$item.title
        body = [string]$item.body
    }
}

$priorityIssues = @()
foreach ($item in @($data.seo_audit.priority_issues)) {
    $priorityIssues += [pscustomobject]@{
        issue = [string]$item.issue
        evidence = [string]$item.evidence
        why_it_matters = [string]$item.why_it_matters
        recommended_fix = [string]$item.recommended_fix
    }
}

$summary = [ordered]@{
    mode = 'bootstrap-from-report-data'
    data_path = $resolvedDataPath
    brand_name = [string]$data.brand.name
    brand_website = [string]$data.brand.website
    competitors = $competitors
    influential_news = $news
    reputation = [ordered]@{
        platform_readout = @($data.brand_reputation.platform_readout)
        recommended_actions = @($data.brand_reputation.recommended_actions)
    }
    seo = [ordered]@{
        semrush_evidence = $semrushEvidence
        priority_issues = $priorityIssues
    }
    tavily_validation = [ordered]@{
        competitor_discovery = [ordered]@{
            status = 'blocked'
            tool = 'tavily'
            validated_on = $null
            query_summary = @()
            source_count = 0
            used_in_sections = @('competitive_landscape')
            why_passed = 'Bootstrap mode reused an existing competitor set from report-data.json and did not run Tavily in this pass.'
        }
        recent_news = [ordered]@{
            status = 'blocked'
            tool = 'tavily'
            validated_on = $null
            query_summary = @()
            source_count = 0
            used_in_sections = @('brand_reputation')
            why_passed = 'Bootstrap mode reused existing influential-news entries from report-data.json and did not run Tavily in this pass.'
        }
        reputation_public_web = [ordered]@{
            status = 'blocked'
            tool = 'tavily'
            validated_on = $null
            query_summary = @()
            source_count = 0
            used_in_sections = @('brand_reputation')
            why_passed = 'Bootstrap mode reused existing reputation notes from report-data.json and did not run Tavily in this pass.'
        }
        source_gathering = [ordered]@{
            status = 'blocked'
            tool = 'tavily'
            validated_on = $null
            query_summary = @()
            source_count = 0
            used_in_sections = @('appendix')
            why_passed = 'Bootstrap mode did not perform a Tavily-backed source-gathering pass.'
        }
    }
    source_provenance_summary = [ordered]@{
        tavily_backed_sources = 0
        owned_sources = 0
        third_party_sources = 0
    }
    source_map = @()
    locked_sets = [ordered]@{
        competitors = @($competitors | ForEach-Object { $_.name })
        influential_news = @($news | ForEach-Object { $_.headline })
    }
    status = [ordered]@{
        competitor_discovery = $(if ($competitors.Count -gt 0) { 'passed' } else { 'pending' })
        recent_news = $(if ($news.Count -gt 0) { 'passed' } else { 'pending' })
        reputation_public_web = $(if ((@($data.brand_reputation.platform_readout)).Count -gt 0 -or (@($data.brand_reputation.recommended_actions)).Count -gt 0) { 'passed' } else { 'pending' })
        source_gathering = 'blocked'
        semrush = $(if ($semrushEvidence.Count -gt 0) { 'passed' } else { 'pending' })
    }
    notes = @(
        'Bootstrap summary created from report-data.json rather than live Tavily or Composio calls.'
    )
}

& $writeJsonUtf8 -Path $OutputPath -InputObject $summary

[pscustomobject]@{
    data = $resolvedDataPath
    summary = $OutputPath
    competitor_count = $competitors.Count
    influential_news_count = $news.Count
    semrush_evidence_count = $semrushEvidence.Count
    mode = 'bootstrap-from-report-data'
} | ConvertTo-Json -Depth 8 -Compress
