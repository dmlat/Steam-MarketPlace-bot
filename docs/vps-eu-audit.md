# VPS eu Audit Report

**Host:** 5542993-yg68522 (5.129.237.108)  
**Date:** 2026-06-10

## Verdict: GO (after disk cleanup)

| Resource | Before cleanup | After cleanup |
|---|---|---|
| Disk / | 96% (4.9 GB free) | **23% (77 GB free)** |
| Docker build cache | ~10 GB | 0 B |
| CPU | 8 vCPU, load ~5 | load ~5 (shared) |
| RAM | 11 GB, ~6 GB avail | OK |

## Port map (conflicts avoided)

| Port | Owner | Our project |
|---|---|---|
| 5433 | morpheus-db (127.0.0.1) | **Do not use** |
| 5434 | stt_db | — |
| 5435 | morpheus-db-staging | — |
| **5436** | free | **steam_scanner Postgres** |

## GitHub deploy

- SSH host alias: `github-steam-marketplace-bot`
- Key: `~/.ssh/github_deploy_steam_marketplace_bot`
- Repo: `dmlat/Steam-MarketPlace-bot`

## Deploy path

`~/Steam-MarketPlace-bot`

## Monitoring from Windows

```powershell
ssh eu "cd ~/Steam-MarketPlace-bot && ./deploy/status.sh"
```

## Notes

- 28 other Docker containers — do not modify
- Do not open Steam in browser on VPS egress IP used for scraping
- Proxies: 3x SOCKS5 on port 50101 (verified PASS locally)