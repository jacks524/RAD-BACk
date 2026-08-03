#!/usr/bin/env bash
# Demarre les services de donnees embarques utilises par la stack Docker locale.
set -euo pipefail

mkdir -p /data/redis /data/minio
redis-server --dir /data/redis --appendonly yes &
minio server /data/minio --address ":9000" --console-address ":9001" &
wait -n
