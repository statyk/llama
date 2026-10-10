#!/bin/sh
# Run transmitter's tests on hugo's versions: Debian 12 = Python 3.11 + ffmpeg 5.1.
# Usage: packages/transmitter/scripts/test-in-debian12.sh [extra pytest args]
set -eu
repo=$(cd "$(dirname "$0")/../../.." && pwd)
exec docker run --rm -v "$repo:/src:ro" debian:12 sh -euc '
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv ffmpeg >/dev/null
  ffmpeg -version | head -1
  python3 --version
  mkdir /work
  tar -C /src --exclude="./.venv*" --exclude=./.superpowers --exclude=./.git --exclude=./.claude \
      --exclude="*/node_modules" --exclude="*/__pycache__" -cf - . | tar -C /work -xf -
  python3 -m venv /venv
  /venv/bin/pip install -q -e "/work/packages/transmitter[dev]"
  cd /work
  /venv/bin/python -m pytest -q -p no:cacheprovider packages/transmitter/tests_transmitter "$@"
' sh "$@"
