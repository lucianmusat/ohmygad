#!/usr/bin/env bash
set -euo pipefail

IMAGE_DEFAULT="lucianmusat/ohmygad"
PLATFORM_DEFAULT="linux/amd64"
BUILDER_NAME_DEFAULT="amd64builder"

usage() {
  cat <<'EOF'
Usage:
  ./build.sh <tag> [--image <name>] [--platform <platform>] [--latest] [--no-push] [--builder <name>]

Examples:
  ./build.sh 1.1.0
  ./build.sh 1.1.0 --latest
  ./build.sh 1.1.0 --image lucianmusat/ohmygad --platform linux/amd64
  ./build.sh 1.1.0 --no-push   # builds & loads locally

Notes:
- Refuses to run unless host arch is x86_64 (so you don't accidentally run it on Raspberry Pi armv7).
- Uses docker buildx and a dedicated builder container.
EOF
}

TAG=""
IMAGE="$IMAGE_DEFAULT"
PLATFORM="$PLATFORM_DEFAULT"
BUILDER_NAME="$BUILDER_NAME_DEFAULT"
PUSH=1
TAG_LATEST=0

if [[ ${1:-} == "" || ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

TAG="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE="$2"; shift 2 ;;
    --platform)
      PLATFORM="$2"; shift 2 ;;
    --builder)
      BUILDER_NAME="$2"; shift 2 ;;
    --latest)
      TAG_LATEST=1; shift ;;
    --no-push)
      PUSH=0; shift ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

ARCH="$(uname -m)"
if [[ "$ARCH" != "x86_64" ]]; then
  echo "Refusing to run: host architecture is '$ARCH' (expected x86_64)." >&2
  echo "Run this script on kottos (x86_64), not on the Raspberry Pi (armv7)." >&2
  exit 3
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found in PATH." >&2
  exit 4
fi

# Ensure buildx is available
if ! docker buildx version >/dev/null 2>&1; then
  echo "docker buildx not available. Ensure Docker Buildx is installed/enabled." >&2
  exit 5
fi

# Ensure builder exists and is selected
if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER_NAME" --driver docker-container --use >/dev/null
else
  docker buildx use "$BUILDER_NAME" >/dev/null
fi

# Warm up builder
docker buildx inspect --bootstrap >/dev/null

TAGS=("-t" "${IMAGE}:${TAG}")
if [[ "$TAG_LATEST" -eq 1 ]]; then
  TAGS+=("-t" "${IMAGE}:latest")
fi

if [[ "$PUSH" -eq 1 ]]; then
  docker buildx build --platform "$PLATFORM" "${TAGS[@]}" --push .
else
  # --load only supports single-platform builds; safe here.
  docker buildx build --platform "$PLATFORM" "${TAGS[@]}" --load .
fi

echo "Done: ${IMAGE}:${TAG} (platform: ${PLATFORM})"
