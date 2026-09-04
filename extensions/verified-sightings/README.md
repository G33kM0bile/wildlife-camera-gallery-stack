# Verified sightings extension

PiGallery2 3.5.2 extension that lets authenticated users add/remove a photo
from the logical album **Bekreftede observasjoner**. The source of truth is the
runtime file `verified-sightings.json`; it is intentionally ignored by Git and
must be backed up.

Install `package.json` and `server.js` in PiGallery's persistent extension
directory, normally:

```text
/opt/pigallery2/config/extensions/verified-sightings/
```

Restart PiGallery2 and enable the extension in Settings if required. Build and
test after source changes:

```bash
npm ci
npm run build
npm test
```

Original photos are not modified by this extension.
