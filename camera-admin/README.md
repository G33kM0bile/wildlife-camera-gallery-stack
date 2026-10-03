# Camera metadata admin

Norwegian-language web UI for the five folders `hc960-01` through `hc960-05`.
It edits camera position, location, title, subject, comment, tags and enabled
state. Authentication is delegated to the existing SFTPGo administrator API.
The placement map uses Kartverket's public topographic WMS as its background
layer; no map API key is stored by this component.
The unauthenticated login view also acts as a small service portal with links
to the gallery, public dashboard, status page, camera information page and
SFTPGo. Portal links are shown first; the visually subdued administrator login
is placed at the bottom. It does not expose internal host or container
addresses.
Elgbørsen and Storviltrapporten are listed separately as external resources so
users can distinguish third-party services from the self-hosted stack.
Both the portal and authenticated editor footer link back to this GitHub
repository for source code and documentation.

Copy `config/cameras.example.json` to the ignored `config/cameras.json` and
replace all fake values before installation. The top-level installer handles
dependencies, systemd units and the metadata watcher:

```bash
sudo ../scripts/install-metadata-stack.sh
```

The default listener is `127.0.0.1:9095`. Existing production configuration is
preserved during reinstall. Changes apply only to new uploads.
