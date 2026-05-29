$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolsDir = Join-Path $projectRoot "tools"
$ffmpegDir = Join-Path $toolsDir "ffmpeg"
$ffmpegExe = Join-Path $ffmpegDir "bin\ffmpeg.exe"
$archivePath = Join-Path $toolsDir "ffmpeg-release-essentials.zip"
$downloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

if (Test-Path -LiteralPath $ffmpegExe) {
    Write-Host "ffmpeg already installed: $ffmpegExe"
    & $ffmpegExe -version
    exit 0
}

New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

Write-Host "Downloading ffmpeg..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath

$extractDir = Join-Path $toolsDir "ffmpeg-extract"
if (Test-Path -LiteralPath $extractDir) {
    Remove-Item -LiteralPath $extractDir -Recurse -Force
}

Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDir -Force
$extractedRoot = Get-ChildItem -LiteralPath $extractDir -Directory | Select-Object -First 1
if ($null -eq $extractedRoot) {
    throw "Could not find extracted ffmpeg directory."
}

if (Test-Path -LiteralPath $ffmpegDir) {
    Remove-Item -LiteralPath $ffmpegDir -Recurse -Force
}

Move-Item -LiteralPath $extractedRoot.FullName -Destination $ffmpegDir
Remove-Item -LiteralPath $extractDir -Recurse -Force

Write-Host "ffmpeg installed: $ffmpegExe"
& $ffmpegExe -version
