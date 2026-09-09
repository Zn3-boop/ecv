Write-Host "=== C盘清理脚本 ===" -ForegroundColor Cyan
Write-Host "开始清理临时文件..." -ForegroundColor Yellow

$totalCleaned = 0

# 1. Windows临时文件夹
Write-Host "`n[1/5] 清理Windows临时文件夹..." -ForegroundColor Yellow
$winTemp = "$env:TEMP"
$before = (Get-ChildItem $winTemp -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Remove-Item "$winTemp\*" -Recurse -Force -ErrorAction SilentlyContinue
$after = (Get-ChildItem $winTemp -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$cleaned = [math]::Round(($before - $after) / 1MB, 2)
$totalCleaned += $cleaned
Write-Host "已清理: $cleaned MB"

# 2. Windows Prefetch
Write-Host "`n[2/5] 清理Prefetch..." -ForegroundColor Yellow
$prefetch = "C:\Windows\Prefetch"
$before = (Get-ChildItem $prefetch -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Remove-Item "$prefetch\*" -Force -ErrorAction SilentlyContinue
$cleaned = [math]::Round($before / 1MB, 2)
$totalCleaned += $cleaned
Write-Host "已清理: $cleaned MB"

# 3. 清理用户临时文件夹
Write-Host "`n[3/5] 清理用户临时文件夹..." -ForegroundColor Yellow
$userTemp = "$env:LOCALAPPDATA\Temp"
$before = (Get-ChildItem $userTemp -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Remove-Item "$userTemp\*" -Recurse -Force -ErrorAction SilentlyContinue
$cleaned = [math]::Round($before / 1MB, 2)
$totalCleaned += $cleaned
Write-Host "已清理: $cleaned MB"

# 4. 清理Recent文件夹
Write-Host "`n[4/5] 清理Recent文件夹..." -ForegroundColor Yellow
$recent = "$env:APPDATA\Microsoft\Windows\Recent"
$before = (Get-ChildItem $recent -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Remove-Item "$recent\*" -Force -ErrorAction SilentlyContinue
$cleaned = [math]::Round($before / 1MB, 2)
$totalCleaned += $cleaned
Write-Host "已清理: $cleaned MB"

# 5. 清理下载文件夹中的旧文件（可选）
Write-Host "`n[5/5] 清理Download旧文件..." -ForegroundColor Yellow
$downloads = "$env:USERPROFILE\Downloads"
$oldFiles = Get-ChildItem $downloads -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) }
$cleaned = 0
foreach ($f in $oldFiles) {
    $cleaned += [math]::Round($f.Length / 1MB, 2)
    Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue
}
$totalCleaned += $cleaned
Write-Host "已清理: $cleaned MB"

Write-Host "`n=== 清理完成 ===" -ForegroundColor Green
Write-Host "总共释放: $totalCleaned MB" -ForegroundColor Cyan
