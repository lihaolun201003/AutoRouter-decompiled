$ErrorActionPreference = 'Stop'
$taskBuildDir = $PSScriptRoot
$taskReportDir = [IO.Path]::GetDirectoryName($taskBuildDir)
$taskSourceDocx = Join-Path $taskBuildDir '光波导布线全部实验报告.docx'
$taskFinalPdf = Join-Path $taskReportDir '光波导布线全部实验报告.pdf'
$taskExportPdf = Join-Path $taskBuildDir 'all_experiments_word_export.pdf'
$taskWordApp = $null
$taskWordDoc = $null
try {
    $taskWordApp = New-Object -ComObject Word.Application
    $taskWordApp.Visible = $false
    $taskWordApp.DisplayAlerts = 0
    $taskWordApp.AutomationSecurity = 3
    $taskWordDoc = $taskWordApp.Documents.Open($taskSourceDocx, $false, $true, $false)
    [void]$taskWordDoc.Fields.Update()
    $taskWordDoc.Repaginate()
    $taskPages = $taskWordDoc.ComputeStatistics(2)
    $taskImages = $taskWordDoc.InlineShapes.Count
    $taskTables = $taskWordDoc.Tables.Count
    $taskWordDoc.ExportAsFixedFormat($taskExportPdf, 17)
    Copy-Item -LiteralPath $taskExportPdf -Destination $taskFinalPdf -Force
    $taskStats = [pscustomobject]@{
        Pages = $taskPages
        Images = $taskImages
        Tables = $taskTables
        FinalPdf = $taskFinalPdf
    }
    $taskStats | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBuildDir 'all_experiments_export_stats.json') -Encoding utf8
    $taskStats | ConvertTo-Json
}
finally {
    if ($null -ne $taskWordDoc) {
        $taskWordDoc.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWordDoc)
    }
    if ($null -ne $taskWordApp) {
        $taskWordApp.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWordApp)
    }
}
