$ErrorActionPreference = 'Stop'
$taskBuildDir = $PSScriptRoot
$taskReportDir = [IO.Path]::GetDirectoryName($taskBuildDir)
$taskSourceDocx = Join-Path $taskBuildDir '光波导布线实验简明报告.docx'
$taskFinalDoc = Join-Path $taskReportDir '光波导布线实验简明报告.doc'
$taskQaPdf = Join-Path $taskBuildDir 'final_doc_qa.pdf'
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
    $taskWordDoc.SaveAs2($taskFinalDoc, 0)
    $taskWordDoc.Close(0)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWordDoc)
    $taskWordDoc = $null

    # Verify the actual legacy DOC after reopening, then export that file for layout QA.
    $taskWordDoc = $taskWordApp.Documents.Open($taskFinalDoc, $false, $true, $false)
    $taskWordDoc.Repaginate()
    $taskPages = $taskWordDoc.ComputeStatistics(2)
    $taskImages = $taskWordDoc.InlineShapes.Count
    $taskTables = $taskWordDoc.Tables.Count
    $taskWordDoc.ExportAsFixedFormat($taskQaPdf, 17)
    $taskStats = [pscustomobject]@{
        Pages = $taskPages
        Images = $taskImages
        Tables = $taskTables
        FinalDoc = $taskFinalDoc
        QaPdf = $taskQaPdf
    }
    $taskStats | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBuildDir 'export_stats.json') -Encoding utf8
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
