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

    $properties = $Value.PSObject.Properties
    if ($properties) {
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

$brandFolder = Split-Path -Parent $resolvedDataPath
$assetDirectory = Join-Path $brandFolder 'slide-assets'
$brandLogoPath = ''
$brandMarkPath = ''
$brandName = ''
if (Test-HasValue $data.brand) {
    $brandName = [string]$data.brand.name
    if (Test-HasValue $data.brand.logo_url) {
        $brandLogoValue = [string]$data.brand.logo_url
        if ([System.IO.Path]::IsPathRooted($brandLogoValue)) {
            $brandLogoPath = $brandLogoValue
        }
        elseif (-not [string]::IsNullOrWhiteSpace($brandLogoValue)) {
            $brandLogoPath = Join-Path $brandFolder $brandLogoValue
        }
    }
    if (Test-HasValue $data.brand.mark_url) {
        $brandMarkValue = [string]$data.brand.mark_url
        if ([System.IO.Path]::IsPathRooted($brandMarkValue)) {
            $brandMarkPath = $brandMarkValue
        }
        elseif (-not [string]::IsNullOrWhiteSpace($brandMarkValue)) {
            $brandMarkPath = Join-Path $brandFolder $brandMarkValue
        }
    }
}

$influentialNews = @($data.brand_reputation.influential_news)
if ($influentialNews.Count -lt 5) {
    $errors.Add("brand_reputation.influential_news must include at least 5 stories unless the period is explicitly documented as unusually quiet. Current count: $($influentialNews.Count)")
}
elseif ($influentialNews.Count -gt 6) {
    Add-WarningMessage("brand_reputation.influential_news contains $($influentialNews.Count) stories. NewBizIntel now aims for a concise 5 to 6 item shortlist.")
}

for ($i = 0; $i -lt $influentialNews.Count; $i++) {
    $item = $influentialNews[$i]
    $pathPrefix = "brand_reputation.influential_news[$i]"

    if (-not (Test-ExactNewsDate ([string]$item.date))) {
        $errors.Add("$pathPrefix.date must use an exact publication date like '19 November 2025'.")
    }

    if (-not (Test-NewsLogoResolvable -Item $item -AssetDirectory $assetDirectory -BrandName $brandName -BrandLogoPath $brandLogoPath -BrandMarkPath $brandMarkPath)) {
        $errors.Add("$pathPrefix must resolve to a real publisher badge asset for HTML and PPTX delivery.")
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
