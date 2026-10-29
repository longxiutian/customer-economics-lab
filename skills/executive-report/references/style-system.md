# Portable report style system

This is the report-relevant adaptation of Longxiu Tian's maintained `build-longxiu-research-briefs` system. It contains no private research prose, source figures or private file dependencies. The original visual package is included unchanged in `templates/longxiu-research-brief.sty`; the repository's license covers the author's contributed report assets.

## Fixed tokens

| Component | Specification |
|---|---|
| Page | US Letter portrait, 612 x 792 pt |
| Margins | Left/right 0.72 in; top 0.58 in; bottom 0.62 in |
| Typeface | Source Sans, required |
| Body | 9 pt, 11 pt leading |
| Main page title | 18 pt, 20.5 pt leading |
| Optional cover title | 24 pt, 27 pt leading |
| Main ink | `#202521` |
| Muted text | `#5A625D` |
| Forest green | `#185A46` |
| Ochre | `#8A5E0E` |
| Ochre rule | `#B57A19` |
| Border | `#C8CECA` |
| Pale neutral | `#F2F5F2` |
| Pale green | `#E5F2EC` |
| Pale gold | `#FFF1D5` |

Use thin rules, square corners, restrained boxes and deliberate white space. The green identifies structure and primary evidence; ochre identifies a boundary, comparison or secondary emphasis. Color must not be the only way to distinguish observations, forecasts and experiments.

The detailed source-schema appendix is the one deliberate paper-size exception: an A3 landscape foldout preserves the complete table relationships without shrinking the whole report. Executive, model and UCV pages remain US Letter portrait. The report wrapper owns this exception; the upstream style package remains unchanged.

## Executive-page anatomy

Use a compact kicker, a concrete title, a short scope line and readable report body. Present business context and an evidence-supported recommendation first. Then develop observed diagnosis, model explanation, predicted outcomes and action. Put methods, parameter estimates, UCV documentation and reproducibility evidence in appendices.

This is a report, not a slide deck. The upstream one-page-per-paper and radar-chart conventions are intentionally not applied: no paper portfolio or comparative methodological radar is being reported. The actual visual source remains intact; only the report-specific wrapper changes semantic labels.

## Portable build boundary

The only style files needed by the generated TeX live in this repository and are copied into its output folder. A compatible TeX runtime must resolve `sourcesans.sty`; that dependency is declared in the main setup instructions. The build manifest records upstream style version/hash, wrapper hash, template hash, input evidence hashes and compiler identity. Existing builds retain their pinned style; an upstream personal-skill change must not silently alter them.

Render and visually inspect all pages after changes. Do not hide layout defects by rasterizing text, shrinking the whole document, removing uncertainty statements, or replacing Source Sans.
