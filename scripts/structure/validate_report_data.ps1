param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100

$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Test-HasValue {
    param([object]$Value)

    if ($null -eq $Value) {
        return $false
    }

    if ($Value -is [string]) {
        return -not [string]::IsNullOrWhiteSpace($Value)
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($item in $Value) {
            return $true
        }
        return $false
    }

    return $true
}

function Add-MissingError {
    param([string]$PathLabel)
    $errors.Add("Missing or empty required report-data field: $PathLabel")
}

function Add-WarningMessage {
    param([string]$Message)
    $warnings.Add($Message)
}

function ConvertTo-Slug {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    $slug = $Value.ToLowerInvariant() -replace '^https?://', ''
    $slug = $slug -replace '^www\.', ''
    $slug = $slug -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')
    return $slug
}

function Test-ExactNewsDate {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    return $Value -match '^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}$'
}

function Get-ExactNewsDate {
    param([string]$Value)

    if (-not (Test-ExactNewsDate $Value)) {
        return $null
    }

    try {
        return [datetime]::ParseExact($Value, 'd MMMM yyyy', [System.Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        return $null
    }
}

$script:ReputationScoreWeights = [ordered]@{
    source_authority = 0.25
    buyer_relevance = 0.25
    reputation_risk_or_opportunity = 0.20
    evidence_quality = 0.15
    novelty = 0.10
    recency = 0.05
}

$script:ReputationSourceTypes = @(
    'national_business_press',
    'trade_press',
    'financial_investor_press',
    'consumer_press',
    'review_platform',
    'regulatory_or_legal',
    'analyst_or_research',
    'industry_body',
    'owned_newsroom',
    'social_or_forum'
)

function Get-IntOrNull {
    param([object]$Value)

    if ($null -eq $Value -or $Value -is [bool]) { return $null }
    if ($Value -is [int]) { return [int]$Value }
    $text = [string]$Value
    if ($text -match '^\d+$') { return [int]$text }
    return $null
}

function Get-ReputationInfluenceScore {
    param([object]$Subscores)

    if ($null -eq $Subscores) { return $null }
    $total = 0.0
    foreach ($factor in $script:ReputationScoreWeights.Keys) {
        $value = Get-IntOrNull $Subscores.$factor
        if ($null -eq $value -or $value -lt 1 -or $value -gt 100) { return $null }
        $total += ([double]$value * [double]$script:ReputationScoreWeights[$factor])
    }
    return [int][Math]::Round($total)
}

function Test-ReputationDiscoverySequence {
    param(
        [object]$Method,
        [object[]]$FinalNews,
        [string]$PathPrefix
    )

    if ($null -eq $Method) {
        $errors.Add("$PathPrefix must describe the ranking method, candidate pool, broad discovery queries, scoring, and verification sequence.")
        return
    }

    if ([string]$Method.discovery_mode -ne 'broad_first_scored_reduction') {
        $errors.Add("$PathPrefix.discovery_mode must be 'broad_first_scored_reduction'.")
    }

    $candidateCount = Get-IntOrNull $Method.candidate_story_count
    $candidatePool = @($Method.candidate_pool_summary)
    if ($candidatePool.Count -lt 12) {
        $errors.Add("$PathPrefix.candidate_pool_summary must list at least 12 discovered candidate stories before reduction.")
    }
    elseif ($null -ne $candidateCount -and $candidatePool.Count -lt $candidateCount) {
        $errors.Add("$PathPrefix.candidate_pool_summary must contain at least candidate_story_count items.")
    }

    $broadQueries = @($Method.broad_discovery_queries) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
    $distinctBroadQueries = @($broadQueries | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Select-Object -Unique)
    if ($distinctBroadQueries.Count -lt 4) {
        $errors.Add("$PathPrefix.broad_discovery_queries must list at least 4 distinct broad, non-story-specific discovery queries.")
    }

    $sequence = @($Method.discovery_sequence) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
    if ($sequence.Count -lt 3) {
        $errors.Add("$PathPrefix.discovery_sequence must document broad discovery, scoring/reduction, and targeted verification in order.")
    }
    else {
        $broadIndex = -1
        $scoreIndex = -1
        $verifyIndex = -1
        for ($i = 0; $i -lt $sequence.Count; $i++) {
            $step = ([string]$sequence[$i]).ToLowerInvariant()
            if ($broadIndex -lt 0 -and ($step.Contains('broad') -or $step.Contains('discover'))) { $broadIndex = $i }
            if ($scoreIndex -lt 0 -and ($step.Contains('score') -or $step.Contains('scor') -or $step.Contains('reduc'))) { $scoreIndex = $i }
            if ($verifyIndex -lt 0 -and ($step.Contains('verif') -or $step.Contains('target') -or $step.Contains('confirm'))) { $verifyIndex = $i }
        }
        if ($broadIndex -lt 0 -or $scoreIndex -lt 0 -or $verifyIndex -lt 0 -or -not ($broadIndex -lt $scoreIndex -and $scoreIndex -lt $verifyIndex)) {
            $errors.Add("$PathPrefix.discovery_sequence must show broad discovery first, scoring/reduction second, and targeted verification last.")
        }
    }

    $finalSources = @($FinalNews | ForEach-Object { ([string]$_.source).ToLowerInvariant() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $finalHeadlines = @($FinalNews | ForEach-Object { ([string]$_.headline).ToLowerInvariant() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    for ($i = 0; $i -lt $broadQueries.Count; $i++) {
        $query = ([string]$broadQueries[$i]).ToLowerInvariant()
        foreach ($source in $finalSources) {
            if ($query.Contains($source)) {
                $errors.Add("$PathPrefix.broad_discovery_queries[$i] must not pre-select a final publisher/source.")
            }
        }
        $queryWords = @([regex]::Matches($query, '[a-z0-9]+') | ForEach-Object { $_.Value } | Where-Object { $_.Length -gt 2 })
        foreach ($headline in $finalHeadlines) {
            $headlineWords = @([regex]::Matches($headline, '[a-z0-9]+') | ForEach-Object { $_.Value } | Where-Object { $_.Length -gt 2 } | Select-Object -Unique)
            $overlap = @($queryWords | Where-Object { $headlineWords -contains $_ })
            if ($overlap.Count -ge 5) {
                $errors.Add("$PathPrefix.broad_discovery_queries[$i] appears to pre-select a final story headline; move story-specific checks to verification_queries.")
                break
            }
        }
    }
}

function Test-NewsLogoResolvable {
    param(
        [object]$Item,
        [string]$AssetDirectory,
        [string]$BrandName,
        [string]$BrandLogoPath,
        [string]$BrandMarkPath
    )

    $explicitLogo = @(
        [string]$Item.publisher_logo_url,
        [string]$Item.source_logo_url,
        [string]$Item.logo_url
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1

    if ($explicitLogo) {
        if ([System.IO.Path]::IsPathRooted($explicitLogo)) {
            return (Test-Path -LiteralPath $explicitLogo)
        }

        $candidate = Join-Path $AssetDirectory $explicitLogo
        if (Test-Path -LiteralPath $candidate) {
            return $true
        }
    }

    $source = [string]$Item.source
    if (
        -not [string]::IsNullOrWhiteSpace($source) -and
        -not [string]::IsNullOrWhiteSpace($BrandName) -and
        $source.Trim().ToLowerInvariant() -eq $BrandName.Trim().ToLowerInvariant()
    ) {
        if ((-not [string]::IsNullOrWhiteSpace($BrandMarkPath)) -and (Test-Path -LiteralPath $BrandMarkPath)) {
            return $true
        }
        if ((-not [string]::IsNullOrWhiteSpace($BrandLogoPath)) -and (Test-Path -LiteralPath $BrandLogoPath)) {
            return $true
        }
    }

    $namesToTry = New-Object System.Collections.Generic.List[string]
    $sourceSlug = ConvertTo-Slug $source
    if (-not [string]::IsNullOrWhiteSpace($sourceSlug)) {
        foreach ($name in @(
            "$sourceSlug-news.png",
            "$sourceSlug-favicon.png",
            "$sourceSlug-logo.png",
            "$sourceSlug.png"
        )) {
            $namesToTry.Add($name)
        }
    }

    $url = [string]$Item.url
    if (-not [string]::IsNullOrWhiteSpace($url)) {
        try {
            $uri = [System.Uri]$url
            $hostSlug = ConvertTo-Slug $uri.Host
            if (-not [string]::IsNullOrWhiteSpace($hostSlug)) {
                foreach ($name in @(
                    "$hostSlug-news.png",
                    "$hostSlug-favicon.png",
                    "$hostSlug-logo.png",
                    "$hostSlug.png"
                )) {
                    $namesToTry.Add($name)
                }
            }
        }
        catch {
        }
    }

    foreach ($name in $namesToTry) {
        if (Test-Path -LiteralPath (Join-Path $AssetDirectory $name)) {
            return $true
        }
    }

    return $false
}

function Test-ContainsEscapedPunctuationEntity {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    return $Value -match '&#0*39;|&apos;|&#x0*27;'
}

function Find-EscapedPunctuationEntityPaths {
    param(
        [object]$Value,
        [string]$PathLabel = '$'
    )

    $hits = New-Object System.Collections.Generic.List[string]

    if ($null -eq $Value) {
        return $hits
    }

    if ($Value -is [string]) {
        if (Test-ContainsEscapedPunctuationEntity $Value) {
            $hits.Add($PathLabel)
        }
        return $hits
    }

    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) {
            foreach ($hit in (Find-EscapedPunctuationEntityPaths -Value $Value[$key] -PathLabel "$PathLabel.$key")) {
                $hits.Add($hit)
            }
        }
        return $hits
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $index = 0
        foreach ($item in $Value) {
            foreach ($hit in (Find-EscapedPunctuationEntityPaths -Value $item -PathLabel "$PathLabel[$index]")) {
                $hits.Add($hit)
            }
            $index++
        }
        return $hits
    }

    $properties = @($Value.PSObject.Properties | Where-Object { $_.MemberType -eq 'NoteProperty' })
    if ($properties.Count -gt 0) {
        foreach ($property in $properties) {
            foreach ($hit in (Find-EscapedPunctuationEntityPaths -Value $property.Value -PathLabel "$PathLabel.$($property.Name)")) {
                $hits.Add($hit)
            }
        }
    }

    return $hits
}

if (-not (Test-HasValue $data.report_meta)) { Add-MissingError 'report_meta' }
if (-not (Test-HasValue $data.agency_opportunity)) { Add-MissingError 'agency_opportunity' }
if (-not (Test-HasValue $data.usp_ksp_review)) { Add-MissingError 'usp_ksp_review' }

if (Test-HasValue $data.report_meta) {
    if (-not (Test-HasValue $data.report_meta.audience)) { Add-MissingError 'report_meta.audience' }
    if (-not (Test-HasValue $data.report_meta.distribution)) { Add-MissingError 'report_meta.distribution' }
    if (-not (Test-HasValue $data.report_meta.purpose)) { Add-MissingError 'report_meta.purpose' }
}

if (Test-HasValue $data.agency_opportunity) {
    if (-not (Test-HasValue $data.agency_opportunity.score)) { Add-MissingError 'agency_opportunity.score' }
    if (-not (Test-HasValue $data.agency_opportunity.score_summary)) { Add-MissingError 'agency_opportunity.score_summary' }
    if (-not (Test-HasValue $data.agency_opportunity.summary)) { Add-MissingError 'agency_opportunity.summary' }
    if (-not (Test-HasValue $data.agency_opportunity.cards)) { Add-MissingError 'agency_opportunity.cards' }
    if (-not (Test-HasValue $data.agency_opportunity.priority_workstreams)) { Add-MissingError 'agency_opportunity.priority_workstreams' }
    if (-not (Test-HasValue $data.agency_opportunity.archetype_advantages)) { Add-MissingError 'agency_opportunity.archetype_advantages' }
    if (-not (Test-HasValue $data.agency_opportunity.department_opportunity_map)) { Add-MissingError 'agency_opportunity.department_opportunity_map' }
    else {
        $departmentIndex = 0
        foreach ($departmentItem in @($data.agency_opportunity.department_opportunity_map)) {
            if (-not (Test-HasValue $departmentItem.department)) { Add-MissingError "agency_opportunity.department_opportunity_map[$departmentIndex].department" }
            if (-not (Test-HasValue $departmentItem.opportunity_signal)) { Add-MissingError "agency_opportunity.department_opportunity_map[$departmentIndex].opportunity_signal" }
            $departmentIndex += 1
        }
    }

    $leadOffering = $data.agency_opportunity.lead_offering
    if (-not (Test-HasValue $leadOffering)) {
        Add-MissingError 'agency_opportunity.lead_offering'
    }
    else {
        if (-not (Test-HasValue $leadOffering.name)) { Add-MissingError 'agency_opportunity.lead_offering.name' }
        if (-not (Test-HasValue $leadOffering.lead_department)) { Add-MissingError 'agency_opportunity.lead_offering.lead_department' }
        if (-not (Test-HasValue $leadOffering.supporting_departments)) { Add-MissingError 'agency_opportunity.lead_offering.supporting_departments' }
        if (-not (Test-HasValue $leadOffering.verdict)) { Add-MissingError 'agency_opportunity.lead_offering.verdict' }
        if (-not (Test-HasValue $leadOffering.why_this_leads)) { Add-MissingError 'agency_opportunity.lead_offering.why_this_leads' }
        if (-not (Test-HasValue $leadOffering.why_not_first)) { Add-MissingError 'agency_opportunity.lead_offering.why_not_first' }
        if (-not (Test-HasValue $leadOffering.best_buyer)) { Add-MissingError 'agency_opportunity.lead_offering.best_buyer' }
        if (-not (Test-HasValue $leadOffering.expected_outcomes)) { Add-MissingError 'agency_opportunity.lead_offering.expected_outcomes' }
    }
}

if (Test-HasValue $data.usp_ksp_review) {
    if (-not (Test-HasValue $data.usp_ksp_review.score)) { Add-MissingError 'usp_ksp_review.score' }
    if (-not (Test-HasValue $data.usp_ksp_review.score_summary)) { Add-MissingError 'usp_ksp_review.score_summary' }
    if (-not (Test-HasValue $data.usp_ksp_review.summary)) { Add-MissingError 'usp_ksp_review.summary' }
    if (-not (Test-HasValue $data.usp_ksp_review.rows)) { Add-MissingError 'usp_ksp_review.rows' }

    $overallVerdict = $data.usp_ksp_review.overall_verdict
    if (-not (Test-HasValue $overallVerdict)) {
        Add-MissingError 'usp_ksp_review.overall_verdict'
    }
    else {
        if (-not (Test-HasValue $overallVerdict.headline)) { Add-MissingError 'usp_ksp_review.overall_verdict.headline' }
        if (-not (Test-HasValue $overallVerdict.uniqueness_verdict)) { Add-MissingError 'usp_ksp_review.overall_verdict.uniqueness_verdict' }
        if (-not (Test-HasValue $overallVerdict.who_for)) { Add-MissingError 'usp_ksp_review.overall_verdict.who_for' }
    }
}

if (-not (Test-HasValue $data.storybrand)) {
    Add-MissingError 'storybrand'
}
else {
    if (-not (Test-HasValue $data.storybrand.existing_messaging_assessment.summary)) { Add-MissingError 'storybrand.existing_messaging_assessment.summary' }
    if (-not (Test-HasValue $data.storybrand.existing_messaging_assessment.published_statements)) { Add-MissingError 'storybrand.existing_messaging_assessment.published_statements' }
    if (-not (Test-HasValue $data.storybrand.existing_messaging_assessment.reputation_read_across)) { Add-MissingError 'storybrand.existing_messaging_assessment.reputation_read_across' }
    if (-not (Test-HasValue $data.storybrand.existing_messaging_assessment.implication)) { Add-MissingError 'storybrand.existing_messaging_assessment.implication' }
    if (-not (Test-HasValue $data.storybrand.messaging_fixes)) { Add-MissingError 'storybrand.messaging_fixes' }
    if (-not (Test-HasValue $data.storybrand.content_implications)) { Add-MissingError 'storybrand.content_implications' }

    $publishedStatements = @($data.storybrand.existing_messaging_assessment.published_statements)
    $storybrandCards = @($data.storybrand.cards)
    if ($publishedStatements.Count -lt 2) {
        $errors.Add("storybrand.existing_messaging_assessment.published_statements must include at least 2 mission, purpose, promise, or proposition statements.")
    }
    if ($storybrandCards.Count -lt 6) {
        $errors.Add("storybrand.cards must include a full StoryBrand card set, not a partial scaffold.")
    }
    $sourceUrls = New-Object System.Collections.Generic.HashSet[string]
    for ($i = 0; $i -lt $publishedStatements.Count; $i++) {
        $item = $publishedStatements[$i]
        $pathPrefix = "storybrand.existing_messaging_assessment.published_statements[$i]"
        if (-not (Test-HasValue $item.label)) { Add-MissingError "$pathPrefix.label" }
        if (-not (Test-HasValue $item.statement)) { Add-MissingError "$pathPrefix.statement" }
        if (-not (Test-HasValue $item.source)) { Add-MissingError "$pathPrefix.source" }
        if (-not (Test-HasValue $item.source_url)) { Add-MissingError "$pathPrefix.source_url" }
        if (Test-HasValue $item.source_url) { [void]$sourceUrls.Add(([string]$item.source_url).Trim().TrimEnd('/').ToLowerInvariant()) }
    }

    $websiteRoot = ([string]$data.brand.website).Trim().TrimEnd('/').ToLowerInvariant()
    if ($sourceUrls.Count -gt 0) {
        $allHomepage = $true
        foreach ($url in $sourceUrls) {
            if ($url -ne $websiteRoot) {
                $allHomepage = $false
                break
            }
        }
        if ($allHomepage) {
            $errors.Add("storybrand.existing_messaging_assessment must cite at least one specific official source page, not only the homepage root.")
        }
    }

    $storybrandText = [string]::Join(' ', @(
        [string]$data.storybrand.existing_messaging_assessment.summary,
        [string]$data.storybrand.existing_messaging_assessment.reputation_read_across,
        [string]$data.storybrand.existing_messaging_assessment.implication,
        [string]$data.storybrand.one_liner,
        ([string]::Join(' ', @($data.storybrand.messaging_fixes))),
        ([string]::Join(' ', @($data.storybrand.content_implications))),
        ([string]::Join(' ', @($storybrandCards | ForEach-Object { [string]$_.body })))
    )).ToLowerInvariant()
    foreach ($snippet in @(
        'the buyer or customer wants a simpler, more confident path to the outcome the brand promises',
        'feel reassured that the promise is credible, the route is clear, and the experience will stand up under scrutiny',
        'confidence drift: the repeated friction of comparison, unclear proof',
        'clear proof points, visible controls, customer feedback loops, service-recovery evidence',
        'understand the offer, compare the options fairly, see the proof',
        'take the next high-intent step with confidence',
        'the brand feels easier to trust, easier to choose, and easier to stay with',
        'helps customers achieve the promised outcome with clearer choices, stronger proof, and visible control throughout the journey'
    )) {
        if ($storybrandText -like "*$snippet*") {
            $errors.Add("storybrand contains generic reusable card language instead of brand-specific messaging evidence.")
            break
        }
    }

    foreach ($fieldName in @('messaging_fixes', 'content_implications')) {
        $items = @($data.storybrand.$fieldName)
        if ($items.Count -lt 2) {
            $errors.Add("storybrand.$fieldName must include at least 2 rationale-led recommendations.")
        }
        for ($i = 0; $i -lt $items.Count; $i++) {
            $text = [string]$items[$i]
            if ($text -notmatch '(?i)\bwhy:|\bbecause\b') {
                $errors.Add("storybrand.$fieldName[$i] must explain the WHY behind the recommendation.")
            }
            if ($text -notmatch '(?i)reputation|trust|review|service|growth|proof|technology|customer') {
                $errors.Add("storybrand.$fieldName[$i] must show read-across from reputation findings or customer evidence.")
            }
        }
    }
}

if (-not (Test-HasValue $data.seo_audit)) {
    Add-MissingError 'seo_audit'
}
else {
    if (-not (Test-HasValue $data.seo_audit.cards)) { Add-MissingError 'seo_audit.cards' }
    if (-not (Test-HasValue $data.seo_audit.semrush_evidence)) { Add-MissingError 'seo_audit.semrush_evidence' }
    if (-not (Test-HasValue $data.seo_audit.priority_issues)) { Add-MissingError 'seo_audit.priority_issues' }
    if (-not (Test-HasValue $data.seo_audit.content_implications)) { Add-MissingError 'seo_audit.content_implications' }

    $semrushEvidence = @($data.seo_audit.semrush_evidence)
    if ($semrushEvidence.Count -lt 2) {
        $errors.Add("seo_audit.semrush_evidence must include at least 2 compact SEMrush-backed proof points. Current count: $($semrushEvidence.Count)")
    }

    for ($i = 0; $i -lt $semrushEvidence.Count; $i++) {
        $item = $semrushEvidence[$i]
        $pathPrefix = "seo_audit.semrush_evidence[$i]"

        if (-not (Test-HasValue $item.title)) { Add-MissingError "$pathPrefix.title" }
        if (-not (Test-HasValue $item.body)) { Add-MissingError "$pathPrefix.body" }

        $evidenceText = [string]::Join(' ', @(
            [string]$item.title,
            [string]$item.body
        ))
        if ($evidenceText -match '(?i)semrush was unavailable|without semrush|no semrush|semrush unavailable') {
            $errors.Add("$pathPrefix cannot say SEMrush was unavailable in a report that is passing the SEO gate.")
        }
    }

    $seoTextFragments = New-Object System.Collections.Generic.List[string]
    foreach ($card in @($data.seo_audit.cards)) {
        if (Test-HasValue $card.title) { $seoTextFragments.Add([string]$card.title) }
        if (Test-HasValue $card.body) { $seoTextFragments.Add([string]$card.body) }
    }
    foreach ($item in @($data.seo_audit.priority_issues)) {
        if (Test-HasValue $item.issue) { $seoTextFragments.Add([string]$item.issue) }
        if (Test-HasValue $item.evidence) { $seoTextFragments.Add([string]$item.evidence) }
        if (Test-HasValue $item.why_it_matters) { $seoTextFragments.Add([string]$item.why_it_matters) }
        if (Test-HasValue $item.recommended_fix) { $seoTextFragments.Add([string]$item.recommended_fix) }
    }
    foreach ($item in @($data.seo_audit.content_implications)) {
        if (Test-HasValue $item) { $seoTextFragments.Add([string]$item) }
    }

    $seoCombinedText = [string]::Join(' ', $seoTextFragments)
    if ($seoCombinedText -match '(?i)semrush was unavailable|without semrush|no semrush|semrush unavailable') {
        $errors.Add('seo_audit cannot claim SEMrush was unavailable if Gate 3A has passed.')
    }

    $seoCharts = @($data.seo_audit.charts)
    for ($i = 0; $i -lt $seoCharts.Count; $i++) {
        $chart = $seoCharts[$i]
        $titleAndSubtitle = "$($chart.title) $($chart.subtitle)"
        if ($titleAndSubtitle -match '(?i)strategic read from public evidence') {
            $errors.Add("seo_audit.charts[$i] uses a vague strategic-read label; SEO charts must name the metric basis or say they are indexed interpretation.")
        }
        if (-not (Test-HasValue $chart.subtitle)) {
            Add-MissingError "seo_audit.charts[$i].subtitle"
        }
        elseif ($titleAndSubtitle -notmatch '(?i)semrush|similarweb|gsc|search console|traffic|keyword|rank|organic|paid search|direct|indexed|search') {
            $errors.Add("seo_audit.charts[$i].subtitle must name the SEO/search evidence basis, such as SEMrush, Similarweb, traffic, keyword, rank, or indexed interpretation.")
        }
        $series = @($chart.series)
        for ($j = 0; $j -lt $series.Count; $j++) {
            if ([string]$series[$j].note -notmatch '(?i)semrush|similarweb|gsc|search console|traffic|keyword|rank|organic|paid search|direct|indexed|search') {
                $errors.Add("seo_audit.charts[$i].series[$j].note must cite the underlying search or traffic signal.")
            }
        }
    }
}

if (-not (Test-HasValue $data.opportunities.marketing_strategy.strategy)) { Add-MissingError 'opportunities.marketing_strategy.strategy' }
if (-not (Test-HasValue $data.opportunities.marketing_strategy.why_it_matters)) { Add-MissingError 'opportunities.marketing_strategy.why_it_matters' }
if (-not (Test-HasValue $data.opportunities.marketing_strategy.evidence_threads)) { Add-MissingError 'opportunities.marketing_strategy.evidence_threads' }
$strategyThreads = @($data.opportunities.marketing_strategy.evidence_threads)
if ($strategyThreads.Count -lt 4) {
    $errors.Add("opportunities.marketing_strategy.evidence_threads must include at least 4 cross-report finding threads.")
}
$strategyText = [string]::Join(' ', @(
    [string]$data.opportunities.marketing_strategy.headline,
    [string]$data.opportunities.marketing_strategy.strategy,
    [string]$data.opportunities.marketing_strategy.why_it_matters
) + $strategyThreads)
$missingStrategyDimensions = New-Object System.Collections.Generic.List[string]
if ($strategyText -notmatch '(?i)reputation|trust|review|news') { $missingStrategyDimensions.Add('reputation') }
if ($strategyText -notmatch '(?i)messaging|proof|promise|storybrand') { $missingStrategyDimensions.Add('messaging/proof') }
if ($strategyText -notmatch '(?i)search|seo|organic|direct demand|keyword') { $missingStrategyDimensions.Add('search/SEO') }
if ($strategyText -notmatch '(?i)competitor|tesco|sainsbury|asda|waitrose|market') { $missingStrategyDimensions.Add('competitor') }
if ($strategyText -notmatch '(?i)campaign|content|creative|hub|crm') { $missingStrategyDimensions.Add('campaign/content') }
if ($missingStrategyDimensions.Count -gt 0) {
    $errors.Add("opportunities.marketing_strategy must synthesise findings from reputation, messaging/proof, search/SEO, competitor, and campaign/content sections; missing: $([string]::Join(', ', $missingStrategyDimensions))")
}

if (Test-HasValue $data.company_snapshot.items) {
    foreach ($item in @($data.company_snapshot.items)) {
        $label = [string]$item.label
        $value = [string]$item.value
        $profiles = @($item.profiles) + @($item.linkedin_profiles)

        if ([string]::IsNullOrWhiteSpace($label) -or [string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        if ($label -match 'Founder|Leadership|Board' -and $profiles.Count -eq 0) {
            Add-WarningMessage("Company snapshot item '$label' names people or governance signals but has no profile links. Add profiles[] entries when public LinkedIn or equivalent sources are available.")
        }
    }
}

$escapedEntityHits = @(Find-EscapedPunctuationEntityPaths -Value $data -PathLabel '$')
foreach ($hit in $escapedEntityHits) {
    $errors.Add("Report data contains an HTML entity where normal punctuation should be used: $hit")
}

$influentialNews = @($data.brand_reputation.influential_news)
if ($influentialNews.Count -lt 5) {
    $errors.Add("brand_reputation.influential_news must include at least 5 stories unless the period is explicitly documented as unusually quiet. Current count: $($influentialNews.Count)")
}
elseif ($influentialNews.Count -gt 6) {
    Add-WarningMessage("brand_reputation.influential_news contains $($influentialNews.Count) stories. NewBizIntel now aims for a concise 5 to 6 item shortlist.")
}

$influenceRanking = $data.brand_reputation.influence_ranking
Test-ReputationDiscoverySequence -Method $influenceRanking -FinalNews $influentialNews -PathPrefix 'brand_reputation.influence_ranking'

if ($null -ne $influenceRanking) {
    $candidateCount = Get-IntOrNull $influenceRanking.candidate_story_count
    if ($null -eq $candidateCount -or $candidateCount -lt 12) {
        $errors.Add('brand_reputation.influence_ranking.candidate_story_count must be at least 12 before reduction to the final ranked set.')
    }

    $searchQueries = @($influenceRanking.search_queries) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
    if ((@($searchQueries | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Select-Object -Unique)).Count -lt 4) {
        $errors.Add('brand_reputation.influence_ranking.search_queries must list at least 4 distinct search queries.')
    }

    if ([string]::IsNullOrWhiteSpace([string]$influenceRanking.ranking_method) -or ([string]$influenceRanking.ranking_method) -notmatch '(?i)score') {
        $errors.Add('brand_reputation.influence_ranking.ranking_method must explain the influence scoring approach.')
    }

    $confidenceScore = Get-IntOrNull $influenceRanking.confidence_score
    if ($null -eq $confidenceScore -or $confidenceScore -lt 70 -or $confidenceScore -gt 100) {
        $errors.Add('brand_reputation.influence_ranking.confidence_score must be an integer from 70 to 100 for the gate to pass.')
    }

    if ([string]::IsNullOrWhiteSpace([string]$influenceRanking.confidence_rationale)) {
        $errors.Add('brand_reputation.influence_ranking.confidence_rationale must explain why the final ranking is reliable enough to use.')
    }

    if (@($influenceRanking.limitations | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -eq 0) {
        $errors.Add('brand_reputation.influence_ranking.limitations must disclose coverage caveats, even when confidence is high.')
    }

    $rankingFactors = @($influenceRanking.ranking_factors)
    foreach ($factor in $script:ReputationScoreWeights.Keys) {
        if ($rankingFactors -notcontains $factor) {
            $errors.Add("brand_reputation.influence_ranking.ranking_factors must include: $($script:ReputationScoreWeights.Keys -join ', ').")
            break
        }
    }

    foreach ($factor in $script:ReputationScoreWeights.Keys) {
        $actual = $null
        try { $actual = [double]$influenceRanking.score_weights.$factor } catch { $actual = $null }
        $expected = [double]$script:ReputationScoreWeights[$factor]
        if ($null -eq $actual -or [Math]::Abs($actual - $expected) -gt 0.0001) {
            $errors.Add("brand_reputation.influence_ranking.score_weights.$factor must be $expected.")
        }
    }
}

$seenSources = New-Object System.Collections.Generic.List[string]
$seenSourceTypes = New-Object System.Collections.Generic.List[string]
$influenceScores = New-Object System.Collections.Generic.List[int]
$newsWindowEnd = (Get-Date).Date
$newsWindowStart = $newsWindowEnd.AddMonths(-6)

for ($i = 0; $i -lt $influentialNews.Count; $i++) {
    $item = $influentialNews[$i]
    $pathPrefix = "brand_reputation.influential_news[$i]"

    foreach ($field in @('date', 'headline', 'source', 'url', 'why_it_matters', 'source_type', 'sentiment', 'rank_reason')) {
        if (-not (Test-HasValue $item.$field)) {
            Add-MissingError "$pathPrefix.$field"
        }
    }

    if (-not (Test-ExactNewsDate ([string]$item.date))) {
        $errors.Add("$pathPrefix.date must use an exact publication date like '19 November 2025'.")
    }
    else {
        $parsedDate = Get-ExactNewsDate ([string]$item.date)
        if ($null -eq $parsedDate) {
            $errors.Add("$pathPrefix.date could not be parsed as an exact day-month-year publication date.")
        }
        elseif ($parsedDate.Date -lt $newsWindowStart -or $parsedDate.Date -gt $newsWindowEnd) {
            $errors.Add("$pathPrefix.date must fall within the last six months. Cutoff for this run is $($newsWindowStart.ToString('dd MMMM yyyy')); found $($parsedDate.ToString('dd MMMM yyyy')).")
        }
    }

    if (-not ([string]$item.url).StartsWith('http://') -and -not ([string]$item.url).StartsWith('https://')) {
        $errors.Add("$pathPrefix.url must be an http(s) URL.")
    }

    $score = Get-IntOrNull $item.influence_score
    if ($null -eq $score -or $score -lt 1 -or $score -gt 100) {
        $errors.Add("$pathPrefix.influence_score must be an integer from 1 to 100.")
    }
    else {
        $influenceScores.Add($score)
    }

    $calculatedScore = Get-ReputationInfluenceScore $item.influence_subscores
    if ($null -eq $calculatedScore) {
        $errors.Add("$pathPrefix.influence_subscores must provide integer values from 1 to 100 for: $($script:ReputationScoreWeights.Keys -join ', ').")
    }
    elseif ($null -ne $score -and $calculatedScore -ne $score) {
        $errors.Add("$pathPrefix.influence_score must equal the weighted subscore calculation ($calculatedScore); found $score.")
    }

    $sourceType = [string]$item.source_type
    if ($script:ReputationSourceTypes -notcontains $sourceType) {
        $errors.Add("$pathPrefix.source_type must be one of: $($script:ReputationSourceTypes -join ', ').")
    }
    elseif (-not [string]::IsNullOrWhiteSpace($sourceType)) {
        $seenSourceTypes.Add($sourceType)
    }

    $source = ([string]$item.source).Trim().ToLowerInvariant()
    if (-not [string]::IsNullOrWhiteSpace($source)) {
        $seenSources.Add($source)
    }
}

if ($influentialNews.Count -ge 5 -and (@($seenSources | Select-Object -Unique)).Count -lt 3) {
    $errors.Add('brand_reputation.influential_news must include at least 3 distinct publishers/sources.')
}

$sourceCounts = @{}
foreach ($source in $seenSources) {
    if (-not $sourceCounts.ContainsKey($source)) { $sourceCounts[$source] = 0 }
    $sourceCounts[$source] += 1
}
$repeatedSources = @($sourceCounts.Keys | Where-Object { $sourceCounts[$_] -gt 2 })
if ($repeatedSources.Count -gt 0) {
    $errors.Add("brand_reputation.influential_news must not include more than 2 stories from the same publisher/source: $($repeatedSources -join ', ').")
}

if ((@($seenSourceTypes | Select-Object -Unique)).Count -lt 3) {
    $errors.Add('brand_reputation.influential_news must cover at least 3 source classes, not just one channel.')
}

for ($i = 1; $i -lt $influenceScores.Count; $i++) {
    if ($influenceScores[$i] -gt $influenceScores[$i - 1]) {
        $errors.Add('brand_reputation.influential_news must be ordered by influence_score descending.')
        break
    }
}

if ($errors.Count -gt 0) {
    $message = @(
        'Report data schema validation failed.'
        'This brand folder is missing required fields from the current NewBizIntel format.'
        'Update report-data.json from the latest template before rendering.'
        ''
    ) + @($errors)

    throw ($message -join [Environment]::NewLine)
}

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    warnings = @($warnings)
} | ConvertTo-Json -Depth 3 -Compress
