# Rapport – økten 2. november 2026 (gren `rapporter-2026-11-02`, ikke flettet, ikke pushet)

Alt under svarer på ett av to spørsmål: tar jeg en bedre kjøpsbeslutning, eller vet jeg mer sikkert når jeg tok feil?
Beslutningene står i `DECISIONS.md` (D34–D37). Testsettet: 394 passed in 564.15s (0:09:24) (hele settet grønt, ruff ren). Dashbordet fra grenen kjørte på
`http://127.0.0.1:8061` ved siden av main på 8060; skjermbilder (private, viser research book) ligger i
`~/osloquant-home/natt/shots-rapporter/` (`idag.png`, `sats.png`, `outlt.png`, `pretrade.png`, `kalibrering.png`, `datahelse.png`).

## Bygget

1. **Rapporter på aksjesiden** (`dashboard/reportpdf.py`, D34). Boksen «Rapporter» lister PDF-ene per selskap fra
   `~/osloquant-home/cases/reports_pdf/<KODE>/` med dato, utgave, syn, kursmål, DCF, kurs, sidetall og om byggeporten var
   bestått; PDF-en åpnes fra dashbordet (`/reports/<KODE>/<fil>`). Med to utgaver vises «siste estimat mot forrige» linje
   for linje. Når rapportens kursmål avviker fra siste rad i research book og ingen vurdering er logget etter rapporten,
   står det på «I dag» som punktet *report-tp* – rapporten endrer ikke boken, det gjør bare en vurdering. SATS og Outlet
   ligger der nå (2 utgaver SATS: 7. okt og 2. nov). Rapportbyggeren i Toolkit kopierer dit ved bygg (Toolkit-gren
   `report-5-dashboard`, lokal).
2. **«Før du kjøper»** (`dashboard/pretrade.py`, D35, `/stock/<KODE>/pretrade`, lenket fra skjemaet). Seks blokker:
   hva markedet priser inn (reverse DCF fra casemodellen + lett case) mot mitt syn; utfallsodds på 3/6/12 mnd (simulering,
   alle aksjer, egen historikk) med break-even-andel; bull/bear med de tre sterkeste argumentene mot kjøp sitert fra
   rapportleseren, Claudes syn, lett case, risikosignaler og egen bear-verdi i fast styrkerekkefølge; hendelser før
   horisonten; posisjonsstørrelse ved maks tap pluss åpne syn i samme sektorgruppe; sjekkliste på fire punkter som låser
   opp lenken til skjemaet. Avkryssingen skrives på raden (`checklist`), så kalibreringen kan skille syn med og uten.
3. **Lær av egne feil** (`dashboard/learn.py`, D36). Kalibreringssiden har nå Brier og oppgitt-sannsynlighet-mot-utfall per
   case, og en feilmønster-rapport bygget av regler på loggen og kursbanen: for tidlig inn, for sent ut, kill-kriterium
   ignorert, aldri sjekket, ankret til guiding (ordtreff, merket som spørsmål), kursmål innenfor 5 % av konsensus.
   Referansene OSEBX / «kursen står stille» / konsensus fantes fra D21 og står over. Med to egne rader er dette en
   struktur, ikke et funn.
4. **Datahelse** (`dashboard/datahealth.py`, D37). Ny tabell per case: alder på synet, lett case (kurs mot lageret), siste
   rapport (kursmål), modellfilens dato og avvikene i ord. I dag sier den: SATS-rapporten sier 58, synet 54; rapportleseren
   har Q3 nyere enn synet; modellfilen research book peker på er eldre enn rapporten (begge caser). Nytt fra idélisten (#24):
   kursen på raden mot lagerets sluttkurs samme dag.

Tester på fiktive data i `tests/test_rapporter.py` (7 tester: rapportliste og servering, avvik → beslutning, før-du-kjøper
inkl. sjekkliste på raden, motargumentenes rekkefølge, feilmønster og Brier per case, kalibreringssiden, datahelse-avvik).
Ingen ekte research book eller logg i tester; hash-kjeden urørt; ingen generert tekst – bare tall, lister og sitater med kilde.

## Ikke rukket

- Del 5 utover #24: bear-stress på tvers av syn (#20) og kvartalsvis reverse-DCF-serie (#33) står igjen.
- Papirkontoene (live.yaml) telles ikke i sektoreksponeringen på «Før du kjøper» – bare BUY-syn med posisjon i loggen.
- «Argumenter mot» siterer bare det som finnes maskinlesbart; rapportens egen tekst leses ikke.

## Beslutninger bare du kan ta

- SATS: rapporten av 2. nov sier 58, din vurdering 54 (6. okt). Logg en ny rad – også om du holder 54 – via «Før du kjøper».
  Forslaget til rad ligger i `~/osloquant-home/cases/proposals/SATS-2026-11-02.yaml`; jeg skriver ikke i loggen din.
- Research book peker på Toolkit-modellen på `main` (6. okt). Når Toolkit-PR-ene (#5–#8) er flettet, peker den på den nye.
- Grensene i `dashboard.yaml` (max_loss 2 000, max_position 25 %) er startverdier satt av meg – sett dine egne.
- Flette denne grenen til main, eller ikke.

## Før Outlet-rapporten 12. november

1. Logg synet ditt på OUTLT før 12. nov («I dag» ber om det; sist 8. okt) – ellers scores det med etterpåklokskap.
2. Skriv `reports.yaml`-spesifikasjon for OUTLT (datahelse: «no spec»), test med `oq reports dryrun` på en prospekt-side.
3. Gå gjennom «Før du kjøper» for OUTLT: kill-nivå mangler i vurderingen (bear-verdien brukes), ingen konsensus finnes.
4. Etter rapporten: `oq reports run`, kill-sjekk, ny rad; bygg andre utgave av Outlet-rapporten i Toolkit (revisjonen vises da på aksjesiden).
