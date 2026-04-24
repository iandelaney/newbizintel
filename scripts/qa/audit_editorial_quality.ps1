param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

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

function Add-Missing {
    param([string]$PathLabel)
    $errors.Add("Missing or empty editorial field: $PathLabel")
}

function Add-EditorialIssue {
    param([string]$Message)

    if ($isTemplateFixture) {
        $warnings.Add($Message)
    }
    else {
        $errors.Add($Message)
    }
}

function Get-ObjectProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($property) {
        return $property.Value
    }

    return $null
}

function Find-TextFindings {
    param(
        [object]$Value,
        [string]$PathLabel = '$'
    )

    if ($null -eq $Value) {
        return
    }

    if ($Value -is [string]) {
        foreach ($pattern in $placeholderPatterns) {
            if ($Value -match $pattern.regex) {
                $placeholderFindings.Add([pscustomobject]@{
                    path = $PathLabel
                    label = $pattern.label
                    sample = $(if ($Value.Length -gt 120) { $Value.Substring(0, 120) } else { $Value })
                })
                break
            }
        }
        return
    }

    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) {
            Find-TextFindings -Value $Value[$key] -PathLabel "$PathLabel.$key"
        }
        return
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $index = 0
        foreach ($item in $Value) {
            Find-TextFindings -Value $item -PathLabel "$PathLabel[$index]"
            $index++
        }
        return
    }

    foreach ($property in @($Value.PSObject.Properties | Where-Object { $_.MemberType -eq 'NoteProperty' })) {
        Find-TextFindings -Value $property.Value -PathLabel "$PathLabel.$($property.Name)"
    }
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$placeholderFindings = New-Object System.Collections.Generic.List[object]

$placeholderPatterns = @(
    @{ label = 'replace-with'; regex = '(?i)\breplace with\b' },
    @{ label = 'todo'; regex = '(?i)\bTODO\b|\bTBD\b' },
    @{ label = 'lorem'; regex = '(?i)lorem ipsum' },
    @{ label = 'add-verified'; regex = '(?i)\badd verified\b' },
    @{ label = 'assumption-placeholder'; regex = '(?i)assumption goes here|state any .* assumptions here|state whether .* here' }
)

$isTemplateFixture = (
    [string]$data.brand.name -eq 'Example Brand' -or
    [string]$data.brand.website -eq 'https://example.com/'
)

Find-TextFindings -Value $data
if ($placeholderFindings.Count -gt 0) {
    if ($isTemplateFixture) {
        $warnings.Add("Template fixture contains $($placeholderFindings.Count) placeholder strings; production brand runs must replace these before QA.")
    }
    else {
        foreach ($finding in $placeholderFindings) {
            $errors.Add("Placeholder copy remains at $($finding.path): $($finding.label)")
        }
    }
}

if (-not (Test-HasValue $data.executive_summary.cards)) { Add-Missing 'executive_summary.cards' }
elseif (@($data.executive_summary.cards).Count -lt 4) { Add-EditorialIssue 'executive_summary.cards should include at least 4 evidence-backed cards.' }

if (-not (Test-HasValue $data.agency_opportunity.score_summary)) { Add-Missing 'agency_opportunity.score_summary' }
if (-not (Test-HasValue $data.agency_opportunity.lead_offering.verdict)) { Add-Missing 'agency_opportunity.lead_offering.verdict' }

$campaignIdeas = @($data.creative_campaign_ideas.ideas)
if ($campaignIdeas.Count -lt 3) {
    Add-EditorialIssue "creative_campaign_ideas.ideas should include at least 3 campaign ideas. Current count: $($campaignIdeas.Count)"
}

for ($i = 0; $i -lt $campaignIdeas.Count; $i++) {
    $idea = $campaignIdeas[$i]
    foreach ($field in @('title', 'addresses', 'concept', 'activation', 'why_it_fits', 'why_it_will_work', 'intended_effect')) {
        if (-not (Test-HasValue (Get-ObjectProperty -Object $idea -Name $field))) {
            Add-EditorialIssue "Missing or empty editorial field: creative_campaign_ideas.ideas[$i].$field"
        }
    }

    $sequence = @()
    $sequenceShape = 'activation_sequence'
    if (Test-HasValue (Get-ObjectProperty -Object $idea -Name 'activation_sequence')) {
        $sequence = @($idea.activation_sequence)
    }
    elseif (Test-HasValue (Get-ObjectProperty -Object $idea -Name 'activation_plan')) {
        $plan = Get-ObjectProperty -Object $idea -Name 'activation_plan'
        if (Test-HasValue (Get-ObjectProperty -Object $plan -Name 'order_of_precedence')) {
            $sequence = @($plan.order_of_precedence)
            $sequenceShape = 'activation_plan.order_of_precedence'
        }
    }

    if ($sequence.Count -lt 3) {
        Add-EditorialIssue "creative_campaign_ideas.ideas[$i].$sequenceShape should include at least 3 ordered activation items."
    }
    for ($j = 0; $j -lt $sequence.Count; $j++) {
        $step = $sequence[$j]
        $fieldMap = if ($sequenceShape -eq 'activation_plan.order_of_precedence') {
            @(
                @{ actual = 'name'; label = 'name' },
                @{ actual = 'primary_goal'; label = 'primary_goal' },
                @{ actual = 'contains'; label = 'contains' },
                @{ actual = 'inputs_needed'; label = 'inputs_needed' }
            )
        }
        else {
            @(
                @{ actual = 'name'; label = 'name' },
                @{ actual = 'why_first'; label = 'why_first' },
                @{ actual = 'should_contain'; label = 'should_contain' },
                @{ actual = 'needs_as_input'; label = 'needs_as_input' }
            )
        }

        foreach ($field in $fieldMap) {
            if (-not (Test-HasValue (Get-ObjectProperty -Object $step -Name $field.actual))) {
                Add-EditorialIssue "Missing or empty editorial field: creative_campaign_ideas.ideas[$i].$sequenceShape[$j].$($field.label)"
            }
        }
    }
}

$semrushEvidence = @($data.seo_audit.semrush_evidence)
if ($semrushEvidence.Count -lt 2) {
    Add-EditorialIssue "seo_audit.semrush_evidence should include at least 2 evidence points before delivery. Current count: $($semrushEvidence.Count)"
}

$newsItems = @($data.brand_reputation.influential_news)
if ($newsItems.Count -lt 5 -and -not $isTemplateFixture) {
    $errors.Add("brand_reputation.influential_news should include at least 5 current stories before delivery. Current count: $($newsItems.Count)")
}

$result = [pscustomobject]@{
    ok = ($errors.Count -eq 0)
    data = $resolvedDataPath
    template_fixture = $isTemplateFixture
    errors = $errors.ToArray()
    warnings = $warnings.ToArray()
    placeholder_findings = $placeholderFindings.ToArray()
}

if ($errors.Count -gt 0) {
    throw ("Editorial QA failed: {0}" -f ($errors.ToArray() -join '; '))
}

$result | ConvertTo-Json -Depth 8 -Compress
