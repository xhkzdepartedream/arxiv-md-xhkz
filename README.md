# arxiv-md

Good enough™ LaTeX to Markdown converter, optimized on hundreds of arXiv
papers from 2016 to 2026.

## CLI

```console
arxiv-to-md 2506.04225 --outdir ./out
arxiv-to-md --top-k 3 "world consistent video diffusion" --outdir ./out
tex-to-md paper.tex --outdir ./out
```

Converted papers land in `<outdir>/<arxiv_id>/document.md` with a
`conversion.json` sidecar and an `images/` directory.

## Options

- `--keep-archive` / `--keep-source` — keep the downloaded source bundle /
  extracted source tree.
- `--json` — emit a machine-readable envelope on stdout.
- `--no-equation-appendix` — omit the verbatim display-math appendix appended
  to `document.md`.
- `--asset-mode rasterize|copy|skip` — how PDF/JPEG figure assets are handled
  (`rasterize` needs the `assets` extra).
- `--strict` — fail on conversion warnings.

## Assets

Optional rasterization support (PDF pages → PNG):

```console
uv tool install --from . arxiv-md --extra assets
```
