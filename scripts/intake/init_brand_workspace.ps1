param(
    [Parameter(Mandatory = $true)]
    [string]$BrandName,

    [string]$Website,

    [string]$RootPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

function Get-BrandSlug {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $slug = $Name.ToLowerInvariant()
    $slug = $slug -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')

    if ([string]::IsNullOrWhiteSpace($slug)) {
        throw "Brand name '$Name' does not contain usable letters or digits."
    }

    return $slug
}

function Get-NormalizedWebsite {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    $website = $Value.Trim()
    if ($website -notmatch '^https?://') {
        $website = "https://$website"
    }

    try {
        $uri = [System.Uri]::new($website)
        $builder = [System.UriBuilder]::new($uri)
        if ([string]::IsNullOrWhiteSpace($builder.Host)) {
            throw "Website is missing a host."
        }
        return $builder.Uri.AbsoluteUri
    }
    catch {
        throw "Website '$Value' is not a valid URL or domain."
    }
}

$brandSlug = Get-BrandSlug -Name $BrandName
$brandPath = Join-Path $RootPath $brandSlug
$normalizedWebsite = Get-NormalizedWebsite -Value $Website

if (-not (Test-Path -LiteralPath $brandPath)) {
    New-Item -ItemType Directory -Path $brandPath | Out-Null
}

$templatePath = Join-Path (Join-Path $PSScriptRoot '..\..\templates') 'report-data.template.json'
$brandDataPath = Join-Path $brandPath 'report-data.json'
$templateAssetPath = Join-Path (Join-Path $PSScriptRoot '..\..\templates') 'slide-assets'
$brandAssetPath = Join-Path $brandPath 'slide-assets'

if ((Test-Path -LiteralPath $templatePath) -and (-not (Test-Path -LiteralPath $brandDataPath))) {
    if ([string]::IsNullOrWhiteSpace($normalizedWebsite)) {
    throw 'A real -Website is required when creating a new NewBizIntel brand workspace.'
    }

    $template = Get-Content -LiteralPath $templatePath -Raw | ConvertFrom-Json
    $template.brand.name = $BrandName
    $template.brand.slug = $brandSlug
    $template.brand.website = $normalizedWebsite
    $template.cover.assumptions[0] = "Confirmed primary site: $normalizedWebsite."
    $template | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $brandDataPath -Encoding UTF8
}
elseif ((Test-Path -LiteralPath $brandDataPath) -and -not [string]::IsNullOrWhiteSpace($normalizedWebsite)) {
    $existing = Get-Content -LiteralPath $brandDataPath -Raw | ConvertFrom-Json
    $existing.brand.name = $BrandName
    $existing.brand.slug = $brandSlug
    $existing.brand.website = $normalizedWebsite
    if ($existing.cover -and $existing.cover.assumptions -and @($existing.cover.assumptions).Count -gt 0) {
        $existing.cover.assumptions[0] = "Confirmed primary site: $normalizedWebsite."
    }
    $existing | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $brandDataPath -Encoding UTF8
}

if ((Test-Path -LiteralPath $templateAssetPath) -and (-not (Test-Path -LiteralPath $brandAssetPath))) {
    Copy-Item -LiteralPath $templateAssetPath -Destination $brandAssetPath -Recurse -Force
}

$result = [pscustomobject]@{
    brand_name = $BrandName
    brand_slug = $brandSlug
    website = $normalizedWebsite
    brand_path = $brandPath
    report_data_path = $brandDataPath
}

$result | ConvertTo-Json -Compress
