# Caddy-hosted camera information page

This folder backs up the static Norwegian information page used by the QR code
physically attached to each camera. Its production URL is intentionally stable:

```text
https://8370.no/viltkamera.html?id=hc960-01
```

Do not move or redirect that URL without replacing every printed QR code.

## Deployment

Copy the page to the existing Caddy document root:

```bash
install -o root -g root -m 0644 viltkamera.html /var/www/html/viltkamera.html
```

The page also expects this separately protected deployment asset:

```text
/var/www/html/grunneiertillatelse.jpg
```

`grunneiertillatelse.jpg` is intentionally excluded from Git because it may
contain private or legally sensitive information. Back it up through the
protected server backup instead.

No dedicated Caddy route is required when the existing `8370.no` site already
serves `/var/www/html` with `file_server`. Preserve and back up the production
Caddyfile separately; it may contain configuration for unrelated sites.
