param(
    [Parameter(Mandatory = $true)]
    [string]$BrandName,

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

$brandSlug = Get-BrandSlug -Name $BrandName
$brandPath = Join-Path $RootPath $brandSlug

if (-not (Test-Path -LiteralPath $brandPath)) {
    New-Item -ItemType Directory -Path $brandPath | Out-Null
}

$templatePath = Join-Path (Join-Path $PSScriptRoot '..\..\templates') 'report-data.template.json'
$brandDataPath = Join-Path $brandPath 'report-data.json'
$templateAssetPath = Join-Path (Join-Path $PSScriptRoot '..\..\templates') 'slide-assets'
$brandAssetPath = Join-Path $brandPath 'slide-assets'

if ((Test-Path -LiteralPath $templatePath) -and (-not (Test-Path -LiteralPath $brandDataPath))) {
    $template = Get-Content -LiteralPath $templatePath -Raw | ConvertFrom-Json
    $template.brand.name = $BrandName
    $template.brand.slug = $brandSlug
    $template.brand.website = 'https://example.com/'
    $template.cover.assumptions[0] = "Assumption: the primary site is https://example.com/ until confirmed otherwise."
    $template | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $brandDataPath -Encoding UTF8
}

if ((Test-Path -LiteralPath $templateAssetPath) -and (-not (Test-Path -LiteralPath $brandAssetPath))) {
    Copy-Item -LiteralPath $templateAssetPath -Destination $brandAssetPath -Recurse -Force
}

$result = [pscustomobject]@{
    brand_name = $BrandName
    brand_slug = $brandSlug
    brand_path = $brandPath
    report_data_path = $brandDataPath
}

$result | ConvertTo-Json -Compress
