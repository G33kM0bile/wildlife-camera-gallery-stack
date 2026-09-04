# Named and colored GPX waypoints

This overlay targets PiGallery2 3.5.2 at commit
`ed21d7f94bb346b5ba98e846bd71cd59782b453a`.

`build.sh` clones that exact revision, overlays two frontend files, builds all
locales, and creates `viltkamera/pigallery2:3.5.2-map-waypoints`. The final image
uses the same PiGallery2 3.5.2 manifest digest captured by the reference
deployment.

Build requirements are Git, Node.js 22/npm, Docker and roughly 2 GB free RAM.

```bash
./build.sh
```

Before rebuilding on a different architecture, verify the pinned manifest
supports it. To intentionally use another base, pass a tested build argument:

```bash
docker build --build-arg BASE_IMAGE=... -t ... -f Dockerfile .
```

Do not apply this overlay blindly to another PiGallery version. Rebase the two
files, run TypeScript/build tests and verify map behavior first.
