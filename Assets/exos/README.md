# EXOS production assets

The SVG files are the editable masters. PNGs are transparent production exports.

- Horizontal light/dark: `2400 × 720`
- Vertical master: `1800 × 2000`
- Icon master: `1024 × 1024`
- Desktop icon: `512 × 512`
- Mobile icon: `192 × 192`
- Favicon: `32 × 32`

Run `scripts/render_exos_assets.mjs` after changing an SVG master. The render is
deterministic and uses headless Chrome so all PNG exports stay aligned.

The `imagegen-brand-exploration.png` file records the AI-assisted concept pass.
Production surfaces use the controlled SVG masters, not the exploratory raster.
