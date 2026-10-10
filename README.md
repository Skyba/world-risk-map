# World Risk Map

Independent visualisation of government travel advice. France Diplomatie is the primary source; clearly labelled UK FCDO guidance fills some missing advice coverage. Source repository: [Skyba/world-risk-map](https://github.com/Skyba/world-risk-map). Requested website: `riskmap.basilev.com`.

The worldwide preview contains 263 selectable country/territory records, world-map colour geometry in 194 of them, six higher-detail country layers and 7,342 named places. Advice is linked for 202 records through France Diplomatie and another 34 through UK FCDO. These are geographic records, not counts of sovereign states or distinct source pages. The French catalogue supplied 194 security pages; some pages serve multiple destinations. Twenty-seven small territories, dependencies or disputed areas have no matched dedicated advice page.

This is a candidate worldwide overview, not a completed high-resolution advisory dataset. Only 180 records have more than half their Natural Earth land area covered by the world extraction. Unresolved islands, source-frame gaps and unmapped areas remain visibly distinct. Russia now has world-overview geometry; its country-map conversion remains withheld. The world source image is dated 25 September 2026; the first worldwide snapshot is 7 October 2026 UTC. Country pages may be more recent than the world image.

## Run the local preview

The current local project includes local input data. The public source-only checkout excludes the extracted geometry objects, so a fresh checkout must be supplied with those inputs before building the complete map. The public website serves the authorized display geometry.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/world.py validate
.venv/bin/python scripts/world.py build --preview
.venv/bin/python -m http.server 8764 --bind 127.0.0.1
```

Open `/preview/`. The project is static: no application backend, login, credentials or paid map API is required. MapLibre 5.12.0 and glyphs currently load from public CDNs; vendor suitable licensed assets before a dependable production release.

The map supports country, territory and city search; square capitals; zoom-dependent city labels; solid dark plum civilian restrictions; thin country borders; country-outline selection with clickable zone advice; direct official links; short country-level source excerpts; source/map/snapshot dates; shareable URL views; snapshot selection; and changed-source/geometry highlighting. The initial world snapshot has no earlier world comparison, so the change control is disabled with an explanation. There is no invented historical advice and no incident dataset.

France's overseas departments are split from metropolitan France for selection and source matching. UK advice uses its own native alert flags. Absence of a UK “against travel” flag never becomes a French green rating. Blue-grey denotes other-government advice without French zone geometry; it is not a risk severity. Short excerpts remain in the source language, are labelled as country-level context and do not claim to explain every coloured subregion.

## Manual monthly update

Run this manually when ready; it stages source changes and never publishes or changes the active snapshot:

```sh
.venv/bin/python -m pip install -r requirements-extraction.txt
.venv/bin/python scripts/world.py update
```

The updater checks the French destination catalogue, country security pages, matched UK API pages, the official world image and the seven retained country images. It caches source evidence privately. An unchanged world image reuses the previous extraction; a changed image is fitted against candidate projections and rejected if land-mask alignment is below 90% intersection-over-union. This is an alignment diagnostic, not a boundary-accuracy certification. Failed checks retain the last successful advice with its old verification date and an error notice; they do not claim freshness.

Review the staged source changes, dates, overview fit, sub-country boundaries, small islands and special restrictions. A changed detailed country map is omitted from a new snapshot until it has been re-extracted and reviewed. The retained country pipeline is available for that work; update its image, URL, crop, control points and private overrides first:

```sh
.venv/bin/python pipeline/test_maps.py
.venv/bin/python pipeline/validate_expanded.py
.venv/bin/python pipeline/build_partition.py
.venv/bin/python pipeline/build_display.py
.venv/bin/python scripts/stage_extraction.py --date YYYY-MM-DD
.venv/bin/python scripts/manage.py snapshot --input private/import/YYYY-MM-DD --date YYYY-MM-DD
```

Then create the new worldwide snapshot and preview:

```sh
.venv/bin/python scripts/world.py snapshot --date YYYY-MM-DD
.venv/bin/python scripts/world.py validate
.venv/bin/python scripts/world.py build --preview
.venv/bin/python -m unittest discover -s tests
```

Snapshot dates are immutable. Changed inputs require a new date; historical records are not overwritten. Reusing an existing snapshot date is only valid when its complete content is identical. Creating a snapshot is an explicit local action, not publication or rights approval. Source-check timestamps and page fingerprints are separate from stable advice content in new snapshots, so routine rechecks do not duplicate unchanged text or claim a risk change. The first snapshot predates that metadata split and remains readable.

## Storage and performance

Geometry is stored as per-country, content-addressed TopoJSON objects. Monthly manifests point to unchanged objects. Cities, context and source metadata are separate from area geometry. A source-only ZIP excludes `private/`, generated previews, built deployment files, raw maps, environments and caches. See [DATA-MODEL.md](DATA-MODEL.md) and [storage-report.json](storage-report.json).

The browser initially loads the world overview, land, major cities and six lightweight country overviews. It fetches local city detail and the higher-detail country shapes as the user zooms. The complete city search index is fetched only when searching. The current viewer consumes decoded GeoJSON assets; TopoJSON saves repository storage, while lazy loading controls browser work. Future vector tiles should be driven by measured bottlenecks rather than required for this first world overview.

The build lightly rounds corners on shared edges between world-overview risk colours. Both neighbouring zones use the same curved edge. Country borders, coastlines, unmapped gaps and the six detailed country layers retain their geometry. The builder checks validity, overlaps, unchanged coverage and preservation of polygon components and holes, reducing the rounding if necessary. This is a display treatment applied during the build; immutable source snapshots and monthly advice comparisons are unchanged. Curves are precomputed, with no smoothing work during browser interaction.

## Publication status

The source code is public on [GitHub](https://github.com/Skyba/world-risk-map). On 9 October 2026 the project owner authorized distribution of the complete candidate map as a public beta. The decision in `data/publication.json` is bound to the exact snapshot hash; it does not claim separate ministry permission or completed geographic review. See [DATA-LICENSES.md](DATA-LICENSES.md) for source-specific terms. The MIT licence covers authored software and documentation, not third-party data. No recurring source-update job is scheduled.

Build the authorized snapshot for deployment:

```sh
.venv/bin/python scripts/world.py build
```

The generated `dist/` is the complete static deployment. Raw maps, local caches and original geometry objects stay under ignored directories and are not uploaded wholesale. The Sites project is recorded in `.openai/hosting.json`; its source and the public GitHub repository use the same Git commits. Deployment packages contain `dist/` and the hosting manifest. The intended custom domain is `riskmap.basilev.com`.

A new monthly snapshot requires a new recorded publication decision after reviewing the changes. Passing geometry tests alone does not authorize a different snapshot. Approximate boundaries, missing islands and disputed areas remain limitations of this beta; use the linked official advice when planning travel.
