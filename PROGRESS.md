# PROGRESS – forbedring av dashbordet (startet 10. nov. 2026)

Grenen er `forbedring-2026-11-10` (worktree `Private prosjekter/oslo-quant-forbedring`). Den bygger på
`natt-2026-11-10` (kursgrafen, D59) og har med `docs/feilsok/funn.md`. Ingenting slås sammen og ingenting pushes.

- Funn: `docs/forbedring/funn.md`. Endringer skrives i `docs/forbedring/endringer.md` før de gjøres.
- Valg: `DECISIONS.md` (D60 og utover).
- Testhjem: scratchpad `testhjem` (kopi av lageret, fiktiv book og logg). Server: `run_natt.py SRC PORT`, port 8067.
- Tester: `PYTHONPATH=$PWD/src ../oslo-quant/.venv/Scripts/python.exe -m pytest -q`.

## Ferdig
- **Fase 1: revisjon.** 105 sider gått gjennom i nettleser, loggene fra 22 kjøringer talt opp, hver datakilde
  vurdert. 36 nye funn, 105 åpne fra 9. nov. Før-bilder i `Pareto Equity Research/forbedring-2026-11-10/for`.
- **E1–E3 krasj** (19a4c41): modellfil og loggrad kan ikke ta ned en side, tomt lager, norske feilsider.
- **E4–E6 datakilder** (76d7fc6): `dashboard/sources.py`, kjørelogg, varsel på «I dag», tabellen «Kilder» på
  Datahelse, skriptene henter noterte kurser og regnskap, nye forsøk, færre kall.
- **E7–E8 logikk** (f9817fb): loggen avviser NaN og uendelig, skjemaene leser desimalkomma, oppdateringsskjemaet
  kaster ikke det som er skrevet, utfallsodds uten simulering tar ikke stilling.
- **E9 utbytter i fremmed valuta** (cc7a2b2): renseregel 0. Kontrollert mot ekte Yahoo-historikk uten å skrive.
- **E10 selskapshendelser og KOG**: børsmeldingene leses for emisjon, splitt, fisjon, navn/ticker, avnotering og
  nye noteringer; KOG 15. apr. 2026 i `drop_returns`.

## Pågår
- E11: dagsendring og 12 m lav/høy på noterte kurser (#30, #31).

## Neste
- Fase 3 rest: kontroll mellom kilder (D12), nye kilder vurdert (fase 3 punkt 5).
- Fase 4: felles visuelt system (norsk tallformat, språk, tabeller, graftema).
- Fase 5: flyter (#86, #87, #89, #90, #114).
- Røyktest i CI, etter-bilder og rapport.

## Viktig før sammenslåing
- E9 endrer den justerte historikken for aksjer med utbytte i USD og DKK første gang `oq record` kjøres.
  Papirkontoene leser samme lager.
- Skriptene i `scripts/` gjelder først når grenen er slått sammen: oppgaven kjører skriptene i hovedmappen.
