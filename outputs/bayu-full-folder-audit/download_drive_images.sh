#!/usr/bin/env bash
set -euo pipefail

manifest="$1"
destination="$2"
mkdir -p "$destination"

tail -n +2 "$manifest" | while IFS=$'\t' read -r file_id filename; do
  curl --fail --silent --show-error -L \
    "https://drive.google.com/uc?export=download&id=${file_id}" \
    -o "${destination}/${filename}"
done
