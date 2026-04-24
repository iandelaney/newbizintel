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

    $brandLogoUrl = $data.brand.logo_url
    $brandMarkUrl = $data.brand.mark_url
    $hasBrandFallback = $html -match 'class="[^"]*\bbrand-logo-slot--fallback\b'
    $usesBrandLogoImage = $html -match '<div class="brand-logo-slot">\s*<img\b'
    $script:audit.checks.brand_logo_fallback = $hasBrandFallback
    if ($hasBrandFallback -or -not $usesBrandLogoImage) {
        Add-Issue -Bucket 'errors' -Message 'Brand logo fell back to initials or is absent from the report header.'
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
