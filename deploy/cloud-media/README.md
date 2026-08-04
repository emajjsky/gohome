# GoHome cloud media deployment

This directory defines the production media plane. MediaMTX is pinned to
`v1.19.3`; it forwards the box-composed H.264 stream and never redraws privacy
output.

## Network contract

- `8322/tcp`: public RTSPS publishing from bound boxes.
- `8189/udp` and `8189/tcp`: public WebRTC ICE media.
- `3478/tcp`: public Coturn relay for restrictive client networks.
- `8889/tcp`, `9997/tcp`, `9998/tcp`: loopback only.
- `/media/`: HTTPS WHEP signaling through nginx.
- `/internal/mediamtx/auth`: never proxy publicly; MediaMTX calls it on loopback.

## Installation contract

1. Install the official MediaMTX `v1.19.3` binary at
   `/usr/local/bin/mediamtx` and verify its release checksum.
2. Create the locked service account `mediamtx` without a login shell.
3. Install `mediamtx.yml` and a completed `mediamtx.env` under
   `/etc/gohome/media/`; set both to `root:mediamtx`, mode `0640` and `0600`
   respectively.
4. Copy the public TLS certificate and private key to
   `/etc/gohome/media/tls/server.crt` and `server.key`. The key must be readable
   only by `root:mediamtx`; renewals must update these copies atomically before
   restarting MediaMTX.
5. Generate independent random values for `GOHOME_MEDIA_AUTH_SECRET`,
   `GOHOME_MEDIAMTX_AUTH_SHARED_SECRET`, and the Coturn shared secret. Never use
   a device token as one of these service secrets.
6. Install Coturn with secret-based authentication and configure the same TURN
   secret in `mediamtx.env`. Limit its relay port range in the firewall and
   expose that range in addition to `3478/tcp`.
7. Install `gohome-mediamtx.service`, include `nginx-media.conf` in the existing
   TLS virtual host, run `nginx -t`, then enable both services.

## Acceptance checks

- `/health` reports both `media_access.configured` and
  `media_access.mediamtx_auth_configured` as true without exposing secrets.
- Anonymous RTSPS publishing and WHEP reading are rejected.
- A bound box can publish only its own enabled cameras.
- A current family member can obtain a read session only for the family's
  current privacy mode; changing mode invalidates existing sessions.
- MediaMTX API and metrics cannot be reached from the public network.
- Direct ICE and forced TURN playback both pass a 30-minute dual-camera test.
