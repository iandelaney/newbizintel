param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

function Test-HasValue {
    param([object]$Value)
    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return -not [string]::IsNullOrWhiteSpace($Value) }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($item in $Value) { return $true }
        return $false
    }
    return $true
}

function ConvertTo-Slug {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    $slug = $Value.ToLowerInvariant() -replace '^https?://', ''
    $slug = $slug -replace '^www\.', ''
    $slug = $slug -replace '[^a-z0-9]+', '-'
    return $slug.Trim('-')
}

function Resolve-AssetCandidate {
    param(
        [string]$BrandFolder,
        [string]$AssetDirectory,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    if ([System.IO.Path]::IsPathRooted($Value)) { return $Value }

    foreach ($candidate in @(
        (Join-Path $BrandFolder $Value),
        (Join-Path $AssetDirectory $Value)
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }

    return ''
}

function Test-NewsLogoResolvable {
    param(
        [object]$Item,
        [string]$BrandFolder,
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
        $resolved = Resolve-AssetCandidate -BrandFolder $BrandFolder -AssetDirectory $AssetDirectory -Value $explicitLogo
        if (-not [string]::IsNullOrWhiteSpace($resolved)) { return $true }
    }

    $source = [string]$Item.source
    if (
        -not [string]::IsNullOrWhiteSpace($source) -and
        -not [string]::IsNullOrWhiteSpace($BrandName) -and
        $source.Trim().ToLowerInvariant() -eq $BrandName.Trim().ToLowerInvariant()
    ) {
        if ((-not [string]::IsNullOrWhiteSpace($BrandMarkPath)) -and (Test-Path -LiteralPath $BrandMarkPath)) { return $true }
        if ((-not [string]::IsNullOrWhiteSpace($BrandLogoPath)) -and (Test-Path -LiteralPath $BrandLogoPath)) { return $true }
    }

    $namesToTry = New-Object System.Collections.Generic.List[string]
    $sourceSlug = ConvertTo-Slug $source
    if (-not [string]::IsNullOrWhiteSpace($sourceSlug)) {
        foreach ($name in @("$sourceSlug-news.png", "$sourceSlug-favicon.png", "$sourceSlug-logo.png", "$sourceSlug.png")) {
            $namesToTry.Add($name)
        }
    }

    $url = [string]$Item.url
    if (-not [string]::IsNullOrWhiteSpace($url)) {
        try {
            $uri = [System.Uri]$url
            $hostSlug = ConvertTo-Slug $uri.Host
            if (-not [string]::IsNullOrWhiteSpace($hostSlug)) {
                foreach ($name in @("$hostSlug-news.png", "$hostSlug-favicon.png", "$hostSlug-logo.png", "$hostSlug.png")) {
                    $namesToTry.Add($name)
                }
            }
        }
        catch {
        }
    }

    foreach ($name in $namesToTry) {
        if (Test-Path -LiteralPath (Join-Path $AssetDirectory $name)) { return $true }
    }

    return $false
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$brandFolder = Split-Path -Parent $resolvedDataPath
$assetDirectory = Join-Path $brandFolder 'slide-assets'
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

$brandName = [string]$data.brand.name
$brandLogoPath = Resolve-AssetCandidate -BrandFolder $brandFolder -AssetDirectory $assetDirectory -Value ([string]$data.brand.logo_url)
$brandMarkPath = Resolve-AssetCandidate -BrandFolder $brandFolder -AssetDirectory $assetDirectory -Value ([string]$data.brand.mark_url)

$news = @($data.brand_reputation.influential_news)
for ($i = 0; $i -lt $news.Count; $i++) {
    $item = $news[$i]
    if (-not (Test-NewsLogoResolvable -Item $item -BrandFolder $brandFolder -AssetDirectory $assetDirectory -BrandName $brandName -BrandLogoPath $brandLogoPath -BrandMarkPath $brandMarkPath)) {
        $errors.Add("brand_reputation.influential_news[$i] must resolve to a real publisher badge asset for HTML and PPTX delivery.")
    }
}

if ($errors.Count -gt 0) {
    throw ("Delivery asset validation failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    validation = 'delivery-assets'
    checked_news_items = $news.Count
    warnings = @($warnings)
} | ConvertTo-Json -Depth 5 -Compress
