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

## Fase 2 (fortsatt): feil tall og logikk

### E7 Loggen tar ikke imot «nan» og «inf», og oppdateringsskjemaet kaster ikke det du skrev (#48, #46, #64, #88, #85)
- **Problem:** «nan», «inf» og «1e999» godtas som tall og skrives permanent i den uforanderlige loggen.
  Oppdateringsskjemaet kaster nye sannsynligheter stille når «endret» ikke er krysset av, og gir rå Python-feil på
  desimalkomma.
- **Endring:**
  - `jg.append` avviser enhver rad med et tall som ikke er endelig, uansett radtype.
  - `server._num` avviser de samme verdiene med en norsk melding.
  - Oppdateringsskjemaet: sannsynligheter som er fylt ut og avviker fra de gamle uten avkrysning, gir meldingen
    «du skrev nye sannsynligheter – kryss av for endret». Desimalkomma godtas.
- **Test:** POST med «nan» og «inf» gir 400 og ingen rad; oppdatering med nye tall uten avkrysning gir 400 og ingen
  rad; «0,25» godtas.

### E8 Utfallsodds tar ikke stilling uten simulering (#44, #63)
- **Problem:** Med for kort historikk er andelen NaN, og kortet sier «klart mot kill-nivået».
- **Endring:** Uten avgjorte baner viser kortet «for kort historikk – ingen simulering» og ingen dom. Samme i desk-teksten.
- **Test:** en simulering med null avgjorte baner gir ingen av ordene «mot målet» eller «mot kill-nivået».

### E9 Utbytter i fremmed valuta justeres med riktig beløp i kroner (#5, #13 delvis)
- **Problem:** For selskaper som betaler utbytte i USD eller DKK justerer Yahoo kursen med beløpet i fremmed valuta
  mot en kurs i kroner. Justeringen blir 9,6 ganger for liten for USD og 1,4 ganger for liten for DKK. Kontroll på
  kopien av lageret: 156 av 960 utbytter siden 2015 er rammet, hos FRO, HAFNI, OET, BWLPG, BWO, SNI, WAWI, BORR, ODL,
  MPCC, EQNR, AKRBP og BAKKA. Beløpet i utbyttelisten er dessuten regnet om med valutakursen den dagen historikken
  ble lastet ned, ikke kursen på eks-dagen.
- **Endring:** Ny regel 0 i `recorders/yahoo/cleaning.py`, `fix_foreign_dividends`, som kjøres før de andre reglene
  og også for utbyttelisten.
  - For hvert utbytte regnes beløpet Yahoo faktisk brukte i justeringen: (1 − faktorsteg) × sluttkurs dagen før.
  - Er det oppgitte beløpet 1,15 ganger større eller mer, og forholdet treffer dagens USD-, EUR- eller DKK-kurs
    innen 5 %, er utbyttet i den valutaen. Beløpet i kroner blir valutabeløpet ganger kursen siste dag før eks-dagen
    (Yahoo-valutakurser fra lageret).
  - Justert kurs for alle dager før eks-dagen skaleres til riktig faktorsteg, og utbyttet lagres i kroner.
  - Uten valutakurser i lageret gjør regelen ingenting.
- **Virkning:** Regelen endrer hele den justerte historikken for de rammede aksjene første gang `oq record` kjøres
  etter sammenslåing. Papirkontoene leser samme lager, så signalene deres på disse aksjene vil regnes på riktigere
  totalavkastning. Dette må Oscar vite før sammenslåing.
- **Test:** et utbytte på USD 1 med kurs 10 på eks-dagen og 9,5 på nedlastingsdagen gir faktorsteg 0,90 og beløp
  NOK 10; et kroneutbytte røres ikke; uten valutakurser røres ingenting; utbyttelisten får samme beløp.

### E10 Selskapshendelser fanges opp, og KOG-utskillelsen tas ut av avkastningen (#7, D13)
- **Problem:** Utskillelsen av Kongsberg Maritime 15. apr. 2026 ligger som et kursfall på −18 % i den justerte
  serien. Yahoo har ingen hendelse den dagen. Splitter, emisjoner, tickerendringer, avnoteringer og nye noteringer
  oppdages bare for hånd, og universet er en fast liste.
- **Endring:**
  - `data_exceptions.yaml`: KOG.OL 15. apr. 2026 legges i `drop_returns`, som AKSO i 2024. Hele dagsbevegelsen tas
    ut, så avkastningen over datoen er et anslag (EST) og merkes slik i begrunnelsen.
  - Børsmeldingene vi allerede henter, leses for selskapshendelser: emisjon, splitt eller spleis, fisjon eller
    fusjon, navn- eller tickerendring, avnotering, og nye selskaper tatt opp til handel (også utenfor universet).
    Obligasjoner holdes utenfor. Ingen ekstra kall.
  - Datahelse viser kortet «Selskapshendelser». Hendelser fra de siste 14 dagene står under «Ting å vite nå» og på
    «I dag» som «Universet bør sjekkes».
- **Test:** titler på norsk og engelsk klassifiseres riktig, obligasjonsnoteringer gir ingen treff, en ny notering
  utenfor universet beholdes, og Datahelse og «I dag» viser hendelsen.

## Fase 4: ett visuelt system

### E12 Norsk tallformat på hver side (V2, #108, #117, #128)
- **Problem:** Tall skrives på engelsk og på flere måter: «+14.5%», «45.50», «-0.00 R». Kursgrafen skriver norsk,
  resten ikke. Formatet kommer fra seksten hjelpefunksjoner.
- **Endring:** Ny modul `dashboard/tall.py`. `norske_tall` er ett siste pass i `page()`, som datoene i D58:
  desimalkomma, mellomrom før prosenttegnet, ekte minustegn, og «−0,00» blir «0,00». Passet rører bare tekst mellom
  tagger og hover-teksten i `title`. Skjemafelt, lenker, skript, kode, versjonsnumre, adresser og filnavn står urørt.
  Plotly-grafene får desimalkomma gjennom den norske lokalen.
- **Test:** `tests/test_tall.py`: 20 skrivemåter som skal endres, 19 som ikke skal det, skjemafelt og skript urørt,
  og passet gir samme resultat om det kjøres to ganger på hver side.

### E13 Én aksentfarge, grønn og rød bare for opp og ned, tekst til venstre og tall til høyre (V5, V7)
- **Problem:** Rød brukes til beslutningslisten, feilmeldinger og statuser som «no spec». Tabeller høyrejusterer
  også tekstkolonner.
- **Endring:**
  - Beslutningslisten og merkelappene bruker aksentfargen. Feilmeldinger er ravgule med tykk kant, bekreftelser i
    aksentfargen. Statuser har egne klasser (`st-ok`, `st-warn`, `st-bad`): ok er dempet, et problem er ravgult og
    fet. Grønn og rød står igjen for kursbevegelser, kursmål og kill-nivå.
  - Ett skript på hver side venstrejusterer en tabellkolonne når de fleste cellene er tekst. Tallkolonner står
    høyrejustert som før. En celle med egen justering beholder den.
- **Test:** nettlesertest: på Datahelse er «Kilde» og «Status» venstrejustert og «Feil» høyrejustert; på Sektorer er
  navnekolonnen venstrejustert og avkastningskolonnene høyrejustert.

### E14 «I dag» på norsk, med lenker dit handlingen gjøres (V1, V3, F2, #89, #90)
- **Problem:** Overskrifter og forklaringer i beslutningslisten er engelske, merkelappene er interne nøkler
  («stale-view»), lenkene lander på Oversikt, og tre av handlingene finnes ikke i dashbordet.
- **Endring:** Tekstene er oversatt. Merkelappene har norske navn. Hver lenke går til fanen der handlingen gjøres:
  Min vurdering, Rapporter eller Teknisk. «log a kill check», «close the case» og «renew or retire it» er erstattet
  med handlingen som finnes: logg en ny vurdering. Datahelse bruker norske statuser.
- **Test:** forsiden har ingen av de engelske setningene, og en «gammelt syn»-lenke peker på `/aksje/<kode>/vurdering`.

### E15 Røyktest i nettleser, og en tom tilstand på «Prisen krever» (K2, fase 5)
- **Problem:** Ingen test starter dashbordet og leser nettleserkonsollen på tvers av sidene. Første kjøring av en
  slik test fant et tomt kort på «Prisen krever» når ingen lette caser er bygget.
- **Endring:** `tests/test_royk_browser.py` starter dashbordet på en syntetisk kopi, åpner de 12 fellessidene og 13
  visninger for to aksjer, og feiler ved konsollfeil, feilside, tomt hovedfelt uten forklaring, tomme kort,
  vannrett rulling, eller ordene «undefined», «NaN», «None» og «Traceback». Den kjører i CI: GitHub-maskinen har
  Chrome, og `websockets` følger med yfinance. Det tomme kortet sier nå hva som mangler og hvilken kommando som
  bygger det.
- **Test:** testen selv, 38 sider.
