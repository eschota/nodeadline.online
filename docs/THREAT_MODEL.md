# Threat model (V2, short)

## Trust boundaries

1. **Public internet → Master (HTTPS)**  
   Anyone can hit landing, OAuth start, tracker announce, public APIs. Rate-limit DNS and probe endpoints. Secrets only on server filesystem.

2. **Browser → Node (HTTP, usually localhost)**  
   Attacker on same machine can call APIs. **Destructive / owner APIs** require session cookie + (where noted) `REMOTE_ADDR` loopback-only for UPnP and manual port mutation.

3. **Node → Master**  
   OAuth redeem uses one-time codes; validate `return_to` allowlist (loopback only).

4. **Public share URLs**  
   Only paths under registered share roots; no `..`; optional unguessable slug/token for non-listed public shares (future).

## What we do not claim

- BitTorrent peers are untrusted for integrity until content is verified against published snapshot hash (phase 3).
- `HOST=0.0.0.0` exposes the node on LAN; document for users.

## Operational

- Rotate GitHub PAT / Google secrets if exposed.
- Namecheap API key: VPS IP allowlist in Namecheap panel.
