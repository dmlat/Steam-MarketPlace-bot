# Compliance Note — Steam Market Research Scanner

This system is a **read-only research tool**. It does not perform any automated trading or account actions.

## Allowed actions

- Public HTTP GET requests to Steam Community Market and Steam Store endpoints
- Parsing publicly visible HTML and JSON responses
- Storing snapshots for offline analysis
- Generating reports and dashboards for manual review

## Prohibited actions

- Logging into Steam accounts
- Using authenticated session cookies (`sessionid`, etc.)
- Placing, modifying, or canceling buy/sell orders
- Confirming trades automatically
- Using proxies, VPNs, or region spoofing to access regional prices for purchase
- Integrating with external skin/gambling marketplaces
- Any automated buying or selling

## Rate limiting

- Minimum 1.5–3 seconds between requests (default: 2 seconds)
- Exponential backoff on errors and HTTP 429
- Nightly batch cap configurable (default: 10,000 requests)

## Data usage

Currency comparisons are for understanding Steam's internal rounding and pricing mechanics only — not for cross-region arbitrage execution.

## Manual verification

All "opportunities" flagged by the scanner require manual verification before any human trading decision.
