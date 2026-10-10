# World Risk Map

Static interactive travel-advice map. France Diplomatie is the primary source, with attributed UK FCDO fallbacks. The canonical checkout is `/Users/basilev/code/world-risk-map`; the original Codex output directory links here for local preview compatibility.

## Development

- Install `requirements.txt` and run `python -m unittest discover -s tests`.
- The worldwide viewer lives in `src/world.html`, `src/world.css` and `src/world.js`. Build it with `python scripts/world.py build --preview` and serve `preview/` locally.
- `scripts/world.py update` stages a manual source refresh. Snapshot history is immutable; create a new dated snapshot after checking changes.
- Keep country boundaries separate from risk zones. Selection outlines the country, while clicked zones supply advice details. Capitals are squares; ordinary city markers do not carry a risk rating.

## Data and publication

- Keep `private/`, `preview/`, `dist/`, source maps and credentials out of Git. Read `DATA-LICENSES.md` before changing redistribution scope.
- MIT covers authored software and documentation, not third-party data. Do not mark geometry rights as cleared or geographic review as approved without recorded evidence.
- The owner authorized public distribution of the full candidate map on 9 October 2026. `data/publication.json` records this decision for the exact snapshot; it does not replace historical rights/review metadata or claim a separate ministry permission. Build the authorized release with `python scripts/world.py build`.
- This is an independent interpretation of dated government advice. Preserve source attribution, dates, missing-coverage distinctions and direct official links.
- GitHub repository: `https://github.com/Skyba/world-risk-map`. Requested website: `https://riskmap.basilev.com`.
