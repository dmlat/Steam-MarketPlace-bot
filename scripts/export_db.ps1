param([string]$OutFile = "steam_scanner.dump")
$containerDump = "/tmp/steam_scanner.dump"
docker exec steam_scanner_db pg_dump -U scanner -Fc steam_scanner -f $containerDump
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker cp "steam_scanner_db:${containerDump}" $OutFile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Exported to $OutFile ($((Get-Item $OutFile).Length) bytes)"
