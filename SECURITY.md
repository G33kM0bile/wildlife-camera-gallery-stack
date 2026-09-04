# Security notes

This repository intentionally contains no passwords, API tokens, SSH keys,
user database, photos, production configuration, or real hunting/camera
coordinates. `information-site/viltkamera.html` does contain the already-public
service URLs and contact text printed for the physical camera QR-code workflow.
Review that page before changing repository visibility.

Keep the SFTPGo WebAdmin API and camera-admin service on a trusted network or
behind an authenticated reverse proxy. Publish only PiGallery2, enable its
built-in authentication, replace the default administrator password before
uploading photos, and back up all authentication state encrypted.

Never commit `.env`, `cameras.json`, `verified-sightings.json`, production GPX
files, PiGallery databases or SFTPGo provider databases.
