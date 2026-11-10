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
- **E10 selskapshendelser og KOG** (845236d): børsmeldingene leses for emisjon, splitt, fisjon, navn/ticker,
  avnotering og nye noteringer; KOG 15. apr. 2026 i `drop_returns`.
- **E12 norsk tallformat** (15dce57): `dashboard/tall.py`, siste pass i `page()`.
- **E13–E15 visuelt, språk og røyktest** (eb788ac): én aksentfarge, tabelljustering, «I dag» på norsk,
  `tests/test_royk_browser.py`.
- **E16 noterte kurser** (4513a57): dagsendring og 12 m lav/høy.
- **E17 skjemaflyt** (7e95e61): riktig fane ved feil, bekreftelse fra loggen.
- **E18 kildekontroll og I44** (a63d48d).
- **Rapport:** `docs/forbedring/rapport.md` (kopi i `Pareto Equity Research/forbedring-2026-11-10/rapport.md`).
  Etter-bilder i `forbedring-2026-11-10/etter`. Hele testsettet: 618 grønne.

## Pågår
- (ingenting)

## Neste (hvis en ny økt fortsetter)
- De 49 åpne funnene om tall og logikk i `funn.md` (vedlegget, status «åpen»): start med #8, #14, #45, #59, #60.
- Ytelse: første visning etter oppstart (#84, #94, #95, N1), laste-indikator.
- Ett Plotly-tema, hover med kilde og tid på fellessidene, norske feilmeldinger i skjemaene.
- Typesjekk, CSRF (#119), unntak som svelges (#120).

## Viktig før sammenslåing
- E9 endrer den justerte historikken for aksjer med utbytte i USD og DKK første gang `oq record` kjøres.
  Papirkontoene leser samme lager.
- Skriptene i `scripts/` gjelder først når grenen er slått sammen: oppgaven kjører skriptene i hovedmappen.
