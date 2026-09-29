# Security notes

This repository intentionally contains no passwords, API tokens, SSH keys,
user database, photos, production configuration, or real hunting/camera
coordinates. `information-site/viltkamera.html` does contain the already-public
service URLs and contact text printed for the physical camera QR-code workflow.
The repository is intentionally public. Review that page before changing its
contact details or adding another external service.

The deliberately public surface currently includes the QR information URL,
gallery/login URL, SFTPGo login URL, public Grafana dashboard, status page and
the contact telephone number shown on the physical-camera information page.
None of those links should be treated as a substitute for authentication.

Keep the SFTPGo WebAdmin API and camera-admin service on a trusted network or
behind an authenticated reverse proxy. Publish only PiGallery2, enable its
built-in authentication, replace the default administrator password before
uploading photos, and back up all authentication state encrypted.

Never commit `.env`, `cameras.json`, `verified-sightings.json`, production GPX
files, PiGallery databases or SFTPGo provider databases.
