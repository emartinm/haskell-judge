#!/bin/sh
# Builds the CodeMirror 6 editor into a single static file. Node is not needed on
# the host: it runs in the official node image. Only needed to update the editor;
# the generated file is in the repository.
set -eu
cd "$(dirname "$0")"
OUT=../lhaskell/judge/static/judge/js/haskell-editor.min.js
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/editor" -w /editor node:22-slim sh -c \
  "npm install --no-audit --no-fund --silent && npx esbuild editor.js --bundle --minify --format=iife \
   --global-name=HaskellEditor --legal-comments=none --outfile=haskell-editor.min.js"
mv haskell-editor.min.js "$OUT"
rm -rf node_modules
ls -l "$OUT"
