# GoHome cloud media deployment

This directory defines the production media plane. MediaMTX is pinned to
`v1.19.3`; it forwards the box-composed H.264 stream and never redraws privacy
output.

## Network contract

- `8322/tcp`: public RTSPS publishing from bound boxes.
- `8189/udp` and `8189/tcp`: public WebRTC ICE media.
- `3478/tcp`: public Coturn listener for restrictive client networks.
- `49160-49200/udp`: public Coturn relay allocation range.
- `8889/tcp`, `9997/tcp`, `9998/tcp`: loopback only.
- `/media/`: HTTPS WHEP signaling through nginx.
- `/internal/mediamtx/auth`: never proxy publicly; MediaMTX calls it on loopback.

## Installation contract

1. Install the official MediaMTX `v1.19.3` binary at
   `/usr/local/bin/mediamtx` and verify its release checksum.
2. Create the locked service account `mediamtx` without a login shell.
3. Keep `/etc/gohome` owned by `root:gohome` with mode `0751`. Create
   `/etc/gohome/media` as `root:mediamtx / 0750` and `/etc/gohome/coturn` as
   `root:turnserver / 0750`. The application, media plane and relay can traverse
   the common root but can list and read only their own configuration boundary.
   Install `mediamtx.yml` and a completed `mediamtx.env` under
   `/etc/gohome/media/`; set both to `root:mediamtx`, mode `0640` and `0600`
   respectively.
4. Install `renew-media-certificates.sh` as
   `/etc/letsencrypt/renewal-hooks/deploy/gohome-media-certificates`, mode `0750`,
   and run it once. It validates the certificate/key pair, atomically replaces
   `/etc/gohome/media/tls/server.crt` and `server.key`, then restarts MediaMTX.
5. Generate independent random values for `GOHOME_MEDIA_AUTH_SECRET`,
   `GOHOME_MEDIAMTX_AUTH_SHARED_SECRET`, and the Coturn shared secret. Never use
   a device token as one of these service secrets.
6. Install the distribution `coturn` package, disable its stock unit, and install
   `gohome-coturn.service` plus a completed
   `/etc/gohome/coturn/turnserver.conf` owned by `root:turnserver` with mode
   `0640`. The TURN secret must be identical to
   `MTX_WEBRTCICESERVERS2_0_PASSWORD` in `mediamtx.env`; the public and private IP
   values must match the current cloud instance network. Keep the secret in the
   configuration file so it is never exposed through process arguments.
7. Install `gohome-mediamtx.service`, include `nginx-media.conf` in the existing
   TLS virtual host, run `nginx -t`, then enable the GoHome MediaMTX and Coturn
   units. Open `8322/tcp`, `8189/tcp+udp`, `3478/tcp`, and
   `49160-49200/udp` in the cloud security group.
   The MediaMTX unit must retain `AF_NETLINK` in `RestrictAddressFamilies`.
   Pion uses Linux route netlink to select ICE interfaces even when interface
   candidates are disabled; omitting it makes every WHEP SDP offer fail before
   a reader is created.

## Acceptance checks

- `/health` reports both `media_access.configured` and
  `media_access.mediamtx_auth_configured` as true without exposing secrets.
- Anonymous RTSPS publishing and WHEP reading are rejected.
- A bound box can publish only its own enabled cameras.
- A current family member can obtain a read session only for the family's
  current privacy mode; changing mode invalidates existing sessions.
- MediaMTX API and metrics cannot be reached from the public network.
- A real WHEP offer returns `201`, creates a reader, and does not log
  `error getting local interfaces`.
- Certificate renewal dry-run completes and the deploy hook preserves a matching
  certificate/key pair without changing file ownership or permissions.
- Direct ICE and forced TURN playback both pass a 30-minute dual-camera test.
