param(
    [Parameter(Mandatory=$true)][string]$InputDocx,
    [Parameter(Mandatory=$true)][string]$OutputPdf
)
$ErrorActionPreference = 'Stop'
$taskWordApp = $null
$taskWordDoc = $null
try {
    $taskWordApp = New-Object -ComObject Word.Application
    $taskWordApp.Visible = $false
    $taskWordApp.DisplayAlerts = 0
    $taskWordDoc = $taskWordApp.Documents.Open($InputDocx, $false, $true)
    $taskWordDoc.Fields.Update() | Out-Null
    $taskWordDoc.Repaginate()
    $taskPages = $taskWordDoc.ComputeStatistics(2)
    $taskWordDoc.ExportAsFixedFormat($OutputPdf, 17)
    @{ pages = $taskPages; pdf = $OutputPdf; renderer = 'Microsoft Word native' } | ConvertTo-Json -Compress
}
finally {
    $taskSaveMode = 0
    if ($null -ne $taskWordDoc) { $taskWordDoc.Close([ref]$taskSaveMode) | Out-Null }
    if ($null -ne $taskWordApp) { $taskWordApp.Quit([ref]$taskSaveMode) | Out-Null }
    if ($null -ne $taskWordDoc) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskWordDoc) | Out-Null }
    if ($null -ne $taskWordApp) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskWordApp) | Out-Null }
}

