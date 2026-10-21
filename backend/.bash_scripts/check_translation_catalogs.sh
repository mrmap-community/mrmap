#!/bin/sh
# Compare extracted messages without volatile metadata or source-only changes.
set -eu

catalog_tmp=$(mktemp -d)
trap 'rm -rf "$catalog_tmp"' 0
trap 'exit 1' 1 2 15

msgattrib --no-location --no-wrap --sort-output "$1" -o "$catalog_tmp/committed.po"
msgattrib --no-location --no-wrap --sort-output "$2" -o "$catalog_tmp/extracted.po"
sed '/^"POT-Creation-Date: /d' "$catalog_tmp/committed.po" > "$catalog_tmp/committed.normalized.po"
sed '/^"POT-Creation-Date: /d' "$catalog_tmp/extracted.po" > "$catalog_tmp/extracted.normalized.po"
diff -u "$catalog_tmp/committed.normalized.po" "$catalog_tmp/extracted.normalized.po"
