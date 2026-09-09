# System Resource Analysis Script
Write-Host "=== 系统资源分析 ===" -ForegroundColor Cyan

# Memory Info
Write-Host "`n[内存信息]" -ForegroundColor Yellow
$os = Get-CimInstance Win32_OperatingSystem
$totalMem = [math]::Round($os.TotalVisibleMemorySize/1MB, 2)
$freeMem = [math]::Round($os.FreePhysicalMemory/1MB, 2)
$usedMem = [math]::Round($totalMem - $freeMem, 2)
$memPercent = [math]::Round(($usedMem / $totalMem) * 100, 1)

Write-Host "总内存: $totalMem GB"
Write-Host "已用内存: $usedMem GB"
Write-Host "可用内存: $freeMem GB"
Write-Host "内存使用率: $memPercent%"

# Disk Info
Write-Host "`n[磁盘信息]" -ForegroundColor Yellow
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$totalDisk = [math]::Round($disk.Size/1GB, 2)
$freeDisk = [math]::Round($disk.FreeSpace/1GB, 2)
$usedDisk = [math]::Round($totalDisk - $freeDisk, 2)
$diskPercent = [math]::Round(($usedDisk / $totalDisk) * 100, 1)

Write-Host "C盘总容量: $totalDisk GB"
Write-Host "C盘已用: $usedDisk GB"
Write-Host "C盘可用: $freeDisk GB"
Write-Host "C盘使用率: $diskPercent%"

# Top Memory Processes
Write-Host "`n[占用内存最多的10个进程]" -ForegroundColor Yellow
$topProc = Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 
foreach ($p in $topProc) {
    $memMB = [math]::Round($p.WorkingSet/1MB, 2)
    Write-Host "$($p.Name): $memMB MB"
}

# Risk Assessment
Write-Host "`n[风险评估]" -ForegroundColor Yellow
if ($memPercent -gt 80) {
    Write-Host "⚠️  内存使用率过高 ($memPercent%)" -ForegroundColor Red
}
if ($diskPercent -gt 80) {
    Write-Host "⚠️  C盘使用率过高 ($diskPercent%)" -ForegroundColor Red
}

Write-Host "`n=== 分析完成 ===" -ForegroundColor Cyan
