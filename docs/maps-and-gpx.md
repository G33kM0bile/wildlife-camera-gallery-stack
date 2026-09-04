# GPX maps and camera positions

## Waypoint schema

PiGallery2 3.5.2 normally retains only waypoint latitude/longitude in its map
frontend. The included overlay also parses:

```xml
<wpt lat="60.001" lon="10.001">
  <name>Camera 1 | North crossing</name>
  <desc>Wildlife camera</desc>
  <sym>Camera</sym>
  <type>camera</type>
</wpt>
```

The popup renders name, description, category and coordinates. User-controlled
GPX text is HTML-escaped before it enters the Leaflet popup.

## Marker colors

The mapper normalizes Norwegian and English-like category text from `name`,
`desc`, `sym` and `type`:

| Category | Color |
|---|---|
| camera / `hc960` / `viltkamera` | orange |
| hunting tower / `jakttårn` | red |
| animal track / `trakk` | yellow |
| access / parking / junction | green |
| named posts, crossings, benches and huts | blue |
| other named POI | purple |
| missing or unknown | gray |

Use stable `<type>` values where possible; relying on the displayed name alone
is less predictable.

## Tracks and boundaries

Tracks remain ordinary GPX `<trk>/<trkseg>/<trkpt>` elements and are drawn by
PiGallery2's existing implementation. A waypoint and track may coexist in one
file.

## Privacy

Production hunting boundaries and camera positions are sensitive even if the
gallery requires login. Keep the real GPX outside Git, restrict the gallery to
intended users, and remove GPS/GPX data from any images or exports intended for
fully public distribution.

## Moving a camera

1. Update camera coordinates, title, location, tags and descriptive fields in
   the camera admin UI.
2. Update the matching private GPX waypoint.
3. Upload/replace the GPX at the photo-tree root.
4. Remove only the generated cache matching that GPX from PiGallery's temp
   directory if the map does not refresh. PiGallery2 3.5.2 does not compare the
   source timestamp before reusing a compressed GPX. For example:

   ```bash
   find /opt/pigallery2/tmp -type f \
     -name 'your-private-map.gpx_*' -print
   # Verify every printed path, then remove those exact generated files.
   ```

5. Hard-refresh the browser or clear the site's cached data.
6. Restart or re-index PiGallery if its directory listing is stale.
7. Test one new camera upload.

Changing configuration affects new images only. Historical images retain the
metadata that was valid when they were captured unless a deliberate, backed-up
backfill is run.
