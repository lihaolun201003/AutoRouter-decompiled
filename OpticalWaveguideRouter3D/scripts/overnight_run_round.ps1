param(
  [Parameter(Mandatory=$true)][string]$Round,
  [string]$Adoption = "",
  [string[]]$Only = @(),
  [switch]$SkipFreeze
  [switch]$SkipExisting
)
$ErrorActionPreference = "Stop"
$root = "."
$out  = "outputs\overnight_3d_ideas"
$py   = ".\.venv\Scripts\python.exe"
if (-not $SkipFreeze) {
  $a = @("-B","scripts\freeze_overnight_manifest.py",$root,$out,"--round",$Round)
  if ($Adoption -ne "") { $a += @("--adoption",$Adoption) }
  & $py @a
}
$manifest = Get-Content "$out\manifest\round_$Round.json" -Raw | ConvertFrom-Json
$groups = @($manifest.groups)
if ($Only.Count -gt 0) { $groups = @($groups | Where-Object { $Only -contains $_ }) }
if ($SkipExisting) {
  $groups = @($groups | Where-Object { -not (Test-Path "$out\$Round\$_\summary.json") })
}
if ($groups.Count -eq 0) { Write-Output "nothing to run for round $Round"; exit 0 }
Write-Output ("running " + $groups.Count + " groups of round " + $Round)
& ".\scripts\overnight_launch.ps1" -Round $Round -Groups $groups -Adoption $Adoption
