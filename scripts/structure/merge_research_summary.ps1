param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$ResearchSummaryPath
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

function Test-HasItems {
    param([object]$Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return -not [string]::IsNullOrWhiteSpace($Value) }
    return @($Value).Count -gt 0
}

function Get-IsSafeInfluentialNewsSet {
    param([object[]]$Items)

    $newsItems = @($Items)
    if ($newsItems.Count -lt 5) { return $false }

    foreach ($item in $newsItems) {
        $dateText = [string]$item.date
        if ($dateText -notmatch '^\d{1,2}\s+[A-Za-z]+\s+\d{4}$') {
            return $false
        }
    }

    return $true
}

function Merge-InfluentialNewsPreservingBadges {
    param(
        [object[]]$IncomingItems,
        [object[]]$ExistingItems,
        [string]$AssetDirectory
    )

    $incoming = @($IncomingItems)
    $existing = @($ExistingItems)
    $merged = @()

    for ($i = 0; $i -lt $incoming.Count; $i++) {
        $item = $incoming[$i]
        $existingItem = if ($i -lt $existing.Count) { $existing[$i] } else { $null }

        $hasExplicitLogo =
            -not [string]::IsNullOrWhiteSpace([string]$item.publisher_logo_url) -or
            -not [string]::IsNullOrWhiteSpace([string]$item.source_logo_url) -or
            -not [string]::IsNullOrWhiteSpace([string]$item.logo_url)

        if (-not $hasExplicitLogo -and $null -ne $existingItem) {
            foreach ($field in @('publisher_logo_url', 'source_logo_url', 'logo_url')) {
                $existingValue = [string]$existingItem.$field
                if (-not [string]::IsNullOrWhiteSpace($existingValue)) {
                    Ensure-Property -Object $item -Name $field -Value $existingValue
                }
            }
        }

        $hasExplicitLogoAfterMerge =
            -not [string]::IsNullOrWhiteSpace([string]$item.publisher_logo_url) -or
            -not [string]::IsNullOrWhiteSpace([string]$item.source_logo_url) -or
            -not [string]::IsNullOrWhiteSpace([string]$item.logo_url)

        if (-not $hasExplicitLogoAfterMerge) {
            $genericNewsBadge = Join-Path $AssetDirectory 'news.png'
            if (Test-Path -LiteralPath $genericNewsBadge) {
                Ensure-Property -Object $item -Name 'publisher_logo_url' -Value 'news.png'
            }
        }

        $merged += $item
    }

    return @($merged)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$writeJsonUtf8 = Join-Path $repoRoot 'scripts\common\write_json_utf8.ps1'

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$brandFolder = Split-Path -Parent $resolvedDataPath
$assetDirectory = Join-Path $brandFolder 'slide-assets'

if (-not $ResearchSummaryPath) {
    $ResearchSummaryPath = Join-Path $brandFolder 'research-summary.json'
}

if (-not (Test-Path -LiteralPath $ResearchSummaryPath)) {
    [pscustomobject]@{
        merged = $false
        data = $resolvedDataPath
        research_summary = $ResearchSummaryPath
        reason = 'Research summary file not found.'
    } | ConvertTo-Json -Depth 8 -Compress
    exit 0
}

$resolvedResearchSummaryPath = (Resolve-Path -LiteralPath $ResearchSummaryPath).Path
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
$summary = Get-Content -LiteralPath $resolvedResearchSummaryPath -Raw | ConvertFrom-Json

Ensure-Property -Object $data -Name 'appendix' -Value ([pscustomobject]@{})
Ensure-Property -Object $data.appendix -Name 'sources_reviewed' -Value @()
Ensure-Property -Object $data.appendix -Name 'missing_data' -Value @()
Ensure-Property -Object $data.appendix -Name 'assumptions_and_confidence_notes' -Value @()

if (Test-HasItems $summary.locked_sets.competitors) {
    Ensure-Property -Object $data.cover -Name 'competitors' -Value @($summary.locked_sets.competitors)
}

if (Get-IsSafeInfluentialNewsSet -Items @($summary.influential_news)) {
    $mergedInfluentialNews = Merge-InfluentialNewsPreservingBadges -IncomingItems @($summary.influential_news) -ExistingItems @($data.brand_reputation.influential_news) -AssetDirectory $assetDirectory
    Ensure-Property -Object $data.brand_reputation -Name 'influential_news' -Value @($mergedInfluentialNews)
}

if (Test-HasItems $summary.reputation.platform_readout) {
    Ensure-Property -Object $data.brand_reputation -Name 'platform_readout' -Value @($summary.reputation.platform_readout)
}

if (Test-HasItems $summary.reputation.recommended_actions) {
    Ensure-Property -Object $data.brand_reputation -Name 'recommended_actions' -Value @($summary.reputation.recommended_actions)
}

if (Test-HasItems $summary.seo.semrush_evidence) {
    Ensure-Property -Object $data.seo_audit -Name 'semrush_evidence' -Value @($summary.seo.semrush_evidence)
}

if (Test-HasItems $summary.seo.priority_issues) {
    Ensure-Property -Object $data.seo_audit -Name 'priority_issues' -Value @($summary.seo.priority_issues)
}

if (Test-HasItems $summary.source_map) {
    $sourceUrls = @($summary.source_map | ForEach-Object { [string]$_.url } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Ensure-Property -Object $data.appendix -Name 'sources_reviewed' -Value @($sourceUrls | Select-Object -Unique)
    Ensure-Property -Object $data.appendix -Name 'source_map' -Value @($summary.source_map)
}

if ($null -ne $summary.tavily_validation) {
    Ensure-Property -Object $data.appendix -Name 'tavily_validation' -Value $summary.tavily_validation
}

if ($null -ne $summary.locked_sets) {
    Ensure-Property -Object $data.appendix -Name 'locked_sets' -Value $summary.locked_sets
}

if ($null -ne $summary.source_provenance_summary) {
    Ensure-Property -Object $data.appendix -Name 'source_provenance_summary' -Value $summary.source_provenance_summary
}

$assumptionNotes = @()
if (Test-HasItems $summary.notes) {
    $assumptionNotes += @($summary.notes)
}
if (Test-HasItems $summary.reputation.platform_readout) {
    $assumptionNotes += @($summary.reputation.platform_readout)
}
Ensure-Property -Object $data.appendix -Name 'assumptions_and_confidence_notes' -Value @($assumptionNotes | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)

if (-not (Get-IsSafeInfluentialNewsSet -Items @($summary.influential_news))) {
    $appendixNotes = @($data.appendix.assumptions_and_confidence_notes)
    $appendixNotes += 'Imported live research summary did not replace brand_reputation.influential_news because the imported set was below the delivery-safe threshold for count or date formatting.'
    Ensure-Property -Object $data.appendix -Name 'assumptions_and_confidence_notes' -Value @($appendixNotes | Select-Object -Unique)
}

& $writeJsonUtf8 -Path $resolvedDataPath -InputObject $data

[pscustomobject]@{
    merged = $true
    data = $resolvedDataPath
    research_summary = $resolvedResearchSummaryPath
    cover_competitors = @($data.cover.competitors).Count
    influential_news = @($data.brand_reputation.influential_news).Count
    semrush_evidence = @($data.seo_audit.semrush_evidence).Count
    appendix_sources = @($data.appendix.sources_reviewed).Count
} | ConvertTo-Json -Depth 8 -Compress
