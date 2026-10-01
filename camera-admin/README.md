# Camera metadata admin

Norwegian-language web UI for the five folders `hc960-01` through `hc960-05`.
It edits camera position, location, title, subject, comment, tags and enabled
state. Authentication is delegated to the existing SFTPGo administrator API.
The placement map uses Kartverket's public topographic WMS as its background
layer; no map API key is stored by this component.

Copy `config/cameras.example.json` to the ignored `config/cameras.json` and
replace all fake values before installation. The top-level installer handles
dependencies, systemd units and the metadata watcher:

```bash
sudo ../scripts/install-metadata-stack.sh
```

The default listener is `127.0.0.1:9095`. Existing production configuration is
preserved during reinstall. Changes apply only to new uploads.
