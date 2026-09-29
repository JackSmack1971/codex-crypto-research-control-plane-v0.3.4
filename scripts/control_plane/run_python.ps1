param(
  [Parameter(Position=0)]
  [string]$Script,

  [string]$RuntimeFile,

  [switch]$ProbeOnly,

  [string]$RuntimeOut,

  [switch]$AllowProvision,

  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]]$ScriptArgs
)

$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$PolicyPath = Join-Path $Root 'config\python-runtime-policy.json'
$Policy = Get-Content -Raw -LiteralPath $PolicyPath | ConvertFrom-Json
$MinVersion = [version]$Policy.minimum_version
$Diagnostics = New-Object System.Collections.ArrayList
$Provisioning = New-Object System.Collections.ArrayList

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Add-Diagnostic([string]$Source, [string]$Candidate, [string]$Status, [string]$Detail) {
  [void]$Diagnostics.Add([pscustomobject][ordered]@{
    source = $Source
    candidate = $Candidate
    status = $Status
    detail = $Detail
  })
}

function Test-PythonCandidate([string]$Executable, [string[]]$Prefix, [string]$Source) {
  if ([string]::IsNullOrWhiteSpace($Executable)) { return $null }
  try {
    $exists = Test-Path -LiteralPath $Executable -PathType Leaf
    if (-not $exists) {
      $cmd = Get-Command $Executable -ErrorAction SilentlyContinue
      if (-not $cmd) {
        Add-Diagnostic $Source $Executable 'NOT_FOUND' 'candidate not present'
        return $null
      }
    }
    $probe = 'import json,sys; ok=sys.version_info>=(3,11); print(json.dumps({"ok":ok,"version":sys.version.split()[0],"executable":sys.executable})); raise SystemExit(0 if ok else 2)'
    $output = @(& $Executable @Prefix -B -c $probe 2>&1)
    $exitCode = $LASTEXITCODE
    $text = (($output | ForEach-Object { [string]$_ }) -join "`n").Trim()
    if ($text.Length -gt 800) { $text = $text.Substring($text.Length - 800) }
    if ($exitCode -ne 0 -or $output.Count -eq 0) {
      Add-Diagnostic $Source $Executable 'FAILED' "exit=$exitCode $text"
      return $null
    }
    $jsonLine = $output | ForEach-Object { [string]$_ } | Where-Object { $_.TrimStart().StartsWith('{') } | Select-Object -Last 1
    if (-not $jsonLine) {
      Add-Diagnostic $Source $Executable 'FAILED' 'probe returned no JSON metadata'
      return $null
    }
    $info = $jsonLine | ConvertFrom-Json
    if (-not $info.ok) {
      Add-Diagnostic $Source $Executable 'TOO_OLD' "version=$($info.version) minimum=$MinVersion"
      return $null
    }
    $resolved = [string]$info.executable
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
      Add-Diagnostic $Source $Executable 'FAILED' "resolved executable missing: $resolved"
      return $null
    }
    Add-Diagnostic $Source $Executable 'READY' "version=$($info.version) resolved=$resolved"
    return [pscustomobject]@{
      mode = 'native'
      source = $Source
      executable = $resolved
      prefix = @()
      resolved_executable = $resolved
      version = [string]$info.version
    }
  } catch {
    Add-Diagnostic $Source $Executable 'FAILED' $_.Exception.Message
    return $null
  }
}

function Get-UniqueExistingPythonFiles([string[]]$Paths) {
  $seen = @{}
  foreach ($path in $Paths) {
    if ([string]::IsNullOrWhiteSpace($path)) { continue }
    try { $full = [System.IO.Path]::GetFullPath($path) } catch { $full = $path }
    if (-not $seen.ContainsKey($full)) {
      $seen[$full] = $true
      if (Test-Path -LiteralPath $full -PathType Leaf) { $full }
    }
  }
}

function Get-RepoVenvCandidates {
  $paths = @(
    (Join-Path $Root '.venv\Scripts\python.exe'),
    (Join-Path $Root 'venv\Scripts\python.exe')
  )
  Get-UniqueExistingPythonFiles $paths
}

function Get-RegistryPythonCandidates {
  $roots = @(
    'Registry::HKEY_CURRENT_USER\Software\Python\PythonCore',
    'Registry::HKEY_LOCAL_MACHINE\Software\Python\PythonCore',
    'Registry::HKEY_LOCAL_MACHINE\Software\WOW6432Node\Python\PythonCore'
  )
  $paths = New-Object System.Collections.ArrayList
  foreach ($base in $roots) {
    if (-not (Test-Path $base)) { continue }
    foreach ($versionKey in @(Get-ChildItem $base -ErrorAction SilentlyContinue)) {
      $installKey = Join-Path $versionKey.PSPath 'InstallPath'
      if (-not (Test-Path $installKey)) { continue }
      try {
        $item = Get-Item -LiteralPath $installKey
        $install = [string]$item.GetValue('')
        $exe = [string]$item.GetValue('ExecutablePath')
        if ($exe) { [void]$paths.Add($exe) }
        if ($install) { [void]$paths.Add((Join-Path $install 'python.exe')) }
      } catch { }
    }
  }
  Get-UniqueExistingPythonFiles @($paths)
}

function Get-CommonPythonCandidates {
  $patterns = New-Object System.Collections.ArrayList
  if ($env:LOCALAPPDATA) { [void]$patterns.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python*\python.exe')) }
  if ($env:ProgramFiles) { [void]$patterns.Add((Join-Path $env:ProgramFiles 'Python*\python.exe')) }
  if (${env:ProgramFiles(x86)}) { [void]$patterns.Add((Join-Path ${env:ProgramFiles(x86)} 'Python*\python.exe')) }
  if ($env:USERPROFILE) {
    [void]$patterns.Add((Join-Path $env:USERPROFILE 'scoop\apps\python\current\python.exe'))
    [void]$patterns.Add((Join-Path $env:USERPROFILE 'miniconda3\python.exe'))
    [void]$patterns.Add((Join-Path $env:USERPROFILE 'anaconda3\python.exe'))
  }
  $paths = New-Object System.Collections.ArrayList
  foreach ($pattern in $patterns) {
    Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { [void]$paths.Add($_.FullName) }
  }
  Get-UniqueExistingPythonFiles @($paths)
}

function Get-PathPythonCandidates {
  $paths = New-Object System.Collections.ArrayList
  foreach ($name in @('python.exe','python3.exe','python','python3')) {
    try {
      Get-Command $name -All -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Source) { [void]$paths.Add([string]$_.Source) }
      }
    } catch { }
    try {
      @(& where.exe $name 2>$null) | ForEach-Object {
        if ($_ -and (Test-Path -LiteralPath ([string]$_).Trim() -PathType Leaf)) { [void]$paths.Add(([string]$_).Trim()) }
      }
    } catch { }
  }
  Get-UniqueExistingPythonFiles @($paths)
}

function Get-UvManagedCandidates {
  $dirs = New-Object System.Collections.ArrayList
  $repoRuntime = Join-Path $Root ([string]$Policy.repo_runtime_dir)
  if (Test-Path -LiteralPath $repoRuntime -PathType Container) { [void]$dirs.Add($repoRuntime) }
  if ($env:APPDATA) {
    $defaultUv = Join-Path $env:APPDATA 'uv\data\python'
    if (Test-Path -LiteralPath $defaultUv -PathType Container) { [void]$dirs.Add($defaultUv) }
  }
  $uv = Get-Command 'uv' -ErrorAction SilentlyContinue
  if ($uv) {
    try {
      $uvDir = (& $uv.Source python dir --no-config 2>$null | Select-Object -First 1)
      if ($LASTEXITCODE -eq 0 -and $uvDir) {
        $uvDir = ([string]$uvDir).Trim()
        if (Test-Path -LiteralPath $uvDir -PathType Container) { [void]$dirs.Add($uvDir) }
      }
    } catch { }
  }
  $paths = New-Object System.Collections.ArrayList
  foreach ($dir in @($dirs | Select-Object -Unique)) {
    Get-ChildItem -LiteralPath $dir -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { [void]$paths.Add($_.FullName) }
  }
  Get-UniqueExistingPythonFiles @($paths)
}

function Find-ExistingPython {
  if ($RuntimeFile -and (Test-Path -LiteralPath $RuntimeFile)) {
    try {
      $saved = Get-Content -Raw -LiteralPath $RuntimeFile | ConvertFrom-Json
      if ($saved.status -eq 'READY' -and $saved.resolved_executable) {
        $candidate = Test-PythonCandidate -Executable ([string]$saved.resolved_executable) -Prefix @() -Source 'runtime_file'
        if ($candidate) { return $candidate }
      }
    } catch { Add-Diagnostic 'runtime_file' $RuntimeFile 'FAILED' $_.Exception.Message }
  }

  if ($Policy.allow_repo_venv) {
    foreach ($path in @(Get-RepoVenvCandidates)) {
      $candidate = Test-PythonCandidate $path @() 'repo_venv'
      if ($candidate) { return $candidate }
    }
  }

  if ($Policy.allow_py_launcher) {
    foreach ($prefix in @(@('-3.13'), @('-3.12'), @('-3.11'), @('-3'))) {
      $candidate = Test-PythonCandidate 'py' $prefix 'py_launcher'
      if ($candidate) { return $candidate }
    }
  }

  if ($Policy.allow_windows_registry_scan) {
    foreach ($path in @(Get-RegistryPythonCandidates)) {
      $candidate = Test-PythonCandidate $path @() 'windows_registry'
      if ($candidate) { return $candidate }
    }
  }

  if ($Policy.allow_common_install_scan) {
    foreach ($path in @(Get-CommonPythonCandidates)) {
      $candidate = Test-PythonCandidate $path @() 'common_install_scan'
      if ($candidate) { return $candidate }
    }
  }

  if ($Policy.allow_uv_managed_scan) {
    foreach ($path in @(Get-UvManagedCandidates)) {
      $candidate = Test-PythonCandidate $path @() 'uv_managed_scan'
      if ($candidate) { return $candidate }
    }
  }

  if ($Policy.allow_path_python) {
    foreach ($path in @(Get-PathPythonCandidates)) {
      $candidate = Test-PythonCandidate $path @() 'path_enumeration'
      if ($candidate) { return $candidate }
    }
  }

  if ($Policy.allow_uv_locator) {
    $uv = Get-Command 'uv' -ErrorAction SilentlyContinue
    if ($uv) {
      try {
        $located = (& $uv.Source python find ">=$($Policy.minimum_version)" --no-config --no-python-downloads 2>&1 | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $located) {
          $candidate = Test-PythonCandidate ([string]$located).Trim() @() 'uv_python_find'
          if ($candidate) { return $candidate }
        } else {
          Add-Diagnostic 'uv_python_find' $uv.Source 'FAILED' (([string]$located).Trim())
        }
      } catch { Add-Diagnostic 'uv_python_find' $uv.Source 'FAILED' $_.Exception.Message }
    } else {
      Add-Diagnostic 'uv_python_find' 'uv' 'NOT_FOUND' 'uv executable unavailable'
    }
  }
  return $null
}

function Install-RepoLocalPython {
  if (-not $Policy.allow_repo_local_uv_provision) { return $false }
  $uv = Get-Command 'uv' -ErrorAction SilentlyContinue
  if (-not $uv) {
    [void]$Provisioning.Add([pscustomobject]@{ status='SKIPPED'; reason='UV_NOT_FOUND' })
    return $false
  }
  $target = Join-Path $Root ([string]$Policy.repo_runtime_dir)
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  $oldRegistry = $env:UV_PYTHON_INSTALL_REGISTRY
  $oldBin = $env:UV_PYTHON_INSTALL_BIN
  try {
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    $env:UV_PYTHON_INSTALL_BIN = '0'
    $requested = [string]$Policy.preferred_provision_version
    $started = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    $out = @(& $uv.Source python install $requested --install-dir $target --no-bin --no-config 2>&1)
    $exit = $LASTEXITCODE
    $detail = (($out | ForEach-Object { [string]$_ }) -join "`n").Trim()
    if ($detail.Length -gt 1200) { $detail = $detail.Substring($detail.Length - 1200) }
    [void]$Provisioning.Add([pscustomobject][ordered]@{
      status = $(if ($exit -eq 0) {'COMPLETED'} else {'FAILED'})
      method = 'uv_python_install'
      requested_version = $requested
      install_dir = $target
      started_at = $started
      completed_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
      exit_code = $exit
      detail = $detail
    })
    return ($exit -eq 0)
  } catch {
    [void]$Provisioning.Add([pscustomobject]@{ status='FAILED'; method='uv_python_install'; detail=$_.Exception.Message })
    return $false
  } finally {
    $env:UV_PYTHON_INSTALL_REGISTRY = $oldRegistry
    $env:UV_PYTHON_INSTALL_BIN = $oldBin
  }
}

$runtime = Find-ExistingPython
if (-not $runtime -and $AllowProvision -and $Policy.allow_repo_local_uv_provision) {
  [void](Install-RepoLocalPython)
  $runtime = Find-ExistingPython
}

if (-not $runtime) {
  $blocked = [ordered]@{
    status = 'BLOCKED'
    reason = 'NO_WORKING_PYTHON_3_11_PLUS'
    checked_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    minimum_version = [string]$Policy.minimum_version
    repo_local_provision_allowed = [bool]$Policy.allow_repo_local_uv_provision
    provisioning_attempted = [bool]($Provisioning.Count -gt 0)
    provisioning = @($Provisioning)
    probes = @($Diagnostics)
    remediation = @(
      'Inspect the recorded probe failures before changing the machine.',
      'If repo-local uv provisioning failed, repair uv/network/filesystem execution or install CPython 3.11+ explicitly.',
      'Do not begin Massive acquisition until this probe returns READY.'
    )
  }
  $json = $blocked | ConvertTo-Json -Depth 10
  if ($RuntimeOut) { Write-Utf8NoBom $RuntimeOut ($json + "`n") }
  Write-Output $json
  exit 127
}

$ready = [ordered]@{
  status = 'READY'
  mode = $runtime.mode
  source = $runtime.source
  executable = $runtime.executable
  resolved_executable = $runtime.resolved_executable
  prefix = @($runtime.prefix)
  version = $runtime.version
  checked_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  provisioned_repo_runtime = [bool]($Provisioning | Where-Object { $_.status -eq 'COMPLETED' })
  provisioning = @($Provisioning)
  probes = @($Diagnostics)
}
$readyJson = $ready | ConvertTo-Json -Depth 10
if ($RuntimeOut) { Write-Utf8NoBom $RuntimeOut ($readyJson + "`n") }

if ($ProbeOnly) {
  Write-Output $readyJson
  exit 0
}

if ([string]::IsNullOrWhiteSpace($Script)) {
  Write-Error 'Script is required unless -ProbeOnly is used.'
  exit 2
}

& $runtime.executable -B $Script @ScriptArgs
exit $LASTEXITCODE
