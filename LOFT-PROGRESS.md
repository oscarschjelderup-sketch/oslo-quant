# LOFT-PROGRESS – løft av dashbordet (startet 10. nov. 2026)

Grenen er `loft-2026-11-10` (worktree `Private prosjekter/oslo-quant-loft`), laget fra main 86549f7. Ingenting er pushet
eller slått sammen: Oscar ser på det først. Testhjem og skript ligger i øktens scratchpad (`loft.ps1` starter grenen
på port 8068 mot testhjemmet). Før-bilder: `Pareto Equity Research/loft-2026-11-10/for`.

## Ferdig
- **CI-rettelse** (f8d7db3): Chrome på CI-maskinen sier hvorfor den ikke starter. Ikke pushet; main er rød i CI.
- **Runde 1, «Prisen krever»** (244e8cd): `.info`-kollisjonen som klippet alle blå merkelapper, faste kolonner,
  `FIT_SCRIPT`, norske gruppenavn, tester for klippede merkelapper og for brede tabeller.
- **Runde 2, makro** (949e90f): `macro.py`, `macropage.py`, `static/minichart.js`, feeden `macro`, `/makro`,
  makrostripe på «I dag», kortet «Makro som betyr noe for denne aksjen», menyen med «Mer».
- **Runde 3, nyheter**: `news.py` (vekt per melding), «Nyheter som betyr noe» på «I dag», nyheter dag for dag på
  aksjesiden, M-merker på kursgrafen, drivere og nyheter per sektor.

## Gjenstår
- Runde 4: porteføljesiden og CML-grafen (`funds.py`, `frontier_chart` i `render.py`).
- Runde 5: desken (`desk.py`): utløsere fra nyheter og hendelser, makro som inndata, terskler, felles kildeliste.
- DECISIONS D65–D69, etter-bilder, hele testsettet, rapport til Oscar.

## Research
`scratchpad/research_makro_nyheter.md` (mønstre fra Bloomberg, Koyfin, TradingView m.fl. og gratis kilder med vilkår).
