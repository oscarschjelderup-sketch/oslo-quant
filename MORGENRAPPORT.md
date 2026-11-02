# Morgenrapport – nattøkt 1.–2. november 2026

Gren `natt-2026-11-02` i worktree `oslo-quant-natt`. **Ingenting er slått sammen til main, ingenting er pushet.**
Main står på 705e431; Windows-oppgaven og dashbordet på 8060 kjører som før. Beslutningene står i DECISIONS.md D20–D29.
Revisjon: `docs/natt/revisjon.md`. Idéliste (43 skårede): `docs/natt/ideer.md`. Skjermbilder: `scratchpad/shots-natt/` (utenfor git).

## Bygget (full suite grønn for hver del)

| Del | Hva | Skjermbilde |
|---|---|---|
| A/A2 | Odds gjort ærlige: to-veis klynge-t, bootstrap-intervall, tre delperioder, overlevere, dominerende aksje, grad A–D; chips nøytrale uten A | `a2-sats.png` |
| B | Kalibrering: Brier, oppgitt-mot-realisert-plott, referansene OSEBX / «kursen står stille» / konsensus (konsensus krever kilde) | `b-kalibrering.png` |
| E | Før rapporten: «logg synet før rapporten»-punkt (14 d), `oq reports dryrun` på en PDF, kvittering når et kill-kriterium alt er utløst ved kjøp | `e-outlt.png` |
| F | Forsiden for et fem-minutters besøk: dagens dato + siste sluttkurs, utdatert-banner, nummerert liste med «gjør først», alt-klart-tilstand | `f-idag.png` |
| C | Datahelse-side + `oq data audit` (utbytter Yahoo mot NewsWeb) | `c-datahelse.png` |
| D | Kalender: selskapenes finanskalendere fra NewsWeb, research book, Norges Bank (kun 5. nov verifisert) | `d-kalender.png` |
| G | Boken samlet: felles kill-drivere, sektorkonsentrasjon, valgfritt tapstak per sektorgruppe | `g-idag.png` |
| H | Fjerde gradsjekk: to-veis placebo-bånd (200 trekk, fast seed) i oddsfilen og på signallinjen | `h-signal.png` |
| I | Syn eldre enn siste rapport: eget beslutningspunkt (45 d) og merke i kursmål-tabellen; erstatter «+10 %»-punktet for samme aksje | `i-idag.png` |

## Revisjonsfunn – også de ubehagelige

- **Overlevelsesskjevhet:** universet er dagens 64 aksjer. Likevektet ga +19,5 %/år mot OSEBX +11,6 %/år 2013–2026. Alle odds er målt mot *dette* universet; de sier ingenting om aksjer som forsvant.
- **Statistikken var feil i type:** t på månedssnitt overdrev. Med riktig klynging og intervall har **ingen 20-dagers kjøpssignal** et intervall som utelukker null etter kostnader. Det som står igjen er 60-dagers momentum (BO20/BO60 grad A, RiseCh B; z 3,6–4,1 mot placebo). Risikosiden er svakere enn docstringen påsto: BD60 ligger *innenfor* placebo-båndet (aksjene og månedene forklarer tallet, ikke dagen); bare Death cross 20 d (A) og Falling channel 60 d (C) står igjen.
- **Innsiderstudien er trukket tilbake som funn:** 60 d t gikk fra 2,41 til 0,72 med klynging; snittet bæres av to aksjer. Skrevet om i `docs/dashboard/insider-study.md`.
- **Periodeavhengighet:** risikosignalenes effekt er et 2010–15-resultat; siden 2016 måler ingen av familiene noe.
- **Yahoo mangler utbytter:** 29 ex-dividend-meldinger uten justering (MOWI 2015–17 ≈ 21 pp, WWI, AKER, KID, GSF, PROT, TGS). Falske risikosignaler den dagen og for lav totalavkastning. BORR har ingen Yahoo-kurser jan–nov 2025. OUTLT mangler i rå-tabellen.
- **SATS:** personalkost-kriteriet var brutt alt i basisåret – kriteriet ble satt der det alt var over. Nå krever skjemaet kvittering for slikt.
- **Git-historikk:** `trader_live.db` var sporet én gang; Outlet-trippelen ligger i 85eee61/23d37bb (kjent). Testdekning 85 % (lavest casefile.py og Yahoo-klienten, 38 %).
- Personvernstesten fanget to ekte kill-kriterier jeg selv hadde brukt i en test i natt. Rettet. Testen virker.

## Bare du kan avgjøre

1. Omskriving av historikken for Outlet-lekkasjen (kjent fra 22. okt) – fortsatt ikke gjort.
2. Egne grenser i sizing: `max_total_loss` og det nye `max_loss_per_group` står på standardverdier.
3. Kill-lista: skjemaet, research book og rapportleseren har ikke samme liste. Én liste, én eier.
4. Norges Banks øvrige møtedatoer må legges inn fra den offisielle kalenderen (bare 5. nov var verifiserbar).
5. Om 60-dagers momentum (grad A/B) skal bety noe for *dine* beslutninger – eller om signalene bare skal være en påminnelse om å se på aksjen.

## Før Outlet 12. november

- **Logg synet før rapporten**, helst denne uka. Et syn datert etter 12. nov skåres med etterpåklokskap. Forsiden maser til det er gjort.
- Outlet har ingen tidligere kvartalsrapport (notert 24. sept) – leseren kunne ikke testes på en gammel rapport. Kjør `oq reports dryrun OUTLT <pdf> --period 2026Q3` på prospektet/en Q2-tabell om du har en, og skriv `reports.yaml`-spec for OUTLT før 12. nov; ellers leses rapporten ikke.
- Avklar NCI-spørsmålet fra cases-gjennomgangen (privat notat `~/osloquant-home/natt/cases-review.md`).
- Sett gjerne `[margin]`/`[volume]`-tagger på kill-kriteriene i research book, så boken-samlet-blokken slutter å gjette.

## Status ved avbrudd (00:15 – bruksgrensen ble nådd)

- Full suite for H ble grønn etter avbruddet (369 passed), så `natt-2026-11-02` er flyttet til H (81123b9): A/A2, B, E, F, C, D, G og H.
- Bare I (syn eldre enn siste rapport, D29) står igjen på `natt-i-stale` (60d7f3a + denne rapporten) med grønn delkjøring, ikke full suite.
  Kjør i worktree'en `PYTHONPATH=src ../oslo-quant/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` på `natt-i-stale`;
  er den grønn: `git branch -f natt-2026-11-02 natt-i-stale`.
- Idé 25 (malspor: samme kursmål/sannsynligheter i flere caser) var neste; patch-skript
  ligger i scratchpad (`natt_j_patch.py`), ikke kjørt. D30 ikke skrevet.
- Natt-dashbordet kjører på http://127.0.0.1:8063 med H-koden (kan stoppes); main på 8060 er urørt.
