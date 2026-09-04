#!/bin/bash
set -euo pipefail

readonly HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly VERSION=3.5.2
readonly COMMIT=ed21d7f94bb346b5ba98e846bd71cd59782b453a
readonly BUILD_ROOT="$HERE/build"
readonly SOURCE="$BUILD_ROOT/pigallery2"

for tool in git node npm docker; do
  command -v "$tool" >/dev/null || {
    echo "Missing required command: $tool" >&2
    exit 1
  }
done

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT"
git clone --filter=blob:none https://github.com/bpatrik/pigallery2.git "$SOURCE"
git -C "$SOURCE" checkout --detach "$COMMIT"
test "$(node -p "require('$SOURCE/package.json').version")" = "$VERSION"

cp -a "$HERE/overlay/." "$SOURCE/"
cd "$SOURCE"
npm ci
npm run build

mv "$SOURCE/dist" "$BUILD_ROOT/dist"
docker build \
  -t "viltkamera/pigallery2:${VERSION}-map-waypoints" \
  -f "$HERE/Dockerfile" "$HERE"

echo "Built viltkamera/pigallery2:${VERSION}-map-waypoints"
