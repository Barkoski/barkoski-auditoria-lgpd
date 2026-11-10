Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$exclude = @('.claude','router.php','deploy.zip','sql-antigo','build-zip.ps1')
$root = (Get-Location).Path
$zipPath = Join-Path $root 'deploy-isca.zip'

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

Get-ChildItem -Path $root -Recurse -File | Where-Object {
    $relTop = $_.FullName.Substring($root.Length + 1).Split([System.IO.Path]::DirectorySeparatorChar)[0]
    $exclude -notcontains $relTop
} | ForEach-Object {
    $relPath = $_.FullName.Substring($root.Length + 1).Replace('\', '/')
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $relPath) | Out-Null
}

$zip.Dispose()
