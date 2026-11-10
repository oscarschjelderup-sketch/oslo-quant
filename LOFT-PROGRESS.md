# LOFT-PROGRESS – løft av dashbordet (10. nov. 2026)

Grenen er `loft-2026-11-10` (worktree `Private prosjekter/oslo-quant-loft`), laget fra main 86549f7. Ingenting er pushet
eller slått sammen: Oscar ser på det først. Valgene står i `DECISIONS.md` D65–D69.

- Testhjem og skript ligger i øktens scratchpad. `loft.ps1` starter grenen på port 8068 mot testhjemmet (kopierte
  kurser, fiktiv research book). Aldri mot det ekte hjemmet.
- Før- og etter-bilder: `Pareto Equity Research/loft-2026-11-10/for` og `/etter`.
- Research: `docs/loft/research.md`. Desk-avspillingen: `docs/loft/desk-replay.md`.

## Ferdig
- **CI-rettelse** (f8d7db3): Chrome på CI-maskinen sier hvorfor den ikke starter, og får 45 s. Ikke pushet, så CI på
  main er fortsatt rød etter PR #12.
- **Runde 1, «Prisen krever»** (244e8cd): `.info`-kollisjonen som klippet alle blå merkelapper, faste kolonner,
  `FIT_SCRIPT` (ingen tabell forlater kortet sitt), norske gruppenavn.
- **Runde 2, makro og meny** (949e90f): feeden `macro`, `macro.py`, `macropage.py`, `static/minichart.js`, `/makro`,
  makrostripe på «I dag», kortet «Makro som betyr noe for denne aksjen», menyen med «Mer».
- **Runde 3, nyheter** (9c5841b): `news.py`, «Nyheter som betyr noe», nyheter dag for dag på aksjesiden, M-merker
  på kursgrafen, drivere og nyheter per sektor.
- **Runde 4, porteføljesiden** (0335841): `fundchart.py`.
  Etter gjennomsyn av etter-bildene: NAV-grafene fikk samme farger og tema, og fondsnotatene står på norsk.
- **Runde 5, desken** (63f3fa5): utløservekt, filterregel for svake utløsere, makro som inndata, «klar» via tung
  utløser, tak på fem, felles kildeliste, `desk.replay`.

## Ikke gjort
- Makrokalender med tallslipp (KPI, BNP, utenlandske sentralbanker): trenger en kilde med avklarte vilkår.
- Rentebane fra Norges Bank: finnes bare som regneark med ny adresse for hver rapport.
- Måling av om en utløser er verdt noe (D69): trenger vurderinger å måle på.
- Ett Plotly-tema for de øvrige grafene på aksjesiden (multipler, regnskap).
- Kraftprisen og TTF-gass har kort historikk og bygges opp dag for dag.

## Før sammenslåing
- CI-rettelsen bør pushes og kjøres i en PR: den er ikke bekreftet på Linux.
- Kveldsoppgaven henter den nye feeden `macro` av seg selv (den går gjennom `feeds.refresh`).
- Desken får nye terskler. Den første kjøringen etter sammenslåing bruker dem.
