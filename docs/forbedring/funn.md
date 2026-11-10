# Forbedring av dashbordet – funn (fase 1)

Revisjon 10. nov. 2026 på grenen `forbedring-2026-11-10`, før noe er endret. Grenen bygger på `natt-2026-11-10`
(kursgrafen, D59) og har med `docs/feilsok/funn.md` fra feilsøkingen 9. nov.

## Slik ble det gjort

- **Gjennomgang i nettleser.** Dashbordet startet på et testhjem (kopi av kurslageret, fiktiv research book og
  fiktiv vurderingslogg). 105 sider åpnet i headless Edge: 12 fellessider og 13 visninger hver for SATS, Kitron,
  Elkem, en kopi av Outlet, og TGS, DNB og Mowi uten case. For hver side er HTTP-status, tid på server og i
  nettleser, konsollfeil, tomme kort, vannrett rulling og ordene «undefined», «NaN», «nan», «None» og «inf» logget.
  Før-bilder ligger i `Pareto Equity Research/forbedring-2026-11-10/for`.
- **Tall og logikk.** Funnene #1–#132 fra 9. nov. er kontrollert mot grenen (se vedlegget). De ble den gang målt
  mot Yahoo og noterte kurser, og beregningene ble kjørt med kjente svar.
- **Datainnhenting.** Koden for hver kilde er lest. Loggene fra Windows-oppgaven 19. okt.–9. nov. 2026 (alt som
  finnes, 22 kjøringer) er talt opp. Feed-cachen og lageret i det ekte hjemmet er lest, ikke endret.
- **Kode.** `ruff check`, `ruff format --check`, søk etter avskrudde tester, private stier og hemmeligheter.

## Antall

| Gruppe | Nye funn her | Fra 9. nov. (uten duplikater) | Løst av kursgrafen (D59) |
|---|---|---|---|
| 1 Krasj og feil | 1 | 4 | 1 (#4) |
| 2 Feil tall og logikk | 1 (N2 trukket) | 59 | 1 (#12) |
| 3 Datainnhenting | 14 | (tre av de 59 hører hjemme her: #15, #36, #37) | 0 |
| 4 Visuelt og tekst | 9 | 29 samlet for 4 og 5 («Brukbarhet») | 0 |
| 5 Funksjoner og flyt | 6 | – | 0 |
| 6 Kode | 5 | 13 | 0 |

Alvor: **A** = feil tall eller krasj som kan gi en feil beslutning, **B** = misvisende eller skjuler et problem,
**C** = slitasje og pynt.

---

## 1 Krasj og feil

Gjennomgangen ga ett krasj på 105 sider, ingen konsollfeil utenom det, ingen tomme kort, ingen vannrett rulling og
ingen «undefined» eller «NaN» i synlig tekst.

| Nr | Alvor | Funn | Status |
|---|---|---|---|
| #3 | A | `/calibration` gir 500 når en prognoserad i loggen har `report` som tekst. Én rad tar ned hele siden. Reprodusert i dag. | åpen |
| #1 | A | En celle med tekst i modellfilen (reverse DCF) gir 500 på alle sju faner. | åpen |
| #2 | A | «I dag» og «Sektorer» gir 500 når lageret er tomt. | åpen |
| #4 | A | NaN i periodeknappens `data-r` knekker JSON i nettleseren. | løst av D59 (data-r har bare datoer) |
| N1 | B | Første visning etter oppstart er treg: `/funds` 21,7 s, første aksjeside 5,1 s, `/health` 2,9 s, «I dag» 2,5 s. Ingen laste-indikator. | åpen (se også #84, #94, #95) |

## 2 Feil tall og logikk

De 59 funnene fra 9. nov. står i vedlegget. De som veier tyngst:

| Nr | Alvor | Funn |
|---|---|---|
| #5 | A | Utbytter i USD justeres 9,6 ganger for lite. Justert kurs og avkastning er feil for elleve aksjer. |
| #7 | A | KOG: utskillelsen 15. apr. 2026 ligger som et kursfall på −18 %. |
| #36 | A | Rå-tabellen (noterte kurser) stoppet 19. okt. 2026 for 63 av 64 aksjer. Datahelse sier «siste 9. nov.». Årsaken står i D1. |
| #15 | A | Regnskapet mangler 3. kvartal for elleve selskaper. P/E regnes på tall til 30. juni uten varsel. Årsaken står i D2. |
| #30, #31 | A | Dagsendring og 12 m lav/høy bruker justerte kurser, så de er feil rundt hver eks-dag. |
| #44 | A | Utfallsodds gir dommen «klart mot kill-nivået» når det ikke finnes noen simulering. |
| #45, #46, #48 | A | Oppdateringsskjemaet godtar etterpåklokskap, kaster nye sannsynligheter stille og skriver «nan» og «inf» i loggen. |
| N2 | – | Trukket: regnskapsradene «datert 29. nov. 2026» er ikke en feil. Tidsstempelet er periodeslutt pluss antatt publiseringstid (60 dager), brukt for å unngå å se inn i fremtiden i tilbaketester. Perioden står i `report_date`. |
| N3 | B | Desk-tabellen viser «EV +999 % mot null-vekst» for AutoStore. Tallet er et tak, ikke en måling, og det står ikke. |

## 3 Datainnhenting

Windows-oppgaven «oslo-quant signals» kjører `scripts/run_signals.ps1` mandag–fredag 17:45 og 21:45. Den kjører
`oq record`, `oq dashboard --refresh-only`, desken og signaloversikten.

### Hva loggene sier (19. okt.–9. nov. 2026)

- 22 kjøringer på 16 dager. Alle endte med kode 0: `record` 22 av 22, `feeds` 17 av 17, `desk` 7 av 7.
- Ingen feed har meldt feil én eneste gang i loggen.
- To børsdager uten kjøring: fredag 23. okt. og torsdag 29. okt. PC-en var av. Oppgaven tar igjen kjøringen når
  PC-en starter, men ingenting på dashbordet sier at en dag ble hoppet over.
- Likevel er to tabeller utdaterte (D1, D2). Feilen ligger altså ikke i at kilder faller ut, men i at ting som
  aldri hentes, ikke vises som gamle.

### Status per kilde

| Kilde | Hva | Sist hentet (ekte hjem) | Feil i loggen | Ved feil | Henter vi for mye? | Kan stå gammelt uten varsel? |
|---|---|---|---|---|---|---|
| Yahoo, justerte kurser | 65 aksjer, daglig | 9. nov. 21:49 | 0 av 22 | 3 forsøk med 1,5 og 3 s pause, så stopper hele kjøringen (kode 2) | nei, bare manglende dager | ja: varselet på «I dag» ser bare på nyeste dato i hele tabellen |
| Yahoo, noterte kurser | 64 aksjer | **19. okt.** for 63 aksjer | hentes ikke | – | – | **ja (D1)** |
| Yahoo, regnskap | 65 selskaper | ukjent, ingen tidsstempel | hentes ikke | – | – | **ja (D2)** |
| Yahoo, indeks, valuta, Brent | 5 + 3 + 2 serier | 9. nov. | 0 | som kurser | nei | ja |
| NewsWeb, børsmeldinger | universet, 14 dager | 9. nov. 21:50 | 0 av 17 | gammel cache beholdes, feilen står bare i loggen | **ja: 14 kall per kjøring, 28 per dag, der 1–2 holder (D6)** | ja, etter 3 dager først |
| NewsWeb, innsidehandler | universet, inneværende år | 9. nov. 21:51 | 0 av 15 | som over | **ja: 65 listekall per kjøring for hele året (D6)** | ja, etter 7 dager |
| NewsWeb, finanskalender | fulgte aksjer | 9. nov. 21:51 | 0 av 9 | som over | nei | ja, etter 14 dager |
| NewsWeb, rapporter (PDF) | caser med spesifikasjon | 9. nov. | 0 | feilen skrives i loggen, ikke på siden | nei | ja |
| Norges Bank, rente og 10 år | 2 serier | 9. nov. 21:51 | 0 av 17 | gammel cache | nei | ja, etter 7 dager |
| Norges Bank, USD og EUR | 2 serier | 9. nov. 21:51 | 0 av 17 | gammel cache | nei | ja, etter 7 dager |
| SSB, laksepris | tabell 03024, ukentlig | 9. nov. 21:51 | 0 av 17 | gammel cache | nei | ja, etter 14 dager |
| Finanstilsynet, shortregister | hele registeret, 2,2 MB | 9. nov. 21:51 | 0 av 15 | gammel cache | hele registeret hver gang; API-et har ikke delspørring | ja, etter 7 dager |
| RSS (E24, DN, Finansavisen, NRK) | overskrifter og lenker | 9. nov. 21:51 | 0 av 17 | én feed nede hoppes over og navngis i `errors`; alle nede gir feil | nei | ja: `errors` vises ikke noe sted (D7) |
| MFN, konsensus | per rapport, selskaper med spesifikasjon | ved ny rapport | ukjent | **enhver feil leses som «ingen konsensus» (D8)** | nei | – |

### Funn

| Nr | Alvor | Funn |
|---|---|---|
| D1 | A | **Noterte kurser hentes aldri av oppgaven.** `run_signals.ps1` kaller `oq record` uten `--raw`. Rå-tabellen står på 19. okt. 2026 for 63 av 64 aksjer. Børsverdi, P/E, utbytteyield og kalibreringen leser den. |
| D2 | A | **Regnskapet hentes aldri av oppgaven.** `oq record` kjøres uten `--finance`. Tredje kvartal mangler for selskaper som har rapportert, og tabellene har ingen «hentet»-tid. |
| D3 | A | **Datahelse ser bare på nyeste dato i hele tabellen.** Én fersk aksje (Kitron, lagt til 9. nov.) gjør at rå-tabellen står som «siste 9. nov. 2026». Alder må måles per aksje. |
| D4 | A | **Et mislykket forsøk etterlater ingen spor.** Feilen skrives til loggfilen og ingen andre steder. Cachen beholder forrige «hentet»-tid, og siden viser bare alderen. Datahelse kan ikke skille «hentet i går» fra «prøvd i dag, feilet». |
| D5 | B | **Ingen nye forsøk på feeds.** `feeds._get` gjør ett kall med 20 s tidsavbrudd. Et kort nettbrudd gir en tapt dag for den kilden. Bare Yahoo-klienten prøver på nytt. |
| D6 | B | **Flere kall enn nødvendig mot NewsWeb.** Børsmeldinger: 14 dager hentes på nytt i hver kjøring, to ganger daglig. Innsidehandler: hele året listes på nytt for 65 aksjer i hver kjøring. Sammen rundt 160 kall per dag der 20–30 ville holdt. |
| D7 | B | **RSS-feil vises ikke.** Når én avis er nede, lagres navnet i `errors`, men ingen side leser feltet. Nyhetslisten ser hel ut. |
| D8 | B | **MFN-feil blir «ingen konsensus».** `fetch_consensus` fanger alle unntak og returnerer `None`. Nettfeil og «selskapet har ikke publisert» kan ikke skilles. |
| D9 | B | **Grensene for «utdatert» er for romslige for daglige kilder.** Børsmeldinger kan være 3 dager gamle, renter, valuta og Brent 7 dager, før noe vises. Alle hentes hver børsdag. |
| D10 | B | **Varselet på «I dag» dekker bare kurser.** Utdaterte feeds vises bare på Datahelse. Ingen side sier hvilke tall som påvirkes. |
| D11 | B | **Hoppede kjøringer vises ikke.** To børsdager uten kjøring på 16. Dashbordet vet ikke når oppgaven sist kjørte. |
| D12 | B | **Ingen kontroll mot en annen kilde i daglig drift.** Utbyttekontrollen mot NewsWeb er fra 1. nov. og kjøres bare for hånd. Kurs, valuta og Brent sjekkes ikke mot hverandre, selv om USD/NOK finnes både fra Norges Bank og Yahoo. |
| D13 | B | **Selskapshendelser fanges ikke opp.** Splitter, emisjoner, tickerendringer, avnoteringer og nye noteringer må oppdages for hånd (#7, #37). Universet er en fast liste. |
| D14 | C | **Loggen er ødelagt for norske tegn.** «på» står som «p├Ñ». PowerShell 5.1 tolker utdata fra `oq` som cp850. Loggen er vanskelig å lese når noe først feiler. |

## 4 Visuelt og tekst

| Nr | Alvor | Funn |
|---|---|---|
| V1 | B | **To språk på samme side.** «I dag»: «log your view before the report», «reached the target», «past its horizon – renew or retire it», «no new signals on research-book stocks», «3 views can die from the same driver». Merkelappene «update», «pre-report», «re-rate», «stale-view» er interne nøkler. Se også #90, #97, #105. |
| V2 | B | **Tallformatet er engelsk og sprikende.** «+14.5%» uten mellomrom i tabeller, «+14,3 %» i kursgrafen, «305610 rader» uten tusenskille, «45.5» mot «45.50». Se #108, #117, #128. |
| V3 | B | **Datahelse bruker interne navn.** «Feeds», «announcements», «rates», «no spec», «present – C:\Users\…», «adjusted» og «raw». |
| V4 | B | **To klokker i bunnen av samme side.** «Generated 10. nov. 2026 17:20» og «Generert 10. nov. 2026 16:20» (#23, #42). |
| V5 | C | **Tabeller med tekst høyrejustert.** Feed-tabellen høyrejusterer «Status» og «Hentet». Tekst skal stå til venstre, tall til høyre. |
| V6 | C | **Grafer med ulikt tema.** Kursgrafen er Lightweight Charts med norske tall. Resten er Plotly med eget rutenett, egne farger og engelske tall. |
| V7 | C | **Grønn og rød brukes til mer enn opp og ned.** Rød ramme rundt beslutningslisten, røde «no spec», grønne overskrifter. |
| V8 | C | **Beslutningslisten er en vegg.** 15 punkter med tre linjer hver før første tabell. Samme selskap står opptil fire ganger (#91). |
| V9 | C | **Forklaring og kilde ved hover mangler på fellessidene.** Aksjesiden har det. «I dag», Sektorer, Dekning, Prisen krever og Porteføljer har det ikke gjennomført (#99, #103). |

## 5 Funksjoner og flyt

Tre flyter gått som bruker på testhjemmet.

**Morgensjekk på «I dag».**
| Nr | Alvor | Funn |
|---|---|---|
| F1 | B | Siden sier ikke om kveldens innhenting gikk bra. «Siste sluttkurs: mandag 9. nov.» er eneste tegn. Er noe galt, må jeg til Datahelse for å se det. |
| F2 | B | Lenkene i beslutningslisten lander på Oversikt, ikke der handlingen gjøres (#89). Tre av handlingene finnes ikke i dashbordet (#90). |
| F3 | C | Rekkefølgen er alfabetisk innen hastegrad, ikke etter frist (#92). |

**Fullt case frem til vurderingsskjemaet.**
| Nr | Alvor | Funn |
|---|---|---|
| F4 | B | Et avvist skjema åpner Oversikt med feilen øverst, mens skjemaet ligger på en annen fane og har glemt det jeg skrev (#86, #87). Desimalkomma gir rå Python-feil i to av tre skjemaer (#88). |
| F5 | B | Bekreftelsen «Logged as row #…» kommer fra adressen, ikke fra loggen (#114). Jeg kan ikke vite om raden ble lagret uten å åpne kalibreringen. |

**Kalibrering etter en rapport.**
| Nr | Alvor | Funn |
|---|---|---|
| F6 | A | `/calibration` krasjer på én uventet rad (#3), så flyten stopper helt. Siden har ingen isolasjon per blokk (#123). Brier vises på tre skalaer (#109). |

## 6 Kode

| Nr | Alvor | Funn |
|---|---|---|
| K1 | B | **Ingen typesjekk.** Verken mypy eller pyright er installert eller satt opp. `ruff check` er ren. |
| K2 | B | **CI har ingen røyktest av dashbordet.** Sidene testes med Flasks testklient, men ingen test starter serveren og leser nettleserkonsollen på tvers av sider. |
| K3 | C | **`ruff format` er ikke i bruk.** 125 av 199 filer ville blitt omformatert. Ikke en feil, men formatet håndheves ikke. |
| K4 | C | **Avskrudde tester:** 9 tester hopper over uten frosne private data (#121, #122), 10 visuelle hopper over på Linux. |
| K5 | C | **Ingen private stier eller hemmeligheter i koden.** Søk etter brukernavn, `C:\Users` og OneDrive ga bare ordet «oscar» som analytikernøkkel. Avhengigheter: `flask` og `scipy` importeres uten å stå i `pyproject.toml` (#131). |

---

## Vedlegg: funnene fra 9. nov. med status på denne grenen

Full tekst med reproduksjon står i `docs/feilsok/funn.md`. «dup» = duplikat av et annet funn.

| Nr | Gruppe | Funn | Status |
|---|---|---|---|
| #1 | Krasj | Reverse DCF: en celle med solvertekst eller en modell som ikke kan leses gir HTTP 500 på hele aksjesiden (alle sju faner) | åpen |
| #2 | Krasj | «I dag» og «Sektorer» krasjer med 500 når lageret er tomt (NaT-dato og manglende kolonne) | åpen |
| #3 | Krasj | /calibration gir 500 (TypeError) når en forecast-rad har report som tekst – hele kalibreringssiden faller | åpen |
| #4 | Krasj | Periodeknappen får NaN i data-r når volumet mangler i hele perioden, og da feiler JSON.parse i nettleseren | løst av D59 |
| #5 | Feil tall | Utbytter i USD justeres omtrent 9,6 ganger for lite: justerte kurser og periodeavkastning er feil for FRO, HAFNI, OET, BWLPG, BWO, SNI, WAWI, … | åpen |
| #6 | Feil tall | Kalibrering: «Nå»-kursen (price_now) blåses opp med alt utbytte siden vurderingen når den noterte serien henger etter | åpen |
| #7 | Feil tall | KOG: utskillelsen av Kongsberg Maritime 15. apr. 2026 ligger i lageret som et kursfall på −18 %, og alle KOG-avkastninger over datoen blir feil | åpen |
| #8 | Feil tall | Kurscachen fornyes bare når datoen på nyeste bar endres – en ny sluttkurs for samme dato vises ikke før neste handelsdag eller omstart | åpen |
| #9 | Feil tall | 5Å er alltid av, og «Maks» er bare 26 måneder: kursbildet laster 800 dager, ikke fem år (D57) | dup #12 |
| #10 | Feil tall | 5Å er slått av på alle aksjer og «Maks» viser bare ~2,2 års avkastning – grafen har 800 dager, ikke fem år | dup #12 |
| #11 | Feil tall | 5Å er alltid av og «Maks» er bare 2,2 år: aksjesiden laster 800 dager, ikke fem år | dup #12 |
| #12 | Feil tall | Kursøyeblikksbildet holder bare 800 dager: 5Å er slått av for alle aksjer med feil begrunnelse, og «Maks» betyr bare fra 2. sep. 2024 | løst av D59 |
| #13 | Feil tall | Utbyttetabellen regner «Kurs før» og yield på justert kurs, så eldre yield blir for høy | åpen |
| #14 | Feil tall | «P/E ved kurs X» i Nøkkeltall per år viser multippelen ved lett-casens byggekurs, ikke ved kursen som står i etiketten | åpen |
| #15 | Feil tall | Regnskapet i lageret mangler 3. kvartal for 11 selskaper som har rapportert: P/E i Oversikt er regnet på tall til 30. juni uten varsel | åpen |
| #16 | Feil tall | Kalibrering: totalavkastningen mister utbyttet når den noterte serien mangler på vurderingsdatoen | åpen |
| #17 | Feil tall | Dagsendringen i kursbaren regnes mot utbyttejustert forrige sluttkurs, så den er feil på hver eks-dag | dup #30 |
| #18 | Feil tall | «12 m lav / høy» og «52 ukers høy» er utbyttejusterte kurser som aldri ble handlet, og avviker fra både Yahoo og noterte sluttkurser | dup #31 |
| #19 | Feil tall | «Prisen krever»: KOG sammenlignes med en omsetningsvekst som går over et perimeterbrudd (−0.3 %/år) og havner på kandidatlisten | åpen |
| #20 | Feil tall | «Prisen krever» regner på lett-casens byggekurs, men siden sier ikke når den ble bygget | åpen |
| #21 | Feil tall | Regnskap → Nøkkeltall: «P/E ved kurs 45.50» viser P/E ved lett-casens gamle kurs (15.5x), Oversikt viser 15.7x for samme kurs | dup #14 |
| #22 | Feil tall | «kurs nå» / «Nå» på /review og /calibration er kursen ved horisonten for endelige vurderinger, ikke dagens kurs | åpen |
| #23 | Feil tall | Klokkeslett i to tidssoner uten merking: «Generert» i bunnteksten er maskinens lokaltid, «Logget», desk og «hentet» er Oslo-tid | åpen |
| #24 | Feil tall | «P/E ved kurs 45.50» osv. i Nøkkeltall per år er regnet på lett-casens eldre kurs | dup #14 |
| #25 | Feil tall | PROT: LTM-kolonnen heter «LTM til 31. des. 2025» og EBIT-marginen blander to perioder | åpen |
| #26 | Feil tall | KIT: lett case henter netto gjeld fra 31. mars 2026 og merker egenkapitalen per 30. sep. 2026 med samme dato | åpen |
| #27 | Feil tall | Short «siste 30 dager» måles fra siste registerhendelse, ikke fra i dag | åpen |
| #28 | Feil tall | Odds-kortet har hardkodet «64 aksjer», mens lageret nå har 65 | åpen |
| #29 | Feil tall | RSI-raden viser «nan» når serien er flat | åpen |
| #30 | Feil tall | På eks-dagen viser toppbaren, /sectors og forsiden totalavkastning som «endring mot forrige sluttkurs», ikke kursendringen | åpen |
| #31 | Feil tall | «12 m lav / høy» viser justerte sluttkurser som aksjen aldri har handlet til | åpen |
| #32 | Feil tall | Multippelhistorikken (P/E og P/S per årsslutt) bruker justert årssluttkurs og dagens valutakurs | åpen |
| #33 | Feil tall | Datoen for netto gjeld brukes også som dato for egenkapitalen: feil dato i P/B-kilden og feil kvalitetskarakter | åpen |
| #34 | Feil tall | P/E, EPS, P/S og EV/EBIT er merket «LTM» selv når tallet er siste hele år | åpen |
| #35 | Feil tall | Multiplene i Oversikt for selskaper som rapporterer i USD, EUR eller DKK bruker valutakursen fra dagen lett-casen ble bygget, og hoveren nevner … | åpen |
| #36 | Feil tall | /health melder at rå-tabellen er à jour («siste 9. nov. 2026»), men 63 av 64 aksjer slutter 19. okt. 2026 | åpen |
| #37 | Feil tall | GSF: rå-tabellen har en splitt 2:1 som ikke er rettet bakover, og StockAction har ingen splitt-rad for den | åpen |
| #38 | Feil tall | RSI 14 avviker fra Wilder på korte historikker: OUTLT viser 63, Wilder gir 58 | åpen |
| #39 | Feil tall | Samme 12-måneders topp vises med to tall: Oversikt 46.23 (sluttkurs) og Teknisk «52 ukers høy» 46.90 (intradag-høy), ingen av dem merket | dup #31 |
| #40 | Feil tall | «Kurs nå» / «Nå» på feilgjennomgang og kalibrering viser kursen ved horisonten for endelige vurderinger | dup #22 |
| #41 | Feil tall | Desk-sidens datakvalitet viser UTC-tid som norsk tid (én time feil) | åpen |
| #42 | Feil tall | Bunnteksten «Generert» bruker maskinens lokale tid, resten av siden Oslo-tid | dup #23 |
| #43 | Feil tall | ELK: «Etter rapporten» viser «Vekst prisen krever −38.6 %» mens lett case på samme side sier at ingen vekstrate gjelder | åpen |
| #44 | Feil logikk | Utfallsodds gir dommen «klart mot kill-nivået» når det ikke finnes noen simulering (nylig notert aksje, OUTLT) | åpen |
| #45 | Feil logikk | Oppdateringsløkka (D48) aksepterer en oppdatering etter at horisonten er ute og scorer den i etterpåklokskap | åpen |
| #46 | Feil logikk | Oppdateringsskjemaet (D48) kaster de nye sannsynlighetene stille hvis «endret» ikke er krysset av, og skriver de gamle til den uforanderlige loggen | åpen |
| #47 | Feil logikk | Oppdateringsspørsmålet stilles for vurderinger som har passert horisonten, og Brier for en oppdatering skrevet etter horisonten settes som «bedre» … | dup #45 |
| #48 | Feil logikk | «nan», «inf» og «1e999» godtas som tall og skrives permanent i vurderingsloggen | åpen |
| #49 | Feil logikk | Oppdateringsløkken (D48) gjelder også modne vurderinger – etterpåklok oppdatering scores som bedre Brier | dup #45 |
| #50 | Feil logikk | Teknisk-fanen merker «(utløst nå)» ut fra tilstand, ikke ut fra det målte signalet (kanalraden ser ikke på MA20, drawdown og MA-kryss gjelder i … | åpen |
| #51 | Feil logikk | «60 dagers lav» og volumkravet for 60-dagers brudd regnes på en annen måte enn det målte signalet de henter odds fra | åpen |
| #52 | Feil logikk | 5Å er alltid deaktivert med forklaringen «for kort historikk i lageret», og «Maks» dekker bare 548 økter (fra 2.9.2024) | dup #12 |
| #53 | Feil logikk | Kalibreringen regner dagens kurs for høyt når et utbytte er gått ex etter synet og rå-tabellen ligger etter | dup #6 |
| #54 | Feil logikk | Avsluttede vurderinger (horisont passert) telles som åpne: «Gjør først»-oppdatering på forsiden, «Ikke oppdatert» på kalibreringen, R05 = 50 %, … | åpen |
| #55 | Feil logikk | Feilmønstrene «for tidlig inn» og «for sent ut» måler justert kursbane mot notert kurs og kill-nivå | åpen |
| #56 | Feil logikk | En halvferdig dagsbar fra en kjøring i åpningstiden vises som «siste sluttkurs», mens oddsene på samme side dropper den | åpen |
| #57 | Feil logikk | Teknisk-raden «60 dagers lav» bruker sluttkurser, mens oddsene den viser er målt på intradag-low | åpen |
| #58 | Feil logikk | Varselet om gamle kurser på «I dag» slår ut dagen etter hver børsfridag, men ikke en ukedagskveld da dagens sluttkurs mangler | åpen |
| #59 | Feil logikk | 6M og 5Å teller økter i stedet for kalendermåneder: 6M for SATS viser +6.0 %, der seks måneder gir +10.3 % | åpen |
| #60 | Feil logikk | «other» (ingen driver gjenkjent) telles som delt kill-driver: forsiden og analysesjefen varsler at urelaterte syn «dør av samme driver» | åpen |
| #61 | Feil logikk | Etter en oppdatering viser syn-boksen, oddsene og Før du kjøper fortsatt de gamle sannsynlighetene | åpen |
| #62 | Feil logikk | Ugyldig desk-POST (ukjent kode) lagrer en tom kjøring som blir «Dagens kjøring» på /desk og forsiden | åpen |
| #63 | Feil logikk | Utfallsodds gir dommen «klart mot kill-nivået» uten data (OUTLT, 33 økter) | dup #44 |
| #64 | Feil logikk | «Uendret»-oppdatering kan ikke logges for en vurdering uten sannsynligheter | dup #46 |
| #65 | Feil logikk | Uklassifiserte kill-kriterier («other») regnes som felles kill-driver | dup #60 |
| #66 | Feil logikk | Et SELL-syn uten kill-nivå får bear-verdien som kill-nivå (på samme side av kursen som kursmålet), og dermed aldri utfallsodds | åpen |
| #67 | Feil logikk | Lett case sier «the price needs growth at or above the cost of capital» når den løste veksten ligger under (SALM: 8,33 % mot 8,5 %) | åpen |
| #68 | Feil logikk | value_reading gir meningsløse lesninger på kantinput: ROIC None gir «at or above WACC», og EV ≤ 0 gir et negativt avkastningskrav | åpen |
| #69 | Feil logikk | «Før du kjøper» beskriver odds-metoden feil: universet bruker volatilitetsskalerte avstander, ikke «like nivåer» eller «samme prosentavstander» | åpen |
| #70 | Feil logikk | Periodeknappene er én økt for strenge: med n+1 sluttkurser deaktiveres perioden n | åpen |
| #71 | Feil logikk | Størrelseskalkulatoren i skjemaet (JS) ignorerer max_loss_per_group og tilbyr en størrelse serveren avviser | åpen |
| #72 | Feil logikk | «bedre/ikke bedre» i oppdateringstabellen gjør Brier 0,0 om til 9 | åpen |
| #73 | Feil logikk | Kvartalsprognose (D52) kan besvares av feil rapport: answer() ser ikke på prognosens rapportdato | åpen |
| #74 | Feil logikk | «Kill-kriterium handlet på» teller norske ord som «beholdt» som handling | åpen |
| #75 | Feil logikk | Forsiden kaller en vurdering «past its horizon» 4–6 dager før horisonten (360 dager mot 12 kalendermåneder) | åpen |
| #76 | Feil logikk | «Utbytte siste 12 m» og direkteavkastningen dobles i dagene etter et årlig utbytte som kom tidligere enn året før | åpen |
| #77 | Feil logikk | /sectors: gruppens «snitt … i år» tar med avkastning fra notering uten å merke det | åpen |
| #78 | Feil logikk | Periodeknappen trenger én sluttkurs mer enn /sectors for samme periode (feil med én for nye aksjer) | åpen |
| #79 | Feil logikk | Dekningslinjen på forsiden (universet, full/lett case, under plan) forsvinner helt når Claude ikke har noe syn | åpen |
| #80 | Feil logikk | Kill-driveren gjettes med delstreng-treff: «strategi» → rates, «Sektoren» og «nok» → fx | åpen |
| #81 | Feil logikk | Overvåkningslisten godtar koder som ikke finnes i lageret | dup #106 |
| #82 | Feil logikk | En perfekt oppdatering (Brier 0) merkes «ikke bedre» | dup #72 |
| #83 | Feil logikk | Prognose-POST stoler på skjulte felter: rapportdato og -navn kan settes fritt | dup #73 |
| #84 | Brukbarhet | Aksjesiden er over 2 s på serveren og 3–7 s i nettleseren; signals_since for hele universet og Excel-lesing på hver forespørsel dominerer | åpen |
| #85 | Brukbarhet | Oppdateringsskjemaet (D48) godtar ikke desimalkomma og viser en rå Python-feil | dup #88 |
| #86 | Brukbarhet | Skjema med feil åpner siden på Oversikt: feilmeldingen står øverst, men skjemaet med det du skrev er skjult på en annen fane | åpen |
| #87 | Brukbarhet | Oppdaterings-, prognose- og unnlatelsesskjemaet glemmer det du skrev når serveren avviser det | åpen |
| #88 | Brukbarhet | Desimalkomma og mellomrom i tall: vurderingen godtar «0,25» og «13 500», oppdateringen gir en rå Python-feil og prognosen avviser | åpen |
| #89 | Brukbarhet | Forsidens lenker lander på Oversikt; handlingen ligger på Min vurdering eller Rapporter, og etter en prognose sendes du til feil fane | åpen |
| #90 | Brukbarhet | Forsiden ber om handlinger dashbordet ikke har: «log a kill check», «close the case», «renew or retire it» | åpen |
| #91 | Brukbarhet | Beslutningslisten teller samme selskap flere ganger: «15 ting, omtrent 180 minutter» er 4 selskaper + analysesjefen | åpen |
| #92 | Brukbarhet | Rekkefølgen «i denne rekkefølgen» er alfabetisk innen hastegrad, ikke etter frist | åpen |
| #93 | Brukbarhet | Desk-blokken på forsiden lister 42 parkerte, men navngir ikke den ene som ble drept – din egen BUY i SATS | åpen |
| #94 | Brukbarhet | «Før du kjøper» bruker 1.5–3.7 s: snapshot()/get_coverage kalles 8 ganger fordi _groups() kalles én gang per case | åpen |
| #95 | Brukbarhet | Første side etter oppstart er treg: I dag 4.4–5.1 s, Desk 2.4–4.7 s, Porteføljer 2.3–2.7 s, Datahelse 2.5 s | åpen |
| #97 | Brukbarhet | Feilmeldinger er engelske, rå Python-tekster eller mangler – og 404 er Flasks standardside | åpen |
| #99 | Brukbarhet | Kurser og avkastning på /sectors og forsiden har ingen hover med kilde og tidspunkt, og hovrene på aksjesiden har ISO-datoer | åpen |
| #101 | Brukbarhet | /calibration laster hele prisgrunnlaget tre ganger per visning | åpen |
| #102 | Brukbarhet | Forsiden: «110 signaler på andre aksjer – vis» åpner bare 60 | åpen |
| #103 | Brukbarhet | Fire sider viser kurser uten dato: /coverage, /watchlist, /screen og papirfondenes NAV på /funds | åpen |
| #105 | Brukbarhet | Blandet språk og en feilmelding som peker på en avkrysning som ikke finnes («tick «I know»») | åpen |
| #106 | Brukbarhet | Overvåkning godtar en ticker som ikke finnes («ZZZZ added.»), og den kan ikke fjernes; søkefeltet sender ugyldig kode stille til forsiden | åpen |
| #107 | Brukbarhet | Tekst kuttes midt i ord uten «…», også i det som lagres på vurderingsraden | åpen |
| #108 | Brukbarhet | Tallformat sprikker: prognoser «13000 – 13500», historikk «45.5» mot «45.50», og :g gir 1.23457e+06 over seks sifre | åpen |
| #109 | Brukbarhet | Kalibreringssiden viser Brier på tre skalaer med ulike referansepunkter; vanskelig å vite om et tall er godt | åpen |
| #110 | Brukbarhet | Oppsett: vurderingshistorikken klemmes i et halvbredt kort (datoer over tre linjer) og «Jeg vet det»-avkrysningen står løsrevet midt på egen linje | åpen |
| #111 | Brukbarhet | plotly.min.js (4.8 MB) lastes synkront i <head> på alle sider, også sider uten grafer | åpen |
| #113 | Brukbarhet | Datopasset gjør om datoer inne i Windows-stier | åpen |
| #114 | Brukbarhet | Bekreftelsen «Logged as row #…» vises fra URL-en uten å sjekke loggen | åpen |
| #115 | Brukbarhet | «Siste rapport» og «Neste rapport» er tomme for ikke-fulgte aksjer uten at siden sier hvorfor eller hva man gjør | åpen |
| #116 | Brukbarhet | «Før du kjøper»: kommaer fjernes fra gruppenavn og lister, og «fra før» teller aksjen selv | åpen |
| #117 | Brukbarhet | Negativ null i tallformat («-0.00 R», «-0», «-0%», «-0.0%») | åpen |
| #118 | Brukbarhet | Desk-tabellen på aksjesiden viser bare klokkeslett, så en kjøring 8. nov. ser ut som 6. nov. | åpen |
| #119 | Kode | Skjemaene godtar POST fra hvilken som helst nettside (ingen CSRF-/Origin-sjekk), og Host-headeren sjekkes ikke | åpen |
| #120 | Kode | 11 except-blokker svelger feil uten logg; en kodefeil vises som falsk tom tilstand («for kort historikk») | åpen |
| #121 | Kode | 9 tester hoppes alltid over i CI, og de leser ~/osloquant-home/testdata uansett OSLOQUANT_HOME (to av dem bruker en kopi av den ekte research book) | åpen |
| #122 | Kode | Frosne testdata leses fra den ekte hjemmappen selv når OSLOQUANT_HOME peker på et testhjem | åpen |
| #123 | Kode | Kalibreringssiden har ingen isolasjon per blokk: én rad med uventet form i den uforanderlige loggen gir 500 på hele siden | dup #3 |
| #124 | Kode | sizing.py-docstringen viser max_loss_per_group utenfor sizing:-blokken | åpen |
| #125 | Kode | «Neste rapport» plukkes på fem steder med ulike regler; aksjesidens topplinje kaller enhver research-book-hendelse «Neste rapport» | åpen |
| #126 | Kode | Målte signalodds caches til serveren startes på nytt i render._odds(), mens andre deler leser filen på nytt – to versjoner på samme server | åpen |
| #127 | Kode | Desk-regelen «verdien må ha et tall» får koden til å skrive 0 for ukjente verdier («dag 0 %», «ROIC 0 %») | åpen |
| #128 | Kode | Prosent- og tusenformat kommer fra 16 hjelpefunksjoner med tre former, blandet på samme side | åpen |
| #129 | Kode | Duplisert kode: identiske hjelpere og konstanter kopiert mellom moduler | åpen |
| #130 | Kode | Død kode: ubrukte funksjoner, felt, parametere og en «if False»-gren med ødelagt HTML | åpen |
| #131 | Kode | flask og scipy importeres direkte, men står ikke i pyproject.toml | åpen |
| #132 | Kode | dashboard/calendar.py skygger standardbibliotekets calendar når Python startes fra dashboard-mappen | åpen |
