# Downloads the tools bundled into the app: libmpv (video engine), ffmpeg, a Japanese font.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Force deps | Out-Null
$headers = @{}
if ($env:GITHUB_TOKEN) { $headers.Authorization = "Bearer $env:GITHUB_TOKEN" }

# libmpv from shinchiro's Windows builds (the ones linked from mpv.io)
$rel = Invoke-RestMethod -Headers $headers https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest
$asset = $rel.assets | Where-Object { $_.name -match '^mpv-dev-x86_64-\d{8}' } | Select-Object -First 1
if (-not $asset) { throw "No mpv-dev-x86_64 asset in shinchiro release $($rel.tag_name)" }
Write-Output "libmpv: $($asset.name)"
Invoke-WebRequest $asset.browser_download_url -OutFile deps/mpv-dev.7z
7z e deps/mpv-dev.7z -odeps libmpv-2.dll -r -y | Out-Null
if (-not (Test-Path deps/libmpv-2.dll)) { throw "libmpv-2.dll not found in $($asset.name)" }

# ffmpeg (static build)
Invoke-WebRequest https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip -OutFile deps/ffmpeg.zip
Expand-Archive deps/ffmpeg.zip deps/ffmpeg -Force
foreach ($tool in 'ffmpeg.exe', 'ffprobe.exe') {
  $f = Get-ChildItem deps/ffmpeg -Recurse -Filter $tool | Select-Object -First 1
  Copy-Item $f.FullName deps/
}

# Japanese font for the text drawn on card fronts (optional: falls back to Windows fonts)
foreach ($w in 'Bold', 'Regular') {
  try {
    Invoke-WebRequest "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/JP/NotoSansJP-$w.otf" -OutFile "deps/NotoSansJP-$w.otf"
  } catch { Write-Output "::warning::Font download failed ($w): $_" }
}

Get-ChildItem deps -File | Format-Table Name, Length
