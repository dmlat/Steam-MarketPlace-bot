# Steam API Endpoints Reference

## Allowed (read-only GET)

| Endpoint | Purpose |
|----------|---------|
| `https://store.steampowered.com/search/results/` | Discover games with Trading Cards (`category2=29`) |
| `https://steamcommunity.com/market/search/render/` | Search market items by appid and filters |
| `https://steamcommunity.com/market/priceoverview/` | Lowest/median price and volume |
| `https://steamcommunity.com/market/listings/{appid}/{name}` | Item listing page, extract `item_nameid` |
| `https://steamcommunity.com/market/itemordershistogram` | Buy/sell order book histogram |
| `https://api.steampowered.com/ISteamEconomy/GetAssetClassInfo/v1/` | Optional metadata (requires API key) |

## Prohibited

| Pattern | Reason |
|---------|--------|
| POST to `/market/*` | Order placement/modification |
| `/tradeoffer/*` | Trade automation |
| Authenticated endpoints requiring login | Account access |
| External skin/gambling sites | Out of scope |

## Excluded appids

- 730 — CS2 / Counter-Strike
- 440 — Team Fortress 2
- 570 — Dota 2
- 252490 — Rust

## Primary market appid

Steam Community Items use `appid=753` on the Community Market.
