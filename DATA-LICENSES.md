# Data and dependency rights

The root MIT licence applies to this project's software and authored documentation. It does not relicense data, maps, imagery, fonts or third-party libraries.

| Component | Position as checked 6 October 2026 | Action before publication |
| --- | --- | --- |
| France Diplomatie general website content | The legal notice offers Licence Ouverte 2.0 except for specified third-party rights, with source/date attribution and no misleading reuse. | Keep the source link, source update date and transformation notice. Check each map's own markings. |
| World security image dated 25 September 2026 | The image also visibly carries CC BY-NC-ND. | Worldwide extracted geometry remains private pending permission clarification. |
| Colombia security image dated 27 May 2026 | The image visibly carries CC BY-NC-ND; the badge does not specify a version. | Clarify permission for the traced, simplified and recoloured derivative or obtain explicitly open geographic data. Current candidate shapes remain private. |
| Other advisory maps | No individual publication clearance has been recorded. | Review map-specific rights rather than assuming the general website terms settle every asset. |
| UK FCDO text via GOV.UK Content API | GOV.UK offers its content under Open Government Licence v3.0 except where otherwise stated. | Retain source/provider attribution; do not imply UK endorsement or convert native flags into French categories. No UK map imagery is bundled. |
| Natural Earth boundaries and populated places | Public domain. | Credit is retained even though the source says it is not required. |
| MapLibre GL JS 5.12.0 (world) and 5.6.0 (legacy sample) | BSD-3-Clause and retained upstream notices. | Preserve its notices if bundling it; the current page uses its published CDN build. |
| Python topojson | Its own upstream BSD-3-Clause licence. | Retain upstream notices when distributing the dependency. |
| Labels/glyphs and other Python dependencies | Separate upstream terms. | Audit and retain their licences if vendoring production assets. They are not relicensed by our MIT file. |

The conflicting map-specific and general website notices are a publication-readiness issue, not a finding that all factual risk assessments are copyright-protected or that every format conversion is a prohibited adaptation. Our current process does more than change file format, so a permission clarification or explicitly open source dataset is the cleanest route.

Sources:

- [France Diplomatie legal notice](https://www.diplomatie.gouv.fr/fr/mentions-legales)
- [Colombia source image showing the badge](https://www.diplomatie.gouv.fr/files/files/cav/colombie/20260527_colombie-fcv.jpg)
- [Creative Commons explanation of BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) — explanatory reference; the map's badge does not identify this version.
- [Natural Earth terms](https://www.naturalearthdata.com/about/terms-of-use/)
- [MapLibre 5.6.0 licence](https://github.com/maplibre/maplibre-gl-js/blob/v5.6.0/LICENSE.txt)
- [Python topojson licence](https://github.com/mattijn/topojson/blob/main/LICENSE)

ACLED and similar event providers have separate redistribution/display terms. Access to a dataset does not automatically permit bundling its records in an open GitHub repository. No ACLED or UCDP event data is included here.

Worldwide sources: [French world map](https://www.diplomatie.gouv.fr/files/files/cav/_carte-vigilance-mondiale/20260925_fcv_monde.jpg), [GOV.UK terms](https://www.gov.uk/help/terms-conditions), [GOV.UK Content API](https://content-api.publishing.service.gov.uk/reference.html). French and UK safety excerpts are attributed source text; the project MIT licence does not relicense them.

The world viewer uses [MapLibre 5.12.0](https://github.com/maplibre/maplibre-gl-js/blob/v5.12.0/LICENSE.txt) for its documented viewport constraint callback, allowing a complete single-world view without cropping or duplicate continents.
