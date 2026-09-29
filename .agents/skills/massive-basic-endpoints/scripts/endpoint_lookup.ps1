param(
  [string]$Market,
  [string]$Search,
  [string]$Path
)

$ErrorActionPreference = 'Stop'
$catalogPath = Join-Path $PSScriptRoot '..\references\endpoint-catalog.json'
$catalog = Get-Content -Raw -LiteralPath $catalogPath | ConvertFrom-Json
$rows = @($catalog.entries)

if ($Market) {
  $rows = @($rows | Where-Object { $_.market -ieq $Market })
}
if ($Path) {
  $rows = @($rows | Where-Object { $_.path -eq $Path })
}
if ($Search) {
  $needle = $Search.ToLowerInvariant()
  $rows = @($rows | Where-Object {
    ($_.capability + ' ' + $_.path + ' ' + $_.best_for + ' ' + $_.basic_limit).ToLowerInvariant().Contains($needle)
  })
}

[pscustomobject]@{
  snapshot_date = $catalog.snapshot_date
  plan = $catalog.plan
  count = $rows.Count
  entries = $rows
} | ConvertTo-Json -Depth 8
