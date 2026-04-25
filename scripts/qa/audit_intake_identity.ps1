param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
$errors = New-Object System.Collections.Generic.List[string]

$brandName = [string]$data.brand.name
$website = [string]$data.brand.website

if ([string]::IsNullOrWhiteSpace($brandName)) {
    $errors.Add('brand.name is missing.')
}
if ([string]::IsNullOrWhiteSpace($website)) {
    $errors.Add('brand.website is missing.')
}
elseif ($website -match '^https?://example\.com/?$') {
    $errors.Add('brand.website still points to example.com.')
}
else {
    try {
        $uri = [System.Uri]::new($website)
        if ([string]::IsNullOrWhiteSpace($uri.Host)) {
            $errors.Add('brand.website is missing a host.')
        }
    }
    catch {
        $errors.Add("brand.website is not a valid URL: $website")
    }
}

if ($errors.Count -gt 0) {
    throw ("Intake identity audit failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    brand_name = $brandName
    website = $website
} | ConvertTo-Json -Depth 4 -Compress
