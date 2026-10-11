#!/bin/sh
# Copy Caddy's certificate for the TURN domain to where coturn reads it, and
# restart coturn when it changed. Run daily (coturn-certs.timer) and once by
# hand after installing.
set -eu

DOMAIN=${DOMAIN:-wildjoker.0s.is}
# Where Caddy (the Debian/Ubuntu package) keeps its certificates. Find yours
# with: sudo find / -name "$DOMAIN.crt" -path '*caddy*' 2>/dev/null
CADDY_CERTS=${CADDY_CERTS:-/var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory}
SRC="$CADDY_CERTS/$DOMAIN"
DEST=/etc/coturn/certs

[ -f "$SRC/$DOMAIN.crt" ] || { echo "no certificate at $SRC/$DOMAIN.crt" >&2; exit 1; }
install -d -m 750 -o root -g turnserver "$DEST"

if cmp -s "$SRC/$DOMAIN.crt" "$DEST/fullchain.pem" && cmp -s "$SRC/$DOMAIN.key" "$DEST/privkey.pem"; then
  exit 0
fi
install -m 644 -o root -g turnserver "$SRC/$DOMAIN.crt" "$DEST/fullchain.pem"
install -m 640 -o root -g turnserver "$SRC/$DOMAIN.key" "$DEST/privkey.pem"
echo "certificate for $DOMAIN updated, restarting coturn"
systemctl restart coturn
