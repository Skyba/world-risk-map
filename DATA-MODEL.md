# Data model

## Worldwide snapshots (version 2)

`data/world-current.json` points to an immutable `data/world-snapshots/YYYY-MM-DD.json` manifest. Each of the 263 country/territory records independently references its overview geometry, optional country-map geometry at two zoom levels, ordinary places, city exceptions and source context. TopoJSON areas and GeoJSON points use the same SHA-256 object stores described below. Unchanged objects are reused. The earlier seven-country experiment remains under `data/snapshots/`; it is not presented as a historical world assessment.

Geometry provenance and advice provenance are independent fields. For example, a territory may have colour coverage in the French world overview and a UK fallback advice page. The interface explicitly attributes both. UK native alert flags remain UK flags: an empty alert list does not imply a French green rating. Dark plum `#49364f` displays `closed_to_civilians`; it is a restriction, not an extra ordinal risk category.

The world geometry is fitted against equirectangular, Miller and Gall stereographic candidates. Gall stereographic gives the best fit for the current source. Coordinates are transformed from the source image, colour polygons are simplified as shared coverage, and their edges are clipped to Natural Earth country boundaries. The 90% land-mask IoU gate prevents some major layout/projection failures but cannot certify local risk boundaries. Source size, source hash, map date, fit parameters, coverage ratios and limitations are retained privately. The first world map has a 92.48% land-mask IoU; geometric validity is a separate test.

Metropolitan France, French Guiana, Guadeloupe, Martinique, Réunion and Mayotte have distinct display/source records, split from Natural Earth's grouped geometry without changing coastlines. Large countries with outlying islands zoom to their largest land component. This is a display choice, not a claim that outlying areas share the mainland's advice. Unclassified regions stay unclassified.

Advice objects retain provider, URL, page title, update date, native warning flags where available and a short verbatim country-level excerpt with source language and topics. Excerpts are not generated causal explanations for individual zones. New snapshots keep verification timestamps, raw-page fingerprints and fetch errors in the monthly manifest rather than stable context objects. Earlier objects containing those fields remain readable. Failed refreshes retain the last successful verification date.

A comparison distinguishes new coverage, changed geometry, changed provider and changed advice content. It does not label a changed extraction or a web-page refresh as worsening security. Snapshot selection shows the data actually recorded on that date. No earlier world snapshot is fabricated; the initial comparison control is disabled. A future spatial risk-change layer will need editorial checks for alignment changes.

The browser loads a shared world overview and major cities first. Country detail and smaller city points load as the user zooms; the full search index loads when searching. Shareable URL fragments retain snapshot, country, zoom, centre, zone or city. They do not invoke a server or publish the local preview. The current incident array is empty; optional incident records remain a future editorial feature, described below.

## Retained seven-country model (version 1)

Area geometry is quantized TopoJSON with shared arcs. Cities are ordinary point GeoJSON because most of their content is attributes and points do not benefit from shared boundary arcs. Country metadata is stored once in a snapshot, separately from geometry. The quantization grid is 100,000,000 positions per axis; the exporter verifies attribute preservation, feature counts, validity and a maximum coordinate displacement of 0.00001 degrees against the input. This tolerance concerns serialization only, not advisory accuracy.

```text
data/
  current.json                    # pointer to one dated manifest
  snapshots/YYYY-MM-DD.json        # immutable metadata + object references
  objects/<sha256>.json            # public-domain or cleared geometry
private/                          # ignored by Git
  objects/<sha256>.json            # uncleared candidate geometry
  maps/                           # raw inputs, control points and overrides
  media/                          # preview images
  source-cache/<sha256>.jpg        # downloaded evidence, once per content hash
  updates/YYYY-MM-DD.json          # source check reports
  import/YYYY-MM-DD/               # staged candidates and review metadata
  extraction/                     # reproducible intermediate outputs
```

A snapshot references objects by SHA-256, scope and byte length. Identical content has the same path across all months, so a no-change month adds only a small manifest. A changed country adds its changed object(s); world boundaries and ordinary city points are not duplicated. JSON remains inspectable and Git can compress it. Generated HTML, previews, raster evidence, virtual environments and compressed build archives are not tracked. Do not commit a SQLite database or a full duplicate world raster every month.

Country records carry ISO code; page/image URLs; image checksum; source map date; page update date when known; actual retrieval/check date; rights status and evidence; geometry review status and review date; separate overview/detail geometry references; optional city exceptions; and an optional context record. Source-only countries have no geometry references. Risk categories remain `green`, `yellow`, `orange`, `red`; `closed_to_civilians` is an independent restriction drawn solid dark plum. The visual dark plum fill must never be treated as a fifth ordinal risk score.

The current `zone_id` is a component identifier within a source snapshot, shared between zoom levels. It is not a permanent region identity across changed source maps. Month-to-month comparison should compare country objects and spatial coverage, not assume that a reused component number identifies the same place.

## Optional context, not yet populated

A short “Why this warning?” panel can be attached to a country or a specifically reviewed zone. Prefer two sentences, up to three reason tags, a review date and a primary source link. Use `armed_conflict`, `kidnapping`, `crime`, `arbitrary_detention` or `restricted_access` where supported. A security warning does not necessarily arise from a war. Do not generate a zone-specific causal claim merely from its colour or its country's general history.

```json
{
  "scope": {"country": "ISO3", "snapshot": "YYYY-MM-DD", "zone_id": null},
  "summary": "A brief, reviewed explanation of the warning.",
  "reason_tags": [],
  "source_urls": [],
  "reviewed_at": null
}
```

## Optional incidents, not yet populated

Use an explicitly incomplete, off-by-default layer of publicly documented incidents involving French nationals. A small fixed red spark/diamond icon is preferable to an animated emoji; cluster at low zoom and let users filter by event type/date. It is a set of reported cases, not a complete count, a real-time alert feed or a traveller mortality rate. More recorded incidents can reflect media coverage and travel volume. Absence of markers does not establish safety.

Separate a death, disappearance, abduction and arbitrary detention. Keep event date, date precision, last verified status, country, location precision, source links and corrections. State involvement requires its own attributed evidence field: `confirmed`, `alleged`, `disputed` or `unknown`, with the named source making that attribution. Do not infer state responsibility from location, nationality or a red advisory colour. Use an authoritative primary record where available, otherwise corroborated reputable reporting and a review; preserve uncertainty. Do not publish nonpublic hostage locations or invent precise coordinates from a country-level report. Include public personal names only when needed and supported by the cited public reporting.

```json
{
  "id": "stable-public-case-id",
  "event_type": "disappearance",
  "occurred_at": null,
  "date_precision": "unknown",
  "nationalities": ["FR"],
  "country": "ISO3",
  "location": null,
  "location_precision": "country",
  "state_involvement": {"status": "unknown", "attributed_to_source": null},
  "case_status": "unresolved",
  "summary": "",
  "sources": [],
  "verified_at": null,
  "corrections": [],
  "review_status": "candidate"
}
```

France Diplomatie describes consular handling of deaths, disappearances and hostage cases but does not provide a comprehensive public geocoded register on the pages reviewed. Its disappearance guidance explains that some information cannot be made public. General conflict-event datasets are a different product and do not solve the nationality/attribution/completeness problem. Review data redistribution terms before adding a provider.

References: [TopoJSON specification](https://github.com/topojson/topojson-specification), [sensitive individual cases](https://www.diplomatie.gouv.fr/fr/le-ministere-en-action/accompagner-les-ressortissants-francais/le-suivi-des-affaires-individuelles-sensibles), [disappearance guidance](https://www.diplomatie.gouv.fr/fr/services-aux-francaises-et-aux-francais/assistance-et-securite/disparitions-inquietantes), [ACLED codebook](https://acleddata.com/methodology/acled-codebook), [ACLED usage terms](https://acleddata.com/contentusage), [UCDP datasets](https://ucdp.uu.se/downloads/).
