param([string]$OutFile = "steam_scanner.dump")
docker exec steam_scanner_db pg_dump -U scanner -Fc steam_scanner > $OutFile
Write-Host "Exported to $OutFile"