param(
  [Parameter(Mandatory=$true)][string]$RunId,
  [Parameter(Mandatory=$true)][string]$AttemptId,
  [Parameter(Mandatory=$true)][string]$ResearchCutoff,
  [string]$Out,
  [string]$RuntimeOut
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
if (-not $Out) { $Out = Join-Path $Root "research\runs\$AttemptId.bootstrap.json" }
elseif (-not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path $Root $Out }
if (-not $RuntimeOut) { $RuntimeOut = Join-Path $Root "research\runs\$AttemptId.python-runtime.json" }
elseif (-not [System.IO.Path]::IsPathRooted($RuntimeOut)) { $RuntimeOut = Join-Path $Root $RuntimeOut }

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Add-Check([System.Collections.ArrayList]$Checks, [string]$Name, [string]$Status, $Detail=$null) {
  $entry = [ordered]@{ check = $Name; status = $Status }
  if ($null -ne $Detail) { $entry.detail = $Detail }
  [void]$Checks.Add([pscustomobject]$entry)
}

$checks = New-Object System.Collections.ArrayList
$errors = New-Object System.Collections.ArrayList
$warnings = New-Object System.Collections.ArrayList

$required = @(
  'config\daily-capabilities.json',
  'config\daily-model.json',
  'config\massive-request-policy.json',
  'config\python-runtime-policy.json',
  'scripts\control_plane\massive_request_gate.py',
  'scripts\control_plane\materialize_mcp_dataset.py',
  'scripts\control_plane\evaluate_capabilities.py',
  'scripts\control_plane\validate_artifact.py',
  'scripts\pipeline\run_daily_pipeline.py',
  'scripts\control_plane\seal_acquisition.py',
  'scripts\control_plane\freeze_forecast.py'
)
foreach ($rel in $required) {
  $exists = Test-Path -LiteralPath (Join-Path $Root $rel) -PathType Leaf
  Add-Check $checks "required_file:$($rel.Replace('\','/'))" $(if ($exists) {'PASS'} else {'FAIL'})
  if (-not $exists) { [void]$errors.Add("missing:$($rel.Replace('\','/'))") }
}

foreach ($rel in @('research\acquisitions','research\data','research\pipeline','research\runs','research\forecasts')) {
  $path = Join-Path $Root $rel
  try {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    $probe = Join-Path $path ('.bootstrap-write-' + [guid]::NewGuid().ToString('N'))
    Write-Utf8NoBom $probe 'ok'
    Remove-Item -Force -LiteralPath $probe
    Add-Check $checks "writable:$($rel.Replace('\','/'))" 'PASS'
  } catch {
    Add-Check $checks "writable:$($rel.Replace('\','/'))" 'FAIL' $_.Exception.Message
    [void]$errors.Add("not_writable:$($rel.Replace('\','/'))")
  }
}

try {
  $policy = Get-Content -Raw -LiteralPath (Join-Path $Root 'config\massive-request-policy.json') | ConvertFrom-Json
  $max = [int]$policy.max_requests_per_window
  $window = [double]$policy.window_seconds
  $interval = [double]$policy.minimum_interval_seconds
  if ($max -lt 1 -or $window -le 0 -or ($interval + 1e-9) -lt ($window / $max)) { throw 'unsafe pacing values' }
  Add-Check $checks 'massive_request_policy' 'PASS' "$max call_api requests/$window s; minimum interval $interval s"
} catch {
  Add-Check $checks 'massive_request_policy' 'FAIL' $_.Exception.Message
  [void]$errors.Add('massive_request_policy_invalid')
}

$prior = @(Get-ChildItem -Path (Join-Path $Root 'research\runs') -Filter '*.json' -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*$RunId*" })
if ($prior.Count -gt 0) {
  Add-Check $checks 'prior_run_discovery' 'WARN' $prior.Count
  [void]$warnings.Add("prior_run_artifacts:$($prior.Count):create_new_attempt_do_not_overwrite")
} else {
  Add-Check $checks 'prior_run_discovery' 'PASS' 0
}

$version = $null
$manifestDigest = $null
try {
  $version = (Get-Content -Raw -LiteralPath (Join-Path $Root 'VERSION')).Trim()
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.IO.File]::ReadAllBytes((Join-Path $Root 'CONTROL_PLANE_MANIFEST.json'))
    $hash = $sha.ComputeHash($bytes)
    $manifestDigest = 'sha256:' + ([BitConverter]::ToString($hash).Replace('-','').ToLowerInvariant())
  } finally { $sha.Dispose() }
  Add-Check $checks 'source_identity' 'PASS' "$version $manifestDigest"
} catch {
  Add-Check $checks 'source_identity' 'WARN' $_.Exception.Message
  [void]$warnings.Add('source_identity_incomplete')
}

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git -and (Test-Path -LiteralPath (Join-Path $Root '.git'))) {
  try {
    $head = (& $git.Source -C $Root rev-parse HEAD 2>$null | Select-Object -First 1).Trim()
    Add-Check $checks 'git_checkout' 'PASS' $head
  } catch {
    Add-Check $checks 'git_checkout' 'WARN' 'git head unavailable'
    [void]$warnings.Add('git_head_unavailable')
  }
} else {
  Add-Check $checks 'git_checkout' 'WARN' 'not a Git checkout; source identity fallback recorded'
  [void]$warnings.Add('git_checkout_unavailable')
}

$runtimeProbe = Join-Path $ScriptDir 'run_python.ps1'
$runtimeStatus = $null
try {
  & $runtimeProbe -ProbeOnly -RuntimeOut $RuntimeOut -AllowProvision *> $null
  if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $RuntimeOut)) {
    $runtimeStatus = Get-Content -Raw -LiteralPath $RuntimeOut | ConvertFrom-Json
    Add-Check $checks 'python_runtime' 'PASS' "$($runtimeStatus.version) via $($runtimeStatus.source): $($runtimeStatus.resolved_executable)"
  } else {
    throw "runtime probe exit $LASTEXITCODE; inspect $RuntimeOut for candidate/provisioning diagnostics"
  }
} catch {
  Add-Check $checks 'python_runtime' 'FAIL' $_.Exception.Message
  [void]$errors.Add('python_runtime_unavailable')
}

[void]$warnings.Add('massive_effective_access_probe_required:bootstrap cannot prove MCP entitlement')
$status = if ($errors.Count -gt 0) { 'BLOCKED' } else { 'READY' }
$result = [ordered]@{
  run_id = $RunId
  attempt_id = $AttemptId
  created_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  research_cutoff = $ResearchCutoff
  status = $status
  checks = @($checks)
  errors = @($errors)
  warnings = @($warnings)
  python_runtime_file = $RuntimeOut
  source_version = $version
  control_plane_manifest_digest = $manifestDigest
}
$json = $result | ConvertTo-Json -Depth 10
Write-Utf8NoBom $Out ($json + "`n")
Write-Output $json
exit $(if ($status -eq 'READY') { 0 } else { 2 })
