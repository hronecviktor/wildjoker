# Deploying Wild Joker

How to run Wild Joker at **https://zolik.0s.is** and **https://cards.0s.is**
(the same game under both names), on the server that already hosts
bbl3d.0s.is behind Caddy:

- the game is one Docker image, built on your machine and pushed to your
  Docker Hub account; the server pulls it and runs it on `127.0.0.1:8100`,
  restarting it after crashes and at boot;
- Caddy serves both names with automatic HTTPS and proxies to it
  (WebSockets included);
- **coturn**, installed next to it, relays voice chat for players whose
  network doesn't allow a direct connection (common on mobile data). It
  runs under `zolik.0s.is`.

The server commands assume Debian or Ubuntu, with Caddy installed from its
apt package (as a systemd service with `/etc/caddy/Caddyfile`), Docker with
the compose plugin, and `ufw` as the firewall. Run them as root or with
`sudo`.

## Values you choose

| What | Where it goes | Example |
|---|---|---|
| **Docker Hub account** | `deploy/publish.sh` (`DOCKERHUB_USER`), `.env` (`WILDJOKER_IMAGE`) | `viktor` → `viktor/wildjoker:latest` |
| **TURN secret**: a long random string, generate it with `openssl rand -hex 32` | `.env` (`WILDJOKER_TURN_SECRET`) **and** `turnserver.conf` (`static-auth-secret`): both must be the same | `3f9c…` (64 hex characters) |
| **Server's public IPv4** (and IPv6, if it has one) | DNS records; `turnserver.conf` `external-ip` only if the server is behind NAT (step 5.3) | `203.0.113.10` |
| **Port for the container** (if 8100 is taken) | `.env` (`WILDJOKER_PORT`) and the Caddyfile | `8100` |

Everything else in the files below can stay as it is.

## 1. Publish the image

On the machine with the code (the VM or your computer), log in to Docker Hub
once and publish:

```bash
docker login                                 # your Docker Hub account
DOCKERHUB_USER=viktor deploy/publish.sh      # build and push
```

It refuses to run with uncommitted changes, so every image matches a
commit; it's pushed as `viktor/wildjoker:latest` and
`viktor/wildjoker:<commit>`. The build is for `linux/amd64` (most servers;
check with `uname -m` on the server: `x86_64`). For an ARM server
(`aarch64`) set `PLATFORM=linux/arm64`, which needs QEMU emulation for
buildx on an x86 machine.

A **public** repository on Docker Hub needs nothing more on the server. For
a **private** one, run `docker login` on the server too (an access token
with read-only access is enough).

## 2. DNS

At your DNS provider for `0s.is`, add for both `zolik` and `cards`:

| Type | Name | Value |
|---|---|---|
| `A` | `zolik`, `cards` | the server's public IPv4 (the same as `bbl3d`) |
| `AAAA` | `zolik`, `cards` | the server's IPv6, only if `bbl3d` has one too |

Check that both resolve before continuing (Caddy needs it to get the
certificates):

```bash
dig +short zolik.0s.is cards.0s.is     # prints the server's IP twice
```

## 3. The game container

The server only needs the files in this `deploy/` folder, not the code.
Copy them over, e.g. from your computer:

```bash
scp -r ~/ai/projects/priv/wildjoker/deploy server:/tmp/wildjoker-deploy
```

and on the server put them in place and create the settings file:

```bash
mkdir -p /opt/wildjoker && cp -r /tmp/wildjoker-deploy/. /opt/wildjoker/
cd /opt/wildjoker
cp env.example .env
chmod 600 .env
openssl rand -hex 32          # copy this: it's your TURN secret
nano .env                     # WILDJOKER_IMAGE and WILDJOKER_TURN_SECRET
```

Pull and start it:

```bash
docker compose pull
docker compose up -d
docker compose ps             # STATUS shows "healthy" after a few seconds
curl http://127.0.0.1:8100/healthz     # prints: ok
```

**Restarting at boot:** the container has `restart: unless-stopped`, so
Docker starts it again whenever Docker itself starts. Make sure Docker
starts at boot (it does by default on Debian and Ubuntu):

```bash
systemctl is-enabled docker   # enabled; if not: systemctl enable docker
```

Its settings, all in `.env`:

| Variable | Meaning |
|---|---|
| `WILDJOKER_IMAGE` | The image to run, e.g. `viktor/wildjoker:latest` (required). |
| `WILDJOKER_TURN_SECRET` | Shared secret for TURN credentials (required). |
| `WILDJOKER_TURN_URLS` | TURN servers given to browsers, comma-separated. Empty disables TURN. |
| `WILDJOKER_STUN_URLS` | STUN servers, comma-separated. |
| `WILDJOKER_TURN_TTL` | How long TURN credentials are valid (seconds, default 12 h). |
| `WILDJOKER_PORT` | Port on `127.0.0.1` for Caddy to proxy to (default 8100). |

## 4. Caddy

Add the block from `Caddyfile.snippet` to `/etc/caddy/Caddyfile`, next to the
`bbl3d.0s.is` block:

```caddyfile
zolik.0s.is, cards.0s.is {
	encode zstd gzip
	reverse_proxy 127.0.0.1:8100
}
```

`reverse_proxy` passes WebSockets through as they are; nothing else is
needed. Check and reload:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Open https://zolik.0s.is and https://cards.0s.is: the game loads, and Caddy
has fetched a certificate for each (it takes a few seconds the first time;
`journalctl -u caddy` shows it). The game works now; voice works for
players who can connect directly. coturn makes it work on every network.

## 5. coturn (TURN relay for voice chat)

### 5.1 Install

```bash
apt update
apt install coturn
systemctl stop coturn
```

On older releases (Ubuntu 20.04, Debian 11) the service is disabled until
you enable it in `/etc/default/coturn`: uncomment `TURNSERVER_ENABLED=1`.

### 5.2 Certificate for TURN over TLS (port 5349)

coturn uses a copy of the certificate Caddy got for `zolik.0s.is`.
`coturn-certs.sh` copies it and restarts coturn when it changes; a daily
timer keeps it up to date after Caddy renews (about every 60 days).

```bash
cd /opt/wildjoker
install -m 755 coturn-certs.sh /usr/local/bin/coturn-certs.sh
install -m 644 coturn-certs.service coturn-certs.timer /etc/systemd/system/
/usr/local/bin/coturn-certs.sh          # first copy; prints an error if it can't find the certificate
ls -l /etc/coturn/certs/                # fullchain.pem and privkey.pem
systemctl daemon-reload
systemctl enable --now coturn-certs.timer
```

If it says "no certificate at …", Caddy keeps its data elsewhere. Find it:

```bash
find / -name 'zolik.0s.is.crt' -path '*caddy*' 2>/dev/null
```

and set the directory that contains the `zolik.0s.is/` folder in
`/usr/local/bin/coturn-certs.sh` (`CADDY_CERTS=…`). For example, Caddy
uses `…/certificates/acme.zerossl.com-v2-dv90` when the certificate came from
ZeroSSL instead of Let's Encrypt.

### 5.3 Configuration

```bash
cp /etc/turnserver.conf /etc/turnserver.conf.orig     # the package's example, for reference
install -m 640 -o root -g turnserver /opt/wildjoker/turnserver.conf /etc/turnserver.conf
nano /etc/turnserver.conf
```

Change these lines (marked `CHANGE` in the file):

- `static-auth-secret=`: **the same secret** as `WILDJOKER_TURN_SECRET`
  in `/opt/wildjoker/.env`.
- `external-ip=`: only if the server is behind NAT. Compare
  `ip -4 addr` (addresses on the network interfaces) with
  `curl -4 ifconfig.me` (the public address). If the public address is
  among the interface addresses (most VPS, e.g. Hetzner), leave the line
  commented out. If it isn't (e.g. AWS, GCP), uncomment it as
  `external-ip=<public IP>/<private interface IP>`.

The rest of the file:

- listens on **3478** (UDP and TCP; STUN and TURN) and **5349** (TLS);
- relays audio through UDP ports **49152–49451**;
- only accepts credentials signed with the shared secret
  (`use-auth-secret`); the game server hands out credentials valid for 12
  hours to players connected to a room;
- refuses to relay to private, loopback and other special address ranges,
  so the relay can't be used to reach the server's own services or your
  local network;
- relays UDP only (no TCP relays), limits relays per user and in total,
  and has no admin console (`no-cli`);
- logs to the systemd journal.

### 5.4 Firewall

Open the TURN ports (the game itself only needs 80/443, which Caddy already
uses):

```bash
ufw allow 3478/udp
ufw allow 3478/tcp
ufw allow 5349/tcp
ufw allow 5349/udp
ufw allow 49152:49451/udp
ufw status
```

If your hosting provider has its own firewall (a cloud "security group"),
open the same ports there too.

### 5.5 Start

```bash
systemctl enable --now coturn
systemctl status coturn          # active (running)
journalctl -u coturn -n 50       # no "ERROR" lines about the config or certificate
ss -lnptu | grep turnserver      # listening on 3478 and 5349
```

### 5.6 Check that it works

**From your own computer**, check that STUN answers (in the `coturn`
package; on macOS `brew install coturn`):

```bash
turnutils_stunclient zolik.0s.is     # prints your public IP as "UDP reflexive addr"
```

**Check TURN.** First make a
credential on the server, the same way the game does:

```bash
SECRET=$(grep ^static-auth-secret= /etc/turnserver.conf | cut -d= -f2)
TURN_USER="$(( $(date +%s) + 3600 )):test"
PASS=$(printf %s "$TURN_USER" | openssl dgst -binary -sha1 -hmac "$SECRET" | base64)
echo "username: $TURN_USER"; echo "password: $PASS"
```

A quick test on the server itself: relay a few packets between two TURN
allocations.

```bash
turnutils_uclient -y -n 5 -u "$TURN_USER" -w "$PASS" zolik.0s.is
```

It ends with `Total lost packets 0`. `Cannot complete Allocation` means
the credentials were refused (secret mismatch or wrong clock).

For a check from your own network, open
https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/,
remove the default server, and add:

- STUN or TURN URI `turn:zolik.0s.is:3478`, with the username and
  password from above. Click **Gather candidates**: a row with type
  **relay** means TURN over UDP works.
- Repeat with `turns:zolik.0s.is:5349?transport=tcp` (TLS). A
  **relay** row again means TLS works too.

`authentication failed` or no relay row: the secret in `.env` and
`turnserver.conf` differ, the clock is wrong (`timedatectl`), or a port is
blocked; `journalctl -u coturn -f` shows what coturn sees while you try.

**In the game**: join voice with two devices, one of them on mobile data.
In Chrome, `chrome://webrtc-internals` shows the connection; in a
"candidate-pair" that is `succeeded`, the local candidate type `relay`
means it went through coturn.

## 6. Updating and logs

**Update to a new version.** Publish it (step 1), then run this on the
server. Restarting ends games in progress (rooms are kept in memory), so do
it when nobody is playing:

```bash
cd /opt/wildjoker
docker compose pull
docker compose up -d             # recreates the container with the new image
docker image prune -f            # remove the old image
```

To go back to an earlier version, set `WILDJOKER_IMAGE` in `.env` to an
older commit tag (e.g. `viktor/wildjoker:3ac122e`) and run
`docker compose up -d`.

If the deploy files changed (`git log -p deploy/`), copy them over again
(step 3, keeping your `.env`): a new `turnserver.conf` (keeping your secret
and `external-ip`) needs `systemctl restart coturn`, a new site block a
Caddy reload.

**Logs:**

```bash
cd /opt/wildjoker
docker compose logs -f --tail 100   # the game (kept up to 3 × 10 MB)
docker compose ps                   # running and healthy?
journalctl -u coturn -f             # TURN relay
journalctl -u caddy -f              # HTTPS, certificates, proxy errors
journalctl -u coturn-certs          # certificate copies
```

coturn logs little by default. To see each relay session while debugging,
add `verbose` to `/etc/turnserver.conf`, restart coturn, and remove it
afterwards.

**Stop or remove:** `docker compose down` stops the game;
`systemctl disable --now coturn coturn-certs.timer` stops coturn.

## Files here

| File | What it is |
|---|---|
| `../Dockerfile` | Builds the frontend with Node, then a slim Python image running the server. |
| `publish.sh` | Builds the image and pushes it to Docker Hub. |
| `docker-compose.yml` | Runs the image with `restart: unless-stopped`, on `127.0.0.1` only. |
| `env.example` | Template for `.env` (the image, settings and the TURN secret). |
| `Caddyfile.snippet` | The Caddy site block for both names. |
| `turnserver.conf` | coturn configuration. |
| `coturn-certs.sh`, `.service`, `.timer` | Copy Caddy's certificate to coturn, daily. |
