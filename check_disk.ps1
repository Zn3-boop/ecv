$disk = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DeviceID -eq 'C:' }
$total = [math]::Round($disk.Size/1GB, 2)
$free = [math]::Round($disk.FreeSpace/1GB, 2)
$used = [math]::Round($total - $free, 2)
$percent = [math]::Round(($used / $total) * 100, 1)
Write-Host "C盘总容量: $total GB"
Write-Host "C盘已用: $used GB"
Write-Host "C盘可用: $free GB"
Write-Host "C盘使用率: $percent%"
