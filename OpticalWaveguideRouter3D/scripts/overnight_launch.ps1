param(
  [Parameter(Mandatory=$true)][string]$Round,
  [Parameter(Mandatory=$true)][string[]]$Groups,
  [string]$Adoption = "",
  [string]$Tag = ""
)
$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"
$logdir = "outputs\overnight_3d_ideas\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$procs = @()
foreach ($g in $Groups) {
  $a = @("-B","scripts\run_overnight_3d.py",".","outputs\overnight_3d_ideas","--round",$Round,"--group",$g)
  if ($Adoption -ne "") { $a += @("--adoption", $Adoption) }
  if ($Tag -ne "") { $a += @("--tag", $Tag) }
  $suffix = if ($Tag -ne "") { "_" + $Tag } else { "" }
  $procs += Start-Process -FilePath $py -ArgumentList $a -NoNewWindow -PassThru `
      -RedirectStandardOutput "$logdir\console_$g$suffix.log" `
      -RedirectStandardError  "$logdir\console_$g${suffix}_err.log"
}
Write-Output ("launched " + $procs.Count + " groups of round " + $Round)
$procs | Wait-Process
$fail = 0
foreach ($p in $procs) { if ($p.ExitCode -ne 0) { $fail++; Write-Output ("FAILED pid=" + $p.Id + " code=" + $p.ExitCode) } }
Write-Output ("BATCH DONE round=" + $Round + " failures=" + $fail)
