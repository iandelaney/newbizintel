param(
    [Parameter(Mandatory = $true)]
    [string]$BrandFolder,

    [string[]]$SearchWorkpacks = @(),

    [string[]]$ResearchWorkpacks = @(),

    [int]$MinimumSearchWorkpacks = 2,

    [int]$MinimumSearchResults = 8,

    [switch]$AllowResearchEscalation
)

$ErrorActionPreference = 'Stop'

$resolvedBrandFolder = (Resolve-Path -LiteralPath $BrandFolder).Path
$validate = Join-Path $PSScriptRoot 'validate_tavily_workpack.ps1'
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$searchValidations = @()
$researchValidations = @()

foreach ($path in @($SearchWorkpacks)) {
    $resolved = if ([System.IO.Path]::IsPathRooted($path)) { $path } else { Join-Path $resolvedBrandFolder $path }
    $result = & $validate -Path $resolved -Kind search | ConvertFrom-Json
    $searchValidations += $result
    if ($result.ok -ne $true) {
        $errors.Add("Search workpack failed validation: $resolved")
    }
}

foreach ($path in @($ResearchWorkpacks)) {
    $resolved = if ([System.IO.Path]::IsPathRooted($path)) { $path } else { Join-Path $resolvedBrandFolder $path }
    $result = & $validate -Path $resolved -Kind research | ConvertFrom-Json
    $researchValidations += $result
    if ($result.ok -ne $true) {
        $errors.Add("Research workpack failed validation: $resolved")
    }
}

$totalSearchResults = 0
foreach ($validation in $searchValidations) {
    $totalSearchResults += [int]$validation.result_count
}

$searchCoverageOk = ($searchValidations.Count -ge $MinimumSearchWorkpacks -and $totalSearchResults -ge $MinimumSearchResults)
if (-not $searchCoverageOk) {
    $warnings.Add("Cheap search coverage is below target: workpacks=$($searchValidations.Count)/$MinimumSearchWorkpacks results=$totalSearchResults/$MinimumSearchResults.")
}

if ($researchValidations.Count -gt 0 -and -not $AllowResearchEscalation) {
    $errors.Add('Tavily Research workpacks are present but research escalation was not allowed for this audit.')
}

[pscustomobject]@{
    ok = ($errors.Count -eq 0)
    brand_folder = $resolvedBrandFolder
    cheap_search_sufficient = $searchCoverageOk
    search_workpack_count = $searchValidations.Count
    search_result_count = $totalSearchResults
    research_workpack_count = $researchValidations.Count
    allow_research_escalation = [bool]$AllowResearchEscalation
    recommendation = $(if ($searchCoverageOk) { 'Do not use Tavily Research by default; cheap search coverage is sufficient.' } else { 'Escalate only if Jina/direct-source fallbacks cannot close the coverage gap.' })
    errors = @($errors)
    warnings = @($warnings)
} | ConvertTo-Json -Depth 8 -Compress
