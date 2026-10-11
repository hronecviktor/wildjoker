#!/bin/sh
# Build the image and push it to Docker Hub, tagged :latest and with the
# commit it was built from. Log in first with `docker login`.
#
#   DOCKERHUB_USER=yourname deploy/publish.sh
#
# PLATFORM picks the server's architecture (default linux/amd64; for an
# ARM server use linux/arm64, which needs QEMU emulation set up for buildx).
set -eu
cd "$(dirname "$0")/.."

: "${DOCKERHUB_USER:?set DOCKERHUB_USER to your Docker Hub account}"
IMAGE=${IMAGE:-$DOCKERHUB_USER/wildjoker}
PLATFORM=${PLATFORM:-linux/amd64}
COMMIT=$(git rev-parse --short HEAD)

if [ -n "$(git status --porcelain)" ]; then
    echo "Uncommitted changes: commit first, so the image matches a commit." >&2
    exit 1
fi

docker buildx build --platform "$PLATFORM" \
    --tag "$IMAGE:latest" --tag "$IMAGE:$COMMIT" \
    --push .
echo "Pushed $IMAGE:latest and $IMAGE:$COMMIT ($PLATFORM)"
