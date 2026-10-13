# Trading Goats page

Live at https://oscarschjelderup-sketch.github.io/oslo-quant/ (GitHub Pages, deployed by `.github/workflows/goats-site.yml`)
and as a claude.ai artifact.

`trading-goats.html` is the page behind the Trading Goats artifact (three paper accounts as the three billy goats
Gruff, a troll reviewing their books). It is published as a claude.ai Artifact with the `db` capability and reads
these documents from the artifact's store:

| document | written by |
|---|---|
| `meta/state`, `goats/<id>`, `herd/latest`, `stream/latest`, `gate/latest` | `oq goats --split DIR` (one JSON file each) |
| `troll/log` | the reviewer (Claude), `{rewrites, reviewed_at, entries: [{t, kind, goat?, text}]}` |

Entry kinds: `intro`, `verdict`, `handsoff`, `rewrite`, `note`. Times in the export are Oslo wall-clock without a
zone; `generated_at` and the troll's `t` carry a `Z`. The page never writes.
