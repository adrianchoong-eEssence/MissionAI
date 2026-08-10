#!/usr/bin/env bash
set -euo pipefail

source_dir="$1"
destination="$2"
mkdir -p "$destination"

for source_image in "$source_dir"/*.HEIC; do
  image_name="$(basename "$source_image" .HEIC)"
  converted_image="$destination/${image_name}-full.jpg"
  heif-convert "$source_image" "$converted_image" >/dev/null
  sips -Z 720 "$converted_image" \
    --out "$destination/${image_name}.jpg" >/dev/null
  rm "$converted_image"
done
