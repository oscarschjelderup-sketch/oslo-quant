# PROGRESS – forbedring av dashbordet (startet 10. nov. 2026)

Grenen er `forbedring-2026-11-10` (worktree `Private prosjekter/oslo-quant-forbedring`). Den bygger på
`natt-2026-11-10` (kursgrafen, D59) og har med `docs/feilsok/funn.md`. Ingenting slås sammen og ingenting pushes.

- Funn: `docs/forbedring/funn.md`. Endringer skrives i `docs/forbedring/endringer.md` før de gjøres.
- Valg: `DECISIONS.md` (D60 og utover).
- Testhjem: scratchpad `testhjem` (kopi av lageret, fiktiv book og logg). Server: `run_natt.py SRC PORT`, port 8067.
- Tester: `PYTHONPATH=$PWD/src ../oslo-quant/.venv/Scripts/python.exe -m pytest -q`.

## Ferdig
- **Fase 1: revisjon.** 105 sider gått gjennom i nettleser, loggene fra 22 kjøringer talt opp, hver datakilde
  vurdert. 37 nye funn, 105 åpne fra 9. nov. Før-bilder i `Pareto Equity Research/forbedring-2026-11-10/for`.

## Pågår
- Fase 2: krasj og feil tall.

## Neste
- Fase 3: datainnhenting (D1–D14).
- Fase 4: felles visuelt system.
- Fase 5: flyter.
- Røyktest i CI, kildefeil-test, etter-bilder og rapport.
