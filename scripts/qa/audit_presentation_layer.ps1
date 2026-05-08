param(
    [Parameter(Mandatory = $true)]
    [string]$HtmlPath,

    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

$resolvedHtmlPath = (Resolve-Path -LiteralPath $HtmlPath).Path
$html = Get-Content -LiteralPath $resolvedHtmlPath -Raw

$data = $null
if ($DataPath) {
    $resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
    $data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
}

function Add-Issue {
    param(
        [string]$Bucket,
        [string]$Message
    )

    $script:audit[$Bucket] += $Message
}

function Get-ItemCount {
    param(
        $Value
    )

    if ($null -eq $Value) {
        return 0
    }

    if ($Value -is [string]) {
        return 1
    }

    if ($Value -is [System.Collections.IEnumerable]) {
        $count = 0
        foreach ($item in $Value) {
            $count++
        }
        return $count
    }

    return 1
}

function Test-GeneratedLogoFallbackPath {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    try {
        $leaf = Split-Path -Leaf $Value
    }
    catch {
        $leaf = $Value
    }

    return ($leaf -match '(?i)-pptx-logo\.(png|jpe?g|webp|svg)$')
}

function Test-CssClassCoverage {
    param(
        [string]$ClassName,
        [string]$CssText
    )

    $escapedClass = [regex]::Escape($ClassName)
    if ($CssText -match "(?m)\.${escapedClass}(?![A-Za-z0-9_-])") {
        return $true
    }

    if ($ClassName -match '--') {
        $baseClass = $ClassName -replace '--.*$', ''
        $escapedBaseClass = [regex]::Escape($baseClass)
        if ($CssText -match "(?m)\.${escapedBaseClass}(?![A-Za-z0-9_-])") {
            return $true
        }
    }

    return $false
}

function Get-DomainStem {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    try {
        $uri = [System.Uri]$Value
        $hostName = $uri.Host.ToLowerInvariant()
    }
    catch {
        $hostName = $Value.ToLowerInvariant()
    }

    $hostName = $hostName -replace '^www\.', ''
    return $hostName
}

function Get-ClassMatches {
    param(
        [string]$SourceHtml
    )

    $classMatches = [regex]::Matches($SourceHtml, 'class\s*=\s*"([^"]+)"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $classes = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($match in $classMatches) {
        foreach ($className in ($match.Groups[1].Value -split '\s+')) {
            if (-not [string]::IsNullOrWhiteSpace($className)) {
                [void]$classes.Add($className.Trim())
            }
        }
    }
    return $classes
}

$script:audit = @{
    errors = New-Object 'System.Collections.Generic.List[string]'
    warnings = New-Object 'System.Collections.Generic.List[string]'
    checks = [ordered]@{}
}

if ($html -match '(?i)file:///') {
    Add-Issue -Bucket 'errors' -Message 'Rendered HTML contains local file URIs.'
}

$styleMatches = [regex]::Matches($html, '<style\b[^>]*>(.*?)</style>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [System.Text.RegularExpressions.RegexOptions]::Singleline)
if ($styleMatches.Count -eq 0) {
    Add-Issue -Bucket 'errors' -Message 'Rendered HTML does not contain any embedded style blocks.'
    $cssText = ''
} else {
    $cssText = ($styleMatches | ForEach-Object { $_.Groups[1].Value }) -join "`n"
}

$usedClasses = Get-ClassMatches -SourceHtml $html
$missingStyledClasses = New-Object 'System.Collections.Generic.List[string]'
foreach ($className in $usedClasses) {
    if (-not (Test-CssClassCoverage -ClassName $className -CssText $cssText)) {
        [void]$missingStyledClasses.Add($className)
    }
}

$script:audit.checks.class_count = $usedClasses.Count
$script:audit.checks.missing_css_coverage = @($missingStyledClasses | Sort-Object -Unique)

if ($missingStyledClasses.Count -gt 0) {
    Add-Issue -Bucket 'warnings' -Message ("Rendered HTML uses classes without direct CSS coverage: {0}" -f (($script:audit.checks.missing_css_coverage -join ', ')))
}

$tocTargets = [regex]::Matches($html, '<a\b[^>]*href="#([^"]+)"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase) |
    ForEach-Object { $_.Groups[1].Value } |
    Sort-Object -Unique
$headingIds = [regex]::Matches($html, '\sid="([^"]+)"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase) |
    ForEach-Object { $_.Groups[1].Value } |
    Sort-Object -Unique
$missingIds = $tocTargets | Where-Object { $_ -notin $headingIds }
$script:audit.checks.contents_targets = $tocTargets.Count
if ($missingIds) {
    Add-Issue -Bucket 'errors' -Message ("Contents links point to missing section ids: {0}" -f ($missingIds -join ', '))
}

$imageSources = [regex]::Matches($html, '<img\b[^>]*\bsrc="([^"]*)"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase) |
    ForEach-Object { $_.Groups[1].Value }
$emptyImageSources = $imageSources | Where-Object { [string]::IsNullOrWhiteSpace($_) }
if ($emptyImageSources) {
    Add-Issue -Bucket 'errors' -Message 'Rendered HTML contains image tags with empty src attributes.'
}
$externalImages = $imageSources | Where-Object { $_ -match '(?i)^https?://' }
$script:audit.checks.image_count = @($imageSources).Count
$script:audit.checks.external_image_count = @($externalImages).Count

if ($data) {
    $creativeIdeas = $null
    $creativeSection = $null
    if ($null -ne $data.creative_campaign_ideas) {
        $creativeSection = $data.creative_campaign_ideas
        $creativeIdeas = $data.creative_campaign_ideas.ideas
    }
    elseif ($null -ne $data.creative_campaigns) {
        $creativeSection = $data.creative_campaigns
        $creativeIdeas = $data.creative_campaigns.ideas
    }

    $expectedIdeaCount = Get-ItemCount -Value $creativeIdeas
    $renderedIdeaCount = [regex]::Matches($html, 'class="[^"]*\bidea-card\b', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    $script:audit.checks.expected_idea_cards = $expectedIdeaCount
    $script:audit.checks.rendered_idea_cards = $renderedIdeaCount
    if ($expectedIdeaCount -gt 0 -and $renderedIdeaCount -lt $expectedIdeaCount) {
        Add-Issue -Bucket 'errors' -Message ("Creative campaign cards are incomplete. Expected {0}, found {1}." -f $expectedIdeaCount, $renderedIdeaCount)
    }

    $creativeDeliveryMode = ''
    if ($null -ne $creativeSection) {
        $creativeDeliveryMode = [string]$creativeSection.artwork_delivery_mode
    }
    $creativeStyleMode = ''
    if ($null -ne $creativeSection) {
        $creativeStyleMode = [string]$creativeSection.illustration_style_mode
    }
    if ([string]::IsNullOrWhiteSpace($creativeDeliveryMode) -and $creativeStyleMode -match '^(?i)surprise|wild|shuffle|random$') {
        $creativeDeliveryMode = 'final-raster-required'
    }
    $script:audit.checks.campaign_artwork_delivery_mode = $creativeDeliveryMode

    if ($creativeDeliveryMode -eq 'final-raster-required') {
        $nonFinalArtIdeas = @()
        foreach ($idea in @($creativeIdeas)) {
            $role = [string]$idea.illustration_asset_role
            if ([string]::IsNullOrWhiteSpace($role) -or $role -ne 'final-raster-artwork') {
                $nonFinalArtIdeas += ([string]$idea.title)
            }
        }
        if ($nonFinalArtIdeas.Count -gt 0) {
            Add-Issue -Bucket 'errors' -Message ("Creative campaign artwork is still scaffold or unverified for a final-raster-required report: {0}" -f ($nonFinalArtIdeas -join ', '))
        }
    }

    $expectedChartCount = Get-ItemCount -Value $data.seo_audit.charts
    $renderedChartCount = [regex]::Matches($html, 'class="[^"]*\bchart-card\b', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    $script:audit.checks.expected_seo_charts = $expectedChartCount
    $script:audit.checks.rendered_seo_charts = $renderedChartCount
    if ($expectedChartCount -gt 0) {
        $requiredChartClasses = @('chart-grid', 'chart-card', 'chart-row', 'chart-bar-track', 'chart-bar-fill', 'chart-value')
        $missingChartClasses = $requiredChartClasses | Where-Object { -not (Test-CssClassCoverage -ClassName $_ -CssText $cssText) }
        if ($renderedChartCount -lt $expectedChartCount) {
            Add-Issue -Bucket 'errors' -Message ("SEO charts are incomplete. Expected {0}, found {1}." -f $expectedChartCount, $renderedChartCount)
        }
        if ($missingChartClasses) {
            Add-Issue -Bucket 'errors' -Message ("SEO chart styling contract is incomplete. Missing CSS for: {0}" -f ($missingChartClasses -join ', '))
        }
    }

    $expectedCompetitorCount = Get-ItemCount -Value $data.competitive_landscape.table
    $renderedCompetitorCount = [regex]::Matches($html, 'class="[^"]*\bcompetitor-cell\b', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    $competitorFallbackCount = [regex]::Matches($html, 'class="[^"]*\bcompetitor-badge--fallback\b', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    $script:audit.checks.expected_competitors = $expectedCompetitorCount
    $script:audit.checks.rendered_competitors = $renderedCompetitorCount
    $script:audit.checks.competitor_logo_fallbacks = $competitorFallbackCount
    if ($expectedCompetitorCount -gt 0 -and $renderedCompetitorCount -lt $expectedCompetitorCount) {
        Add-Issue -Bucket 'errors' -Message ("Competitor table is incomplete. Expected {0}, found {1}." -f $expectedCompetitorCount, $renderedCompetitorCount)
    }
    if ($expectedCompetitorCount -gt 0 -and $competitorFallbackCount -gt 0) {
        Add-Issue -Bucket 'errors' -Message ("Competitor logos fell back to initials. Fallback count: {0}." -f $competitorFallbackCount)
    }
    $generatedCompetitorLogoFallbacks = @()
    foreach ($row in @($data.competitive_landscape.table)) {
        $name = [string]$row.competitor
        $candidateValues = @([string]$row.logo_url, [string]$row.competitor_logo_url, [string]$row.badge_url, [string]$row.mark_url)
        foreach ($candidateValue in $candidateValues) {
            if (Test-GeneratedLogoFallbackPath -Value $candidateValue) {
                $generatedCompetitorLogoFallbacks += ("{0}: {1}" -f $name, $candidateValue)
                break
            }
        }
    }
    $script:audit.checks.generated_competitor_logo_fallbacks = @($generatedCompetitorLogoFallbacks).Count
    if ($generatedCompetitorLogoFallbacks.Count -gt 0) {
        Add-Issue -Bucket 'errors' -Message ("Competitor logos use generated PPTX text-card fallbacks instead of acquired logo assets: {0}" -f ($generatedCompetitorLogoFallbacks -join '; '))
    }

    $expectedNewsCount = Get-ItemCount -Value $data.brand_reputation.influential_news
    $publisherFallbackCount = [regex]::Matches($html, '<div class="publisher-badge">\s*<span>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    $genericNewsBadgeCount = [regex]::Matches($html, '(?i)src="(?:[^"]*/)?news\.png"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    $script:audit.checks.expected_news_items = $expectedNewsCount
    $script:audit.checks.publisher_logo_fallbacks = $publisherFallbackCount
    $script:audit.checks.generic_news_badges = $genericNewsBadgeCount
    if ($expectedNewsCount -gt 0 -and $publisherFallbackCount -gt 0) {
        Add-Issue -Bucket 'errors' -Message ("News source logos fell back to text. Fallback count: {0}." -f $publisherFallbackCount)
    }
    if ($expectedNewsCount -gt 0 -and $genericNewsBadgeCount -gt 0) {
        Add-Issue -Bucket 'errors' -Message ("News source logos include the generic news.png badge. Count: {0}." -f $genericNewsBadgeCount)
    }

    $brandDomain = Get-DomainStem -Value ([string]$data.brand.website)
    foreach ($newsItem in @($data.brand_reputation.influential_news)) {
        if ($null -eq $newsItem) {
            continue
        }
        $sourceName = [string]$newsItem.source
        $sourceType = [string]$newsItem.source_type
        $sourceDomain = Get-DomainStem -Value ([string]$newsItem.url)
        $ownedSource = $false
        if ($sourceType -match '^(?i)owned_newsroom$') {
            $ownedSource = $true
        }
        elseif (-not [string]::IsNullOrWhiteSpace($sourceName)) {
            $lowerSourceName = $sourceName.ToLowerInvariant()
            $brandName = ([string]$data.brand.name).ToLowerInvariant()
            if (($brandName -and $lowerSourceName.Contains($brandName)) -or $lowerSourceName.Contains('blog') -or $lowerSourceName.Contains('press') -or $lowerSourceName.Contains('newsroom')) {
                $ownedSource = $true
            }
        }
        if (-not $ownedSource -and $brandDomain -and $sourceDomain -and $sourceDomain -eq $brandDomain) {
            Add-Issue -Bucket 'errors' -Message ("Influential news source '{0}' points to the brand-owned domain instead of the named publisher." -f $sourceName)
        }
        $sourceAsset = [string]($newsItem.source_logo_url)
        if (-not $ownedSource -and $sourceAsset -match '(?i)source-initial-mark') {
            Add-Issue -Bucket 'errors' -Message ("Influential news source '{0}' fell back to a generic initial-mark badge instead of a recognisable publisher asset." -f $sourceName)
        }
        if (-not $ownedSource -and -not [string]::IsNullOrWhiteSpace($sourceAsset) -and $sourceAsset.EndsWith('.svg', [System.StringComparison]::OrdinalIgnoreCase)) {
            try {
                $assetPath = Join-Path (Split-Path -Parent $resolvedDataPath) $sourceAsset
                if (Test-Path -LiteralPath $assetPath) {
                    $svgText = (Get-Content -LiteralPath $assetPath -Raw).ToLowerInvariant()
                    $brandName = ([string]$data.brand.name).ToLowerInvariant()
                    if ($brandName -and $svgText.Contains($brandName)) {
                        Add-Issue -Bucket 'errors' -Message ("Influential news source '{0}' is using an SVG badge that still identifies as the brand asset." -f $sourceName)
                    }
                }
            }
            catch {
            }
        }
    }

    $brandLogoUrl = $data.brand.logo_url
    $brandMarkUrl = $data.brand.mark_url
    $hasBrandFallback = $html -match 'class="[^"]*\bbrand-logo-slot--fallback\b'
    $usesBrandLogoImage = $html -match '<div class="brand-logo-slot">\s*<img\b'
    $script:audit.checks.brand_logo_fallback = $hasBrandFallback
    if ($hasBrandFallback -or -not $usesBrandLogoImage) {
        Add-Issue -Bucket 'errors' -Message 'Brand logo fell back to initials or is absent from the report header.'
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$brandMarkUrl) -and $html -notmatch [regex]::Escape([string]$brandMarkUrl)) {
        Add-Issue -Bucket 'errors' -Message 'Rendered report header did not use the available brand mark asset.'
    }
    $brandMarkResolutionSource = [string]$data.brand.mark_resolution_source
    if ($brandMarkResolutionSource -match '(?i)no square logo candidate passed quality check') {
        Add-Issue -Bucket 'errors' -Message 'Brand mark resolution fell back without finding a proper square mark asset.'
    }
    if (
        -not [string]::IsNullOrWhiteSpace([string]$brandMarkUrl) -and
        -not [string]::IsNullOrWhiteSpace([string]$brandLogoUrl) -and
        ([string]$brandMarkUrl -eq [string]$brandLogoUrl) -and
        ([string]$brandMarkUrl -notmatch '(?i)(mark|favicon|initial)')
    ) {
        Add-Issue -Bucket 'errors' -Message 'Brand mark is reusing the main wordmark asset instead of a distinct square mark.'
    }

    $placeholderPatterns = @(
        'source pending',
        'should be confirmed',
        'record whether',
        'record known funding',
        'must be drawn from',
        'identify likely stakeholder groups',
        'treated in this report as a brand'
    )
    foreach ($pattern in $placeholderPatterns) {
        if ($html -match [regex]::Escape($pattern)) {
            Add-Issue -Bucket 'errors' -Message ("Rendered HTML still contains placeholder snapshot language: {0}" -f $pattern)
        }
    }

    if ($html -match '<span class="eyebrow">Built from report findings</span></div></div>') {
        Add-Issue -Bucket 'errors' -Message 'Opportunities section rendered an empty Built from report findings panel.'
    }
}

$ok = $script:audit.errors.Count -eq 0
[pscustomobject]@{
    ok = $ok
    html = $resolvedHtmlPath
    data = $resolvedDataPath
    checks = $script:audit.checks
    warnings = @($script:audit.warnings)
    errors = @($script:audit.errors)
} | ConvertTo-Json -Depth 8 -Compress

if (-not $ok) {
    exit 1
}
