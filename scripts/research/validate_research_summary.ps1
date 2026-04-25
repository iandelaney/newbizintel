param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'

function Test-HasValue {
    param([object]$Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return -not [string]::IsNullOrWhiteSpace($Value) }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        return @($Value).Count -gt 0
    }

    return $true
}

$allowedStatuses = @('pending', 'passed', 'partial', 'quota-limited', 'blocked', 'failed')
$allowedCurrentWebTools = @('tavily', 'jina', 'tavily+jina', 'jina+tavily')
$requiredValidationKeys = @('competitor_discovery', 'recent_news', 'reputation_public_web', 'source_gathering')
$requiredReputationFactors = @('source_authority', 'buyer_relevance', 'reputation_risk_or_opportunity', 'evidence_quality', 'novelty', 'recency')
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

$resolvedPath = (Resolve-Path -LiteralPath $Path).Path
$summary = Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json

foreach ($field in @('mode', 'data_path', 'brand_name', 'brand_website', 'competitors', 'influential_news', 'reputation', 'seo', 'locked_sets', 'status', 'notes')) {
    if (-not (Test-HasValue $summary.$field)) {
        $errors.Add("Missing required field: $field")
    }
}

foreach ($field in @('competitor_discovery', 'recent_news', 'reputation_public_web', 'source_gathering', 'semrush')) {
    $value = [string]$summary.status.$field
    if (-not ($allowedStatuses -contains $value)) {
        $errors.Add("status.$field must be one of: $($allowedStatuses -join ', '). Current value: '$value'")
    }
}

$ranking = $summary.influence_ranking
if (-not (Test-HasValue $ranking)) {
    $errors.Add('Missing influence_ranking. Reputation story selection must document broad discovery, scoring, and verification.')
}
else {
    if ([string]$ranking.discovery_mode -ne 'broad_first_scored_reduction') {
        $errors.Add("influence_ranking.discovery_mode must be 'broad_first_scored_reduction'.")
    }
    if ([int]$ranking.candidate_story_count -lt 12) {
        $errors.Add('influence_ranking.candidate_story_count must be at least 12.')
    }
    if (@($ranking.candidate_pool_summary).Count -lt 12) {
        $errors.Add('influence_ranking.candidate_pool_summary must list at least 12 broad-discovery candidates.')
    }
    if (@($ranking.broad_discovery_queries | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Select-Object -Unique).Count -lt 4) {
        $errors.Add('influence_ranking.broad_discovery_queries must list at least 4 broad, non-story-specific discovery queries.')
    }
    $sequence = [string]::Join(' ', @($ranking.discovery_sequence)).ToLowerInvariant()
    if ($sequence -notmatch 'broad|discover' -or $sequence -notmatch 'score|scor|reduc' -or $sequence -notmatch 'verif|target|confirm') {
        $errors.Add('influence_ranking.discovery_sequence must document broad discovery, scoring/reduction, and targeted verification.')
    }
    foreach ($factor in $requiredReputationFactors) {
        if (@($ranking.ranking_factors) -notcontains $factor) {
            $errors.Add("influence_ranking.ranking_factors must include: $($requiredReputationFactors -join ', ').")
            break
        }
    }
}

$newsScores = @()
foreach ($item in @($summary.influential_news)) {
    foreach ($field in @('date', 'headline', 'source', 'url', 'why_it_matters', 'source_type', 'sentiment', 'influence_score', 'influence_subscores', 'rank_reason')) {
        if (-not (Test-HasValue $item.$field)) {
            $errors.Add("influential_news item missing required field: $field")
        }
    }
    if (Test-HasValue $item.influence_score) {
        $newsScores += [int]$item.influence_score
    }
}
for ($i = 1; $i -lt $newsScores.Count; $i++) {
    if ($newsScores[$i] -gt $newsScores[$i - 1]) {
        $errors.Add('influential_news must be ordered by influence_score descending.')
        break
    }
}

if ($summary.mode -like 'live*') {
    if (-not (Test-HasValue $summary.tavily_validation)) {
        $errors.Add('Live research summary must include tavily_validation.')
    }
    else {
        foreach ($key in $requiredValidationKeys) {
            $entry = $summary.tavily_validation.$key
            if (-not (Test-HasValue $entry)) {
                $errors.Add("tavily_validation.$key is required for live research.")
                continue
            }

            $validationStatus = [string]$entry.status
            if (-not ($allowedStatuses -contains $validationStatus)) {
                $errors.Add("tavily_validation.$key.status must be one of: $($allowedStatuses -join ', '). Current value: '$validationStatus'")
            }
            if (-not ($allowedCurrentWebTools -contains ([string]$entry.tool))) {
                $errors.Add("tavily_validation.$key.tool must be one of: $($allowedCurrentWebTools -join ', ').")
            }
            if (-not (Test-HasValue $entry.used_in_sections)) {
                $warnings.Add("tavily_validation.$key.used_in_sections is empty.")
            }
        }
    }

    if (-not (Test-HasValue $summary.source_provenance_summary)) {
        $errors.Add('Live research summary must include source_provenance_summary.')
    }
}

[pscustomobject]@{
    ok = $errors.Count -eq 0
    path = $resolvedPath
    mode = [string]$summary.mode
    errors = @($errors)
    warnings = @($warnings)
} | ConvertTo-Json -Depth 8 -Compress
