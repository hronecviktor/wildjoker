#!/bin/sh
# Build the image and push it to Docker Hub, tagged :latest and with the
# commit it was built from. Log in first with `docker login`.
#
#   DOCKERHUB_USER=hronecviktor deploy/publish.sh
#
# PLATFORM is the server's architecture: linux/arm64 by default (the VPS is
# ARM). Building it on an x86 machine needs QEMU emulation for buildx, once
# per boot: docker run --privileged --rm tonistiigi/binfmt --install arm64
set -eu
cd "$(dirname "$0")/.."

: "${DOCKERHUB_USER:?set DOCKERHUB_USER to your Docker Hub account}"
IMAGE=${IMAGE:-$DOCKERHUB_USER/wildjoker}
PLATFORM=${PLATFORM:-linux/arm64}
COMMIT=$(git rev-parse --short HEAD)

if [ -n "$(git status --porcelain)" ]; then
    echo "Uncommitted changes: commit first, so the image matches a commit." >&2
    exit 1
fi

docker buildx build --platform "$PLATFORM" \
    --tag "$IMAGE:latest" --tag "$IMAGE:$COMMIT" \
    --push .
echo "Pushed $IMAGE:latest and $IMAGE:$COMMIT ($PLATFORM)"
