# Endringer – forbedring av dashbordet

Hver endring står her før den gjøres: hvilket funn den løser (`funn.md`), hva som endres, og testen som viser det.

## Fase 2: krasj og feil tall

### E1 Én rad eller én modellfil skal ikke ta ned en hel side (#1, #3, #123, F6)
- **Problem:** `/calibration` gir 500 på én prognoserad med uventet form. En tekstcelle i modellfilen gir 500 på
  alle sju faner på aksjesiden.
- **Endring:**
  - `casefile.reverse_dcf` leser tallene som tall. Tekst i en tallcelle («n.a.», «outside range») blir `None` og
    teksten vises i kortet. En fil som ikke kan leses, eller en nøkkel som mangler i kartet, gir kortets egen
    feilmelding.
  - `forecasts.report_of` gir rapporten som `{date, what, source}` uansett form i loggen. `jg.append` avviser en
    prognose uten rapportdato.
  - `render.block` tegner en blokk for seg: feiler den, står det en feilmelding i blokken, feilen logges, og resten
    av siden vises. Brukes på hver blokk på kalibreringssiden.
- **Test:** `tests/test_forbedring.py`: kalibreringssiden svarer 200 med en tekst-rapport i loggen og viser de
  andre blokkene; aksjesiden svarer 200 med «n.a.» i modellen og med en modell uten kart-nøkkel.

### E2 Tomt lager gir en tom tilstand, ikke 500 (#2)
- **Problem:** «I dag» og «Sektorer» krasjer når lageret er tomt (ny installasjon, eller en ødelagt nedlasting).
- **Endring:** Begge sider viser «Lageret har ingen kurser» med kommandoen som fyller det.
- **Test:** begge sider svarer 200 på et tomt lager og nevner `oq record`.

### E3 Feilsider på norsk som sier hva man gjør (#97)
- **Problem:** 404 og 500 er Flasks engelske standardsider uten meny.
- **Endring:** Egne sider med menyen, hva som gikk galt, og neste steg. 500 logger feilen med sti.
- **Test:** ukjent adresse gir 404 med menyen; en rute som kaster, gir 500 med menyen og uten Python-sporing.

### E4 Kveldsoppgaven henter noterte kurser hver dag og regnskap hver uke (D1, D2, #36, #15, #6)
- **Problem:** `oq record` kjøres uten `--raw` og `--finance`. Noterte kurser stoppet 19. okt. for 63 aksjer, og
  regnskapet oppdateres aldri. Børsverdi, P/E og kalibreringens «nå»-kurs leser gamle tall.
- **Endring:** `run_signals.ps1` kjører `oq record --raw` (samme nedlasting som de justerte kursene, ingen ekstra
  kall). `run_weekly.ps1` kjører `oq record --finance` (seks kall per selskap, én gang i uken).
- **Test:** skriptene inneholder flaggene; `oq record --raw` skriver rå-tabellen uten ekstra nedlasting
  (eksisterende test i `test_recorder.py`).

## Fase 3: datainnhenting

### E5 Én oversikt over hver datakilde: sist hentet, sist forsøkt, feil og hva som påvirkes (D3, D4, D9, D10, D11, F1)
- **Problem:** Et mislykket forsøk etterlater ingen spor. Datahelse måler alder på nyeste rad i hele tabellen, så én
  fersk aksje skjuler 63 gamle. «I dag» varsler bare om kurser. Hoppede kjøringer vises ikke.
- **Endring:** Ny modul `dashboard/sources.py`.
  - Hver kilde har navn, opphav, hvor fersk den skal være, og hvilke tall som lener seg på den.
  - Hvert forsøk skrives i `feeds/_runs.json`: tid, ok eller feil, varighet. De siste 60 beholdes per kilde.
  - Status per kilde: «ok», «utdatert», «feilet» eller «aldri hentet». Daglige kilder er utdaterte når de ikke er
    hentet siden forrige børsdags stengetid. Tabellene i lageret måles per aksje.
  - Datahelse viser tabellen «Kilder». «I dag» viser et varsel med hver kilde som ikke er ok, og tallene den
    påvirker.
- **Test:** hver kilde simuleres som nede: status blir «feilet», den gamle tiden står, og «I dag» og Datahelse
  navngir kilden. En rå-tabell som ligger etter for 63 av 64 aksjer vises som utdatert selv om én aksje er fersk.

### E6 Nye forsøk med pause, og færre kall (D5, D6, D7, D8, D14)
- **Problem:** Ett kall, 20 s tidsavbrudd, ingen nye forsøk. NewsWeb får rundt 160 kall per dag der 20–30 holder.
  RSS-feil og MFN-feil vises ikke. Loggen er uleselig for norske tegn.
- **Endring:**
  - `feeds._get` prøver tre ganger med 2 og 5 s pause på nettfeil, tidsavbrudd og 5xx/429. 4xx gir feil med en gang.
  - Børsmeldinger: dagene siden forrige vellykkede henting pluss én, høyst 14. Innsidehandler: listen for året
    hentes fra dagen etter forrige henting.
  - RSS: aviser som var nede, står i kildetabellen. MFN: nettfeil skrives i kjøreloggen og er ikke lenger det
    samme som «ingen konsensus».
  - Skriptene setter konsollens koding til UTF-8 før `oq` kjøres.
- **Test:** `_get` prøver på nytt ved 503 og gir opp ved 404; børsmeldinger henter 2 dager når forrige henting var
  i går; RSS med én avis nede gir status «delvis».
