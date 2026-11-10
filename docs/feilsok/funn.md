# Feilsøking av dashbordet – funn (fase 1)

Gjennomgang 9. nov. 2026 på et testhjem: kopier av lagerets kurser, regnskap, lette caser, feeder, rapporter og desk-kjøringer,
og en **fiktiv** research book og vurderingslogg med gyldig hash-kjede. Den ekte research booken, loggen og hash-kjeden ble ikke lest
av testene og aldri skrevet. Sju aksjer gjennom alle sider og faner: SATS, Kitron (KIT), Elkem (ELK), Outlet (OUTLT, kopi av
casestrukturen med fiktivt syn) og tre uten case – TGS, Protector (PROT, finans) og Bakkafrost (BAKKA, rapporterer i DKK).
124 sider hentet med servertid, mistenkelig tekst og nettleserkonsoll (DevTools-protokollen); syv parallelle gjennomganger
(krasj, kurser, avkastning, odds/DCF, kalibrering/størrelse/desk, brukbarhet, kode) med kjent-svar-tester.

Stier: `<repo>` er oslo-quant, `<testhjem>` testhjemmet, `<feilsok>` arbeidsmappen med skriptene som reproduserer funnene
(ligger utenfor repoet). Funn som har en duplikat peker til hovedfunnet.

| Kategori | Funn | Duplikater | Bekreftet i fase 1 | Ikke kontrollert | Avvist |
|---|---|---|---|---|---|
| Krasj | 4 | 0 | 2 | 2 | 0 |
| Feil tall | 39 | 10 | 13 | 25 | 1 |
| Feil logikk | 40 | 10 | 17 | 23 | 0 |
| Brukbarhet | 30 | 1 | 1 | 29 | 0 |
| Kode | 14 | 1 | 2 | 12 | 0 |
| Byggeforslag (egen liste nederst) | 8 | | | | |

## Krasj

### #1 Reverse DCF: en celle med solvertekst eller en modell som ikke kan leses gir HTTP 500 på hele aksjesiden (alle sju faner)

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/casefile.py:19-25 (returnerer rå celleverdier; KeyError når en nøkkel mangler i kartet); render.py:189-192 (pct) og render.py:836-842 (rd['price']:.2f, rd['dcf']:.1f, rd['rd_k']:.1f); pretrade.py:73-79; desk.py:561-565. server.py:117 kaller reverse_dcf uten try (desk.py:552-556 har try), og stockpage.py:580-583 tegner alle faner hver gang
- **Reproduser:** Kjør data/test_side_med_modelltekst.py (kopi av testhjemmet, Flask test client, bare GET). Når reverse_dcf gir rd_cagr='n.a.' og rd_wacc='outside range', svarer GET /aksje/SATS/oversikt med HTTP 500 (ValueError: Unknown format code 'f' for object of type 'str'). Når reverse_dcf kaster KeyError('Reverse_DCF\|rd_k'), blir det også HTTP 500. Enhetstestene i rene/test_reverse_dcf_kjent.py (syntetisk xlsx med kart) feiler for kortet, for pretrade.implied (ValueError i pretrade.py:77), for manglende nøkkel i kartet (KeyError) og for en arbeidsbok uten bufrede verdier (TypeError i render.py:841).
- **Forventet:** Toolkit-arket skriver selv «n.a.» (Reverse_DCF!C8/C36 når kursen ligger utenfor Sensitivity-tabell 5) og «outside range» (C84/C131 når kursen ligger utenfor intervallet). Kortet bør vise «–» eller «utenfor området», og en modellfeil bør vises som kortets egen feilmelding.
- **Vist:** HTTP 500 på /aksje/SATS, på alle faner. Feilen ligger latent i dag: modellene for SATS, ELKEM og OUTLT har bare tall i cellene som leses (jeg sjekket typene). Elkem har rd_cagr_ref = None, og det håndteres.
- **Årsak:** Verdiene formateres med :.1f uten typesjekk, og stock_context fanger ikke unntak fra reverse_dcf.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #2 «I dag» og «Sektorer» krasjer med 500 når lageret er tomt (NaT-dato og manglende kolonne)

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** http://127.0.0.1:<port>/ og /sectors; src/osloquant/dashboard/server.py:69 og :71 (f"{snap.asof:%Y-%m-%d}"), src/osloquant/dashboard/market.py:55 (asof = pd.NaT når panelet er tomt), src/osloquant/dashboard/render.py:334 (ret["group"] på tom ramme)
- **Reproduser:** PYTHONPATH="<repo>\src" python <feilsok>\kode\empty_home_pages.py <feilsok>\kode  (lager et nytt, tomt hjem i scratch-mappen og ber om 16 URL-er med Flask test_client)
- **Forventet:** Alle 16 URL-er svarer 200 med en tom tilstand som sier hva som mangler (slik de 14 andre gjør).
- **Vist:** "/ EXC ValueError NaTType does not support strftime at server.py:69" og "/sectors EXC KeyError 'group' at render.py:334"; de andre 14 (desk, calendar, coverage, screen, funds, calibration, review, chief, watchlist, health, stock/SATS, aksje/SATS, aksje/SATS/teknisk, pretrade) gir 200.
- **Årsak:** market._snapshot_cached setter asof=pd.NaT for et tomt panel, og today_context formaterer den uten vakt; sectors_page indekserer 'group' på mk.returns() som er tom uten kolonner. Pyright flagger samme NaT-familie flere steder (dates.py:26, weekly.py:32-33, insiders.py:221 NaT.normalize, signals.py:575) – NaT.normalize() gir AttributeError og NaT-formatering ValueError (kjørt).
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #3 /calibration gir 500 (TypeError) når en forecast-rad har report som tekst – hele kalibreringssiden faller

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /calibration ; src/osloquant/dashboard/forecasts.py:158 (calibration_html), samme oppslag f["report"]["date"] i forecasts.py:86, :141, :144 og today.py:240; validering i src/osloquant/judgements.py:50 og :106-123; kalles fra server.py:682 uten vern
- **Reproduser:** GET /calibration (testhjemmet har rad #9 kind=forecast med report="Q4 2026 report"). srv8064.err viser 4 like tracebacks. Ren gjenskaping: fc.calibration_html(fc.scoring([{kind:'forecast',code:'SATS',date:'2026-11-05',report:'Q4 2026 report',metric:'revenue',low:1350,mid:1420,high:1490,label:'x'}])) -> TypeError (test_calibration_forecast_block_survives_a_string_report). jg.append('forecast', {... report:'Q4 2026 report' ...}) godtas (test_jg_append_rejects_a_forecast_without_a_report_date).
- **Forventet:** Siden svarer 200; prognoseblokken viser raden som «ikke avgjort ennå» eller hopper over den med en melding. På en kopi der raden er skrevet om til {date,what,source} svarer siden 200 og viser Brier 0.71 = snitt(0.875, 0.875, 0.375).
- **Vist:** 500 Internal Server Error, 0 kB – også vurderingskalibreringen, Brier, pålitelighet og læringsblokkene forsvinner.
- **Årsak:** Rotårsak: testhjem-byggeren skrev report som streng. Dashbordet selv kan IKKE skrive den formen: POST /stock/<code>/forecast bygger alltid report som dict (server.py:517) og CLI-en har ingen forecast-kommando. Men jg.append sjekker bare at report ikke er tom, og ingen leser av forecast-rader tåler en annen form; én rad tar ned hele siden (ikke try/except som _habit_items har).
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #4 Periodeknappen får NaN i data-r når volumet mangler i hele perioden, og da feiler JSON.parse i nettleseren

*Alvor lav, sikkerhet middels; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/charts.py:104,106 (NaN er sann, så v1 = NaN*1.05) → stockpage.py:115 (json.dumps skriver NaN) → stockpage.py:553 (JSON.parse)
- **Reproduser:** rene/test_perioder_teknisk_kjent.py::test_period_volume_all_nan_gives_nan_axis gir v1 = nan. Feilen ligger latent: ingen aksje i testhjemmet har bare NaN-volum i 5D-vinduet i dag.
- **Forventet:** v1 = None
- **Vist:** v1 = NaN
- **Årsak:** `vmax * 1.05 if vmax` stopper ikke NaN.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

## Feil tall

### #5 Utbytter i USD justeres omtrent 9,6 ganger for lite: justerte kurser og periodeavkastning er feil for FRO, HAFNI, OET, BWLPG, BWO, SNI, WAWI, BORR, ODL, MPCC og EQNR (2021–23)

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/FRO (også /aksje/HAFNI, /aksje/OET, /aksje/BWLPG, /sectors, /calibration, /health); src/osloquant/recorders/yahoo/kdata_recorder.py:31 (bruker Yahoos adj_close uten kontroll); src/osloquant/dashboard/datahealth.py:147 (revisjonen godtar faktorbevegelser > 0,0005)
- **Reproduser:** K=<feilsok>/kurser; PY=python; cd $K; $PY tr_check.py FRO HAFNI OET BWLPG DNB MOWI (sammenligner 1Å/YTD/6M på siden med totalavkastning regnet fra Yahoos noterte sluttkurser pluss Yahoos utbyttehendelser); $PY yahoo_divcheck.py EQNR (faktorendring per eks-dato i Yahoos egen adjclose); $PY adjcheck.py (det samme mot lagerets rå- og justert-tabell); test: cd $K/tests && $PY -m pytest -q -p no:cacheprovider test_kurser.py -k total_return
- **Forventet:** Justert serie = totalavkastning. FRO 1Å +107,0 % (Yahoo noterte sluttkurser + utbytter fra 7. nov. 2025 til 9. nov. 2026), HAFNI +61,1 %, OET +181,0 %, BWLPG +77,8 %. FRO YTD +122,9 %. FRO på eks-dagen 17. sep. 2026: totalavkastning +0,26 % (sluttkurs før 505,80, utbytte NOK 32,10, noterte kurser -6,09 %). EQNR fra 17. nov. 2021: totalavkastning +137,9 %. På hver eks-dato skal faktoren endre seg med 1 - utbytte/sluttkurs før, f.eks. EQNR 9. jan. 2023: 0,97367.
- **Vist:** FRO 1Å +82,0 %, HAFNI +41,8 %, OET +141,1 %, BWLPG +62,5 %. FRO YTD +97,3 %. FRO 17. sep. 2026: justert serie -5,45 %, et falskt kursfall. EQNR 9. jan. 2023: faktor 0,99720, som tilsvarer et utbytte på 0,90 (USD-beløpet) mot NOK-kurs 321,55. I lageret har 92 av 559 utbyttehendelser fra nov. 2021 til nov. 2026 en faktor som tilsvarer utbytte/9,6. Ytterligere 16 er også justert for lite. Alle gjelder selskaper som betaler i USD. Avkastningen som mangler, regnet inn i den justerte serien: 1Å FRO +14,1 %, OET +17,3 %, HAFNI +13,8 %, BWLPG +9,5 %, WAWI +10,4 %, BWO +7,4 %, SNI +5,6 %. 5Å EQNR +9,1 %, HAFNI +48,2 %, BWO +40,0 %, BWLPG +37,6 %. Kontrollene DNB, MOWI, SATS, TGS og KIT stemmer innen 0,2 prosentpoeng. /health lister bare MOWI, WWI, AKER, KID, GSF, PROT, TGS og BOUV som ujustert. NOK-beløpet for disse hendelsene regnes også om med valutakursen på nedlastingsdagen: FRO 11. juni 2026 er 14,92 i lageret og 14,58 hos Yahoo i dag (forhold 1,0232 = 9,625/9,407).
- **Årsak:** Yahoo lagrer disse utbyttene i USD. Kursjusteringen bruker USD-beløpet mot en kurs i NOK, mens beløpet som vises regnes om til NOK med dagens valutakurs. to_bars() skalerer hele baren med Yahoos adj_close/close uten kontroll. Utbytterevisjonen (D25) teller enhver faktorbevegelse over 0,05 % som justert, så en bevegelse som er ti ganger for liten går gjennom.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #6 Kalibrering: «Nå»-kursen (price_now) blåses opp med alt utbytte siden vurderingen når den noterte serien henger etter

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/judgements.py:259-260 (score: factor = raw_s/adj_s; price_now = adj_e*factor); vises i /calibration «Per vurdering» (Nå, mot kursmål, I båndet) og brukes til scenario_hit/Brier og beat_flat
- **Reproduser:** 1) Known-answer: cd <feilsok>\kalibrering\tests && <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_score.py::test_price_now_when_the_quoted_series_lags_the_adjusted_one (BUY @50 2025-05-02, utbytte 2 ex 2025-06-02, sluttkurs 45, noterte serie stopper 2026-01-30, asof 2026-03-10). 2) Ekte lagerdata (kopi): <venv python> ...\kalibrering\demo_pricenow.py scorer en ikke-logget DNB-vurdering 2026-02-02 til 2026-11-09.
- **Forventet:** Syntetisk: price_now 45,00, vs_target -25,0 %. Ekte data: DNB siste sluttkurs 325,80 (lagerets justerte 2026-11-09 = Yahoo chart-API, hentet 9. nov 19:36, close og adjclose 325,80); SATS 45,50 (Yahoo 45,50).
- **Vist:** Syntetisk: price_now 46,875 (= 45 x 50/48), vs_target -21,9 %. Ekte data: DNB price_now 346,00 (+6,2 %), vs_target +2,6 % i stedet for -3,4 %; SATS 46,94 i stedet for 45,50; MOWI 228,34 mot 221,80; ORK 110,03 mot 104,50.
- **Årsak:** Når noterte (raw) sluttkurs mangler på scoringsdatoen (oq record kjøres uten --raw: 63 av 64 noterte serier slutter 2026-10-19, den justerte går til 2026-11-09), ganges justert sluttkurs med raw/adj på VURDERINGSdatoen. Den faktoren er utbyttene mellom vurderingen og i dag, ikke utbyttene etter sluttdatoen. Kommentaren kaller det «approximate», men feilen er systematisk oppover. Den gjelder også endelige vurderinger hvis horisontslutten havner etter siste noterte dato. Da kan scenario_hit og Brier bli feil.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #7 KOG: utskillelsen av Kongsberg Maritime 15. apr. 2026 ligger i lageret som et kursfall på −18 %, og alle KOG-avkastninger over datoen blir feil

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /sectors (KOG-raden, «I år»), /aksje/KOG (YTD, 1Å, Maks), / («Research book mot kursmål», KOG «Siden synet»), scoring av KOG-vurderinger i judgements.score; src/osloquant/resources/data_exceptions.yaml (drop_returns har ingen KOG.OL 2026-04-15); src/osloquant/recorders/yahoo/kdata_recorder.py:23-38 (justert = Yahoos adj_close); src/osloquant/dashboard/datahealth.py:25 (BIG_MOVE 25 %, bare de siste 60 øktene)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_a8_kog_demerger.py" ; kilde: https://newsweb.oslobors.no/message/670655 (15. apr. 2026 07:44 UTC, «Vedtak om opptak til handel – Kongsberg Maritime ASA»), 670803 (16. apr., prospekt for særskilt notering); Yahoo chart API KOG.OL hentet 9. nov. 2026 (avkastning\yahoo\KOG.json)
- **Forventet:** Den justerte serien flat over eks-dagen (som AKSO 2024-11-25 i drop_returns). KOG YTD ≈ +67.6 % (EST: hele åpningsgapet regnet som utdelingen), 1Å ≈ +75.5 % (EST), «siden synet» 2. juni 2025 ≈ +21.5 % (EST)
- **Vist:** Justert dagsbevegelse 15. apr. 2026 −18.19 % (398.50 → 326.00; åpning 328.38 på 956 000 aksjer mot 20-dagerssnitt 1 422 140 – formen til en utdeling, ikke nyheter). /sectors KOG «I år» +37.1 %, 1Å +43.5 %, forsiden KOG «Siden synet» −0.6 %. Yahoo har ingen hendelse den dagen (bare utbytte 5.70 14. apr. og splitt 5:1 2025-06-03), og Yahoos adjclose faller like mye
- **Årsak:** Yahoo justerer ikke for utskillelser; lageret tar adj_close rett fra Yahoo, og unntaket mangler i data_exceptions.yaml. Datahelse lister bare dagsbevegelser over 25 % de siste 60 øktene, så et −18 %-gap fanges aldri. En skanning av hele lageret 2021–2026 (avkastning\gapscan.py: åpningsgap ≥ 12 % som holder til sluttkurs, volum under 20-dagerssnittet) finner bare dette ene tilfellet
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #8 Kurscachen fornyes bare når datoen på nyeste bar endres – en ny sluttkurs for samme dato vises ikke før neste handelsdag eller omstart

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/market.py:52-65 (lru_cache med nøkkel str(get_coverage(Stock1dAdjKdata)['last']), dvs. maks dato); src/osloquant/contract/recorder.py:224-233 (nyeste bar skrives over med overlap_days=10, force_update=True); gjelder alle sider som bruker mk.snapshot(): /, /aksje/<kode>, /sectors, /watchlist, /coverage, /screen, /desk
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_d1_snapshot_cache.py" (endrer bare kopien i avkastning\minihjem og setter verdien tilbake)
- **Forventet:** Etter at 17:30-kjøringen har skrevet den endelige baren: SATS 45.50 (Yahoo chart API, regularMarketTime 9. nov. 2026 16:25)
- **Vist:** Testverdien 44.10 fra en bar skrevet kl. 11 står fortsatt som «siste sluttkurs 9. nov. 2026» etter at baren er skrevet om til 45.50 – til en ny dato kommer neste kveld eller serveren startes på nytt. Morgensjekken dagen etter ville lest gårsdagens formiddagskurs
- **Årsak:** get_coverage()['last'] er maks timestamp (dato kl. 00:00), som er den samme for en halvferdig og en endelig bar. Samme feil når en ny aksje registreres samme dag som siste bar (KIT ble lagt til 9. nov.) og når en historikk skrives om uten ny dato
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #9 5Å er alltid av, og «Maks» er bare 26 måneder: kursbildet laster 800 dager, ikke fem år (D57) – duplikat av #12

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/KIT (og alle aksjer); src/osloquant/dashboard/market.py:54 (start = now − 800 dager); charts.py:81-82, 111-121 (CHART_SESSIONS = 1260, 5Å = 1250 økter); stockpage.py:114 (teksten «for kort historikk i lageret»); stockpage.py:264 («5 års sluttkurser er lastet»)

### #10 5Å er slått av på alle aksjer og «Maks» viser bare ~2,2 års avkastning – grafen har 800 dager, ikke fem år – duplikat av #12

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/SATS (og alle aksjesider, perioderaden i baren og under grafen); src/osloquant/dashboard/market.py:54 (load_panel(start=now-800 dager)); charts.py:111-141 long_chart/period_ranges; tekst «5 års sluttkurser er lastet» i stockpage

### #11 5Å er alltid av og «Maks» er bare 2,2 år: aksjesiden laster 800 dager, ikke fem år – duplikat av #12

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/<KODE> (alle) ; market.py:54 (load_panel start = nå − 800 dager), charts.py:81-83, :116-119 (long_chart/period_ranges), stockpage.py:264 (tekst «5 års sluttkurser er lastet»), stockpage.py:389 (Kurs før i utbyttetabellen bruker samme serie)

### #12 Kursøyeblikksbildet holder bare 800 dager: 5Å er slått av for alle aksjer med feil begrunnelse, og «Maks» betyr bare fra 2. sep. 2024

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/EQNR (og alle aksjesider), periodeknappene under grafen i Oversikt og i toppbaren; src/osloquant/dashboard/market.py:54 (load_panel(start=now-800 dager)); src/osloquant/dashboard/stockpage.py:114 og 264; charts.py:82 og 111 (CHART_SESSIONS=1260 forutsetter 5 år)
- **Reproduser:** Åpne /aksje/EQNR, hold over 5Å og Maks. Test: cd $K/tests && $PY -m pytest -q -p no:cacheprovider test_kurser.py -k five_year. Forventet verdi: sqlite-spørring mot testhjem/data/yahoo_stock_1d_adj_kdata.db, close[-1]/close[-1251]-1.
- **Forventet:** Lageret har EQNR fra 3. jan. 2000 og SATS fra 13. des. 2019, altså over 1250 økter. 5Å (1250 økter fra 17. nov. 2021, lagerets justerte serie): EQNR +119,7 %, SATS +94,5 %, KOG +615,4 %, DNB +111,6 %, KIT +416,3 %, MOWI +14,4 %. Yahoos adjclose på samme dato gir +120,6 %, +94,5 %, +617,6 %, +114,6 %, +416,3 % og +14,5 %. «Maks» skal starte ved grafens første sluttkurs, som er 1260 økter tilbake.
- **Vist:** 5Å er grået ut med teksten «for kort historikk i lageret for 5Å (første kurs 2. sep. 2024)». «Maks» viser for EQNR +56,9 %, for SATS +125,2 % og for KIT +171,0 %, alle «fra 2. sep. 2024». Grafteksten sier «5 års sluttkurser er lastet». Følgefeil: i utbyttetabellen står «Kurs før» som «–» for eks-datoer før 2. sep. 2024 (DNB 2019–2024), og multippelhistorikken viser bare 2024 og 2025.
- **Årsak:** mk._snapshot_cached laster bare 800 kalenderdager. long_chart klipper til 1260 økter, men serien den får er ca. 548 økter lang.

### #13 Utbyttetabellen regner «Kurs før» og yield på justert kurs, så eldre yield blir for høy

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/DNB/regnskap/utbytte (og /aksje/EQNR/regnskap/utbytte); src/osloquant/dashboard/stockpage.py:377-380 (dividends_card bruker ctx['closes'], som er justert)
- **Reproduser:** Åpne /aksje/DNB/regnskap/utbytte og les raden 30. april 2025. Sammenlign med Yahoos noterte sluttkurs før eks-dato: $PY yahoo_divcheck.py DNB EQNR (kolonnen close_before). Test: test_kurser.py -k dividend_yield.
- **Forventet:** DNB 30. apr. 2025: kurs før 269,90, yield 16,75/269,90 = 6,2 %. DNB 22. apr. 2026: 308,30 og 5,8 %. EQNR 18. nov. 2024: 271,10 og 7,75/271,10 = 2,9 % (Yahoos noterte sluttkurser).
- **Vist:** DNB 30. apr. 2025: 238,37 og 7,0 %. DNB 22. apr. 2026: 290,30 og 6,2 %. EQNR 18. nov. 2024: 236,13 og 3,3 %. Hover sier «siste sluttkurs før eks-dato (justert, forsinket)».
- **Årsak:** Den justerte sluttkursen før eks-dato er senket av alle senere utbytter. Et utbytte i dagens kroner delt på en senket kurs gir for høy yield.

### #14 «P/E ved kurs X» i Nøkkeltall per år viser multippelen ved lett-casens byggekurs, ikke ved kursen som står i etiketten

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/EQNR/regnskap (Nøkkeltall per år); src/osloquant/dashboard/render.py:462-471 (key_figures setter etiketten med dagens px, men verdiene er lc['multiples'])
- **Reproduser:** Åpne /aksje/EQNR/regnskap og sammenlign raden «P/E ved kurs 384.70» med flisen P/E (LTM) i Oversikt. Test: test_kurser.py -k keyfigures.
- **Forventet:** P/E ved 384,70 er 8,3x (live_multiples: børsverdi 911,5 mrd / USDNOK 9,3001 / resultat 11,80 mrd USD). For SATS ved 45,50 er den 15,7x, for BAKKA ved 434,80 22,6x.
- **Vist:** EQNR: «P/E ved kurs 384.70 8.8x». 8,8x er multippelen ved byggekursen 406,60 den 4. nov. EV/EBIT, P/B og FCF-yield har samme feil. SATS: «P/E ved kurs 45.50 15.5x». BAKKA: 22.3x. Siden viser altså to ulike P/E for samme kurs.
- **Årsak:** key_figures tar imot px for etiketten, men leser multiplene fra lett-casen, som ble regnet ved kursen den ble bygget på.

### #15 Regnskapet i lageret mangler 3. kvartal for 11 selskaper som har rapportert: P/E i Oversikt er regnet på tall til 30. juni uten varsel

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/MOWI og /aksje/BAKKA (Oversikt: P/E (LTM), EPS, P/S, P/B; Verdsettelse); src/osloquant/dashboard/lightcase.py:367 (varselet skylder på Yahoo); datahealth.py (ingen kontroll)
- **Reproduser:** $PY $K/fetch_ts.py MOWI BAKKA (Yahoo fundamentals-timeseries). Sammenlign med sqlite: select max(report_date) from income_statement where code='MOWI' and report_period='quarter' (testhjem/data/yahoo_finance.db). Hele listen står i $K/stale_quarters.json. Test: test_kurser.py -k newest_quarter.
- **Forventet:** Yahoo har kvartaler til 30. sep. 2026 for AUTO, BAKKA, BOUV, HEX, MOWI, ODF, ODL, OKEA, SALM, WAWI og WWI. MOWI: resultat siste 12 mnd. til 30. sep. 2026 er EUR 716,6 m, som gir P/E ca. 15,6x ved 221,80 og EURNOK 10,4498. BAKKA: DKK 931,4 m, som gir ca. 19,8x ved 434,80 og DKKNOK 1,3967.
- **Vist:** MOWI P/E (LTM) 17,6x og EPS 1,21 EUR, «resultat LTM til 30. juni 2026», med «Siste rapport 4. nov. 2026» i samme rutenett. BAKKA 22,6x. Oversikt har ikke noe varsel. Lett-casens varsel sier «Yahoo has quarterly statements only to 2026-06-30», men det stemmer ikke: Yahoo har Q3, det er lageret som ikke er oppdatert. /health nevner det ikke.
- **Årsak:** oq record --finance er ikke kjørt etter rapportene i oktober og november. Siden og /health sammenligner ikke lagerets nyeste kvartal med siste rapport.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #16 Kalibrering: totalavkastningen mister utbyttet når den noterte serien mangler på vurderingsdatoen

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/judgements.py:255 og :258 (base_close = adj_s når raw mangler; tsr = adj_e/adj_s*base_close/price - 1); /calibration Totalavk., mot OSEBX, Retning
- **Reproduser:** cd ...\scratchpad\feilsok\kalibrering\tests && <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_score.py::test_tsr_keeps_the_dividend_when_the_quoted_series_is_missing (SELL BBB @50 2025-03-03, utbytte 2 ex 2025-06-02 ved 50, sluttkurs 45, ingen notert serie for BBB).
- **Forventet:** tsr = 45/48 - 1 = -6,25 % (kjøpt til 50, utbytte 2 reinvestert til 48: 1+2/48 aksjer x 45 = 46,875); meravkastning mot OSEBX -16,25 %
- **Vist:** tsr = 45/50 - 1 = -10,0 %; meravkastning -20,0 % (utbyttet er borte)
- **Årsak:** Uten raw på startdatoen brukes justert sluttkurs som «dagens sluttkurs». Da blir tsr = adj_e/kurs - 1, en ren kursavkastning. I lageret har OUTLT ingen notert serie i det hele tatt, og alle vurderinger logget etter 2026-10-19 (blant dem Claudes ti fra 2. nov.) har ingen notert startkurs. Ved neste ex-dato forsvinner utbyttet fra deres totalavkastning. Retning og Brier bygger på dette tallet.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #17 Dagsendringen i kursbaren regnes mot utbyttejustert forrige sluttkurs, så den er feil på hver eks-dag – duplikat av #30

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/<kode>, kursbaren; src/osloquant/dashboard/stockpage.py:121-126, 148-149 (bar_html, «endring mot forrige sluttkurs»); src/osloquant/signals.py:486 (chg_1d på justerte kurser); samme tall i /sectors og /watchlist «Dag» (market.py:80) uten merket «inkl. utbytte»

### #18 «12 m lav / høy» og «52 ukers høy» er utbyttejusterte kurser som aldri ble handlet, og avviker fra både Yahoo og noterte sluttkurser – duplikat av #31

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/<kode>/oversikt → Nøkkeltall (src/osloquant/dashboard/stockpage.py:240-242); /aksje/<kode>/teknisk → 52 ukers høy, 60 dagers høy/lav (technicals.py:90-104); grafens hover «Sluttkurs» for historiske dager (charts.py:123-124)

### #19 «Prisen krever»: KOG sammenlignes med en omsetningsvekst som går over et perimeterbrudd (−0.3 %/år) og havner på kandidatlisten

*Alvor middels, sikkerhet middels; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /screen (KOG under «Kandidater for full dekning» og Industrials & materials); src/osloquant/dashboard/screen.py:58-76; lightcase.py:200-219 (history: CAGR fra første til siste år uten bruddsjekk)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_c2_screen_perimeter.py" (leser testhjem\cases\KOG.json uten å skrive)
- **Forventet:** Ingen sammenligning, eller et merket brudd, når årstabellen har et år med −39 %. KOGs omsetning i lett-casen (bygget 4. nov. 2026): 2022 31 803, 2023 40 617, 2024 24 648, 2025 31 562 NOK m. 2024–25 er etter alt å dømme videreført virksomhet uten Kongsberg Maritime: utskilt i april 2026 (NewsWeb 670655), og resultatet for 2024 (5 126) er høyere enn EBIT (3 854)
- **Vist:** KOG: prisen krever +7.4 %/år mot −0.3 %/år (2022–2025), spenn +7.6 pp, «prisen krever mer enn historikken», og står som kandidat for full dekning
- **Årsak:** Yahoos årstall blander perimetre (eldre år fra gamle rapporter, nyere omarbeidet), og history() regner CAGR fra første til siste år uten å se etter brudd. ELK har samme mønster (−28.4 %/år etter salget av Silicones), men får «–» fordi ROIC er under WACC
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #20 «Prisen krever» regner på lett-casens byggekurs, men siden sier ikke når den ble bygget

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /screen ; src/osloquant/dashboard/screen.py:41-79 (case['multiples']['ev'] og reverse fra byggingen); render.py:1300 («Kurs: Yahoo via lageret (daglig sluttkurs, forsinket)» uten dato, «se datoen på hver aksjeside»)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\screen_price.py" ; åpne /screen og finn AutoStore
- **Forventet:** Siden sier hvilken kurs og dato kravet gjelder (eller regner på dagens kurs). AUTO er bygget 4. nov. 2026 ved 14.73, og lageret har 15.75 9. nov. (+6.9 %). Ved dagens kurs krever prisen vekst på eller over kapitalkosten (EST: samme regnskap og valutakurs), ikke +9.0 %/år. AKRBP 354.00 → 313.00 (−11.6 %), HEX +11.7 %
- **Vist:** AUTO «+9.0 % /år siste 12 mnd … prisen krever mer enn historikken», uten dato. 64 caser er bygget 4. nov. og KIT 9. nov., så tallene er fra to ulike dager
- **Årsak:** Skjermen leser case-filene slik oq case build skrev dem, mens kildelinjen antyder dagens sluttkurs
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #21 Regnskap → Nøkkeltall: «P/E ved kurs 45.50» viser P/E ved lett-casens gamle kurs (15.5x), Oversikt viser 15.7x for samme kurs – duplikat av #14

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/SATS/regnskap (tabellen Nøkkeltall per år, radene «P/E/EV/EBIT/P/B/FCF-yield/ROE/ROIC ved kurs …»); src/osloquant/dashboard/render.py:471 (key_figures)

### #22 «kurs nå» / «Nå» på /review og /calibration er kursen ved horisonten for endelige vurderinger, ikke dagens kurs

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /review (overskriften per vurdering), /calibration (tabellen Per vurdering, kolonnen «Nå»); src/osloquant/dashboard/review.py:108-110, render.py:1045, judgements.py:240-260 (price_now = kurs ved min(asof, horisontslutt))
- **Reproduser:** Åpne /review: «KOG #2 – HOLD 369.5 fra 351.86 (2. juni 2025) · kurs nå 315.70 … final». Forsiden samme dag: KOG 349.60. Kjør tester/t_tid_og_kurs.py (sjekk 2).
- **Forventet:** Dagens sluttkurs 349.60 (9. nov. 2026), eller etiketten «sluttkurs ved horisonten (2. juni 2026)» for endelige vurderinger
- **Vist:** «kurs nå 315.70» og kolonnen «Nå» = 315.70 (scored_to 2026-06-02)
- **Årsak:** score() setter price_now til kursen på slutten av scoringsvinduet; for status final er det horisontslutt, men visningen kaller det «nå».
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #23 Klokkeslett i to tidssoner uten merking: «Generert» i bunnteksten er maskinens lokaltid, «Logget», desk og «hentet» er Oslo-tid

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** Alle sider; src/osloquant/dashboard/render.py:216 (dato_tid(datetime.now()) naiv lokaltid) mot dates.py:41-57 (stempel/dato_tid konverterer UTC til Europe/Oslo)
- **Reproduser:** På denne maskinen (tidssone GMT, UTC+0): logg en vurdering kl. 19:32 lokal tid (POST /stock/SATS/judge på testhjem-flyt) og åpne /aksje/SATS/vurdering. Kjør tester/t_tid_og_kurs.py (sjekk 1).
- **Forventet:** Samme tidssone overalt (eller sonen navngitt): en rad logget ett minutt før siden ble laget skal vise et tidspunkt før «Generert»
- **Vist:** Vurderingshistorikk: «#12 … Logget 9. nov. 2026 20:32»; bunntekst: «Generert 9. nov. 2026 19:45». Forsiden: «hentet 9. nov. 2026 18:47» og desk «kl. 18:48» (Oslo) mot «Generert 19:26» (GMT)
- **Årsak:** D58 konverterer UTC-stempler til Oslo-tid, men page() skriver datetime.now() uten sone. På en maskin utenfor norsk tid (eieren er på utveksling i Lisboa, GMT) sprikerer det med en time.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #24 «P/E ved kurs 45.50» osv. i Nøkkeltall per år er regnet på lett-casens eldre kurs – duplikat av #14

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/<KODE>/regnskap ; render.py:465-472 (key_figures setter dagens px i etiketten, verdiene er lc['multiples'])

### #25 PROT: LTM-kolonnen heter «LTM til 31. des. 2025» og EBIT-marginen blander to perioder

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/PROT/regnskap ; render.py:455 (head bruker pr['ebit']['period']), :460 (mg(ltm ebit, ltm revenue)), render.py:401 og stockpage.py:324 (Kapitalstruktur «LTM = …»)
- **Reproduser:** GET /aksje/PROT/regnskap. Lett case-tabellen under Verdsettelse på samme side: Omsetning 15 207 «LTM til 30. sep. 2026», EBIT 3 613 «LTM til 31. des. 2025», Resultat 2 450 «LTM til 30. sep. 2026». Test: test_key_figures_ltm_header_is_the_revenue_period.
- **Forventet:** Kolonnen merket med omsetningens/resultatets periode (LTM til 30. sep. 2026) og EBIT merket for seg; EBIT-margin bare der teller og nevner er samme periode (FY 2025: 3 613/14 248 = 25.4 %).
- **Vist:** Overskrift «LTM til 31. des. 2025» over tall til 30. sep. 2026; «EBIT-margin 23.8 %» = 3 613 (FY 2025) / 15 207 (LTM sep. 2026). For et forsikringsselskap vises også EBIT, EBIT-margin, Netto gjeld og Fri kontantstrøm, som ikke er meningsfulle (EV/EBIT er korrekt skjult).
- **Årsak:** Én periode (EBIT-ens) brukes som overskrift for hele LTM-kolonnen, og margin regnes uten å sjekke at periodene er like.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #26 KIT: lett case henter netto gjeld fra 31. mars 2026 og merker egenkapitalen per 30. sep. 2026 med samme dato

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/KIT/verdsettelse og /aksje/KIT/regnskap ; lightcase.py:324-325 (_latest per kolonne), :374 ("date": nd_date or eq_date)
- **Reproduser:** GET /aksje/KIT/verdsettelse: «Netto gjeld 17 \| 31. mars 2026», «Egenkapital 377 \| 31. mars 2026». Balanse-fanen samme side: egenkapital 377 er Q3 2026 (30. sep.), Q1 2026 er 351; netto gjeld mangler hos Yahoo for 2025 og Q2–Q3 2026 (kontanter 146 > gjeld 114 ved årsslutt 2025). Test: test_light_case_balance_date_belongs_to_the_equity_shown.
- **Forventet:** Egenkapital 377 merket 30. sep. 2026; netto gjeld fra samme dato eller tydelig merket «fra 31. mars 2026 – Yahoo mangler nyere» (sidens egen balanse: rentebærende gjeld 134 − kontanter 96 = 38 EUR m per 30. sep. 2026, som indikasjon – Yahoos definisjon kan avvike).
- **Vist:** Begge linjene datert 31. mars 2026; EV (EUR m) 1 903 og EV/EBIT 18.7x bruker 6 måneder gammel netto gjeld uten merknad, og kvalitet «A».
- **Årsak:** Netto gjeld og egenkapital hentes hver for seg som siste ikke-tomme verdi; balansedatoen tar netto gjelds dato. Yahoo utelater netto gjeld når selskapet har netto kontanter.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #27 Short «siste 30 dager» måles fra siste registerhendelse, ikke fra i dag

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/<KODE>/eiere ; insiders.py:185-191 (short_change), server.py:280, render.py:532
- **Reproduser:** GET /aksje/SATS/eiere: «0.00 % av aksjene shortet offentlig (10. aug. 2026), -0.70 prosentpoeng siste 30 dager». ELK: «(15. juni 2026), -0.76 prosentpoeng siste 30 dager». python krasj/shortchk.py. Test: test_short_change_is_measured_back_from_today.
- **Forventet:** Endring 10. okt.–9. nov. 2026: SATS 0.00, ELK 0.00, TGS +0.45 (2.03 → 2.48); eller teksten «-0.70 pp de 30 dagene før 10. aug.».
- **Vist:** SATS −0.70, ELK −0.76, TGS +0.56 – presentert som de siste 30 dagene.
- **Årsak:** cut = siste hendelsesdato − 30 dager; forsidens short_moves har en «recent»-sjekk, aksjesiden ikke.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #28 Odds-kortet har hardkodet «64 aksjer», mens lageret nå har 65

*Alvor lav, sikkerhet middels; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/render.py:668, 690, 692 (også 320, 513, 743)
- **Reproduser:** Kortet Utfallsodds på /aksje/SATS: overskriften er «Historiske tilfeller, alle 64 aksjer» og foten «Bare dagens 64 aksjer». Snapshotet 9.11.2026 har 65 kolonner (KIT kom til i D57).
- **Forventet:** Antallet bør hentes fra dataene, slik foten allerede gjør med u0.extra['stocks'].
- **Vist:** 64. 12-månederstellingen er 64 i dag bare fordi OUTLT ennå ikke har noe 12-månederstilfelle.
- **Årsak:** Tallet er skrevet rett inn i teksten.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #29 RSI-raden viser «nan» når serien er flat

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/technicals.py:83-85; signals.py:45-49 (0/0)
- **Reproduser:** rene/test_perioder_teknisk_kjent.py::test_rsi_flat_series_prints_nan (30 like sluttkurser). Feilen ligger latent: ingen aksje treffer i dag.
- **Forventet:** «–» (eller 50).
- **Vist:** «nan»
- **Årsak:** up/dn = 0/0.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #30 På eks-dagen viser toppbaren, /sectors og forsiden totalavkastning som «endring mot forrige sluttkurs», ikke kursendringen

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** Toppbaren på /aksje/<kode>, 1D på /sectors og på forsiden; src/osloquant/signals.py:486 (chg_1d på justert serie), src/osloquant/dashboard/stockpage.py:125-126 (NOK-endringen regnes fra den), src/osloquant/dashboard/market.py:80
- **Reproduser:** cd $K/tests && $PY -m pytest -q -p no:cacheprovider test_kurser.py -k ex_date (panelet kuttet 6. nov. 2026 for AKER). Yahoo-data: $K/yahoo/AKER_1mo.json.
- **Forventet:** AKER 6. nov. 2026 (ex NOK 29): notert 1088,00 → 1074,00, altså -14,00 (-1,3 %) (Yahoo chart API).
- **Vist:** Lagerets justerte 1059,00 → 1074,00. Baren ville vist +15,00 (+1,4 %) med teksten «endring mot forrige sluttkurs», og /sectors 1D +1,4 %.
- **Årsak:** Forrige sluttkurs i den justerte serien er trukket ned med utbyttet på eks-dagen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #31 «12 m lav / høy» viser justerte sluttkurser som aksjen aldri har handlet til

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/DNB (Oversikt, Nøkkeltall); src/osloquant/dashboard/stockpage.py:241-242
- **Reproduser:** Åpne /aksje/DNB og les 12 m lav / høy. Sammenlign med Yahoos noterte sluttkurser for de siste 250 øktene i $K/yahoo/DNB_5y.json (beregnet i økten). Test: test_kurser.py -k twelve_month.
- **Forventet:** Notert, 10. nov. 2025 til 9. nov. 2026: DNB 260,60 / 326,70 (laveste intradag 259,00), PROT 400,00 / 556,00, TGS 85,00 / 159,00, KOG 229,15 / 423,50, SATS 35,25 / 46,95.
- **Vist:** DNB 245,38 / 326,70, PROT 395,53 / 531,25, TGS 81,29 / 154,02, KOG 225,96 / 417,60, SATS 34,17 / 46,23. Hover sier «justert».
- **Årsak:** Utvalget er closes.iloc[-250:] fra den justerte serien. Kurser før et utbytte er senket.

### #32 Multippelhistorikken (P/E og P/S per årsslutt) bruker justert årssluttkurs og dagens valutakurs

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/DNB/regnskap (grafen «P/E og P/S ved hvert årsslutt»); src/osloquant/dashboard/stockpage.py:295-307 (_multiple_points); lightcase.export_statements prices_ye fra justert øyeblikksbilde og fx på siste kursdato
- **Reproduser:** Test: test_kurser.py -k multiples_history. Hent Plotly-dataene fra $K/pages/aksje_DNB.html. Forventet verdi: Yahoos noterte sluttkurs 31. des. 2024 × aksjer fra årsbalansen / årsresultat (sqlite testhjem/data/yahoo_finance.db).
- **Forventet:** DNB 2024: 226,90 × 1482,7 m / resultat = 7,67x. SATS 2024: 16,62x (26,50). EQNR 2024: 265,40 NOK / USDNOK 11,3276 (31. des. 2024, lageret) gir 7,26x.
- **Vist:** DNB 2024: 6,77x. SATS 2024: 15,84x. EQNR 2024: 7,83x (justert kurs og USDNOK 9,3001 fra 4. nov. 2026). Grafen viser bare 2024 og 2025, se 800-dagersfunnet.
- **Årsak:** Årssluttkursene kommer fra den justerte serien, og to_rep bruker valutakursen på dagens kursdato for alle år.

### #33 Datoen for netto gjeld brukes også som dato for egenkapitalen: feil dato i P/B-kilden og feil kvalitetskarakter

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/KIT (P/B-hover, Verdsettelse «Egenkapital 377 31. mars 2026»), /screen (GJF karakter B); src/osloquant/dashboard/lightcase.py:374 ('date': nd_date or eq_date) og 297 (quality); stockpage.py:91
- **Reproduser:** Hold over P/B på /aksje/KIT. sqlite: select report_date,total_equity,net_debt from balance_sheet where code in ('KIT','GJF','BWO') (testhjem). $PY -c "from osloquant.dashboard import lightcase as l; ...quality(json.load(open('cases/GJF.json')))". Test: test_kurser.py -k pb_source.
- **Forventet:** KIT: egenkapitalen 377,2 m EUR er fra 30. sep. 2026, og P/B 5,00x er regnet på den. Netto gjeld 17,2 m er fra 31. mars 2026. GJF (finans, bruker ikke netto gjeld): egenkapital 25 063 m fra 30. sep. 2026, som gir karakter A.
- **Vist:** KIT: «egenkapital minus minoriteter 31. mars 2026». GJF: karakter B med «the balance sheet (net debt, equity) is from 2024-12-31: EV and returns use old capital». BWO: EV bruker netto gjeld fra 31. des. 2023 (merket), og egenkapitalen fra 30. juni 2026 er merket 2023. Samme datoavvik for BONHR og SUBC.
- **Årsak:** compute() lagrer én dato for balansen, og det er datoen for netto gjeld. Yahoo dropper net_debt-linjen i nyere kvartaler, så den blir eldre enn egenkapitalen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #34 P/E, EPS, P/S og EV/EBIT er merket «LTM» selv når tallet er siste hele år

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/OUTLT (Oversikt-fliser, Nøkkeltall, Regnskap Kapitalstruktur); src/osloquant/dashboard/stockpage.py:223, 251, 320
- **Reproduser:** Åpne /aksje/OUTLT og hold over P/E (LTM). Hoveren sier «resultat år til 31. des. 2025». Test: test_kurser.py -k fy_figure (syntetisk lett case med period 'FY to 2025-12-31').
- **Forventet:** Etiketten skal si at det er siste hele år («P/E (år 2025)») når profit.period starter med «FY». Selskapet ble notert i sept. 2026 og har ingen kvartaler i lageret.
- **Vist:** «P/E (LTM)», «EPS LTM (NOK)», «P/S (LTM)», «EV/EBIT (LTM)» over tall for året til 31. des. 2025.
- **Årsak:** Etikettene er faste strenger. Bare hoveren bruker periode().

### #35 Multiplene i Oversikt for selskaper som rapporterer i USD, EUR eller DKK bruker valutakursen fra dagen lett-casen ble bygget, og hoveren nevner ikke kursen

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/EQNR (P/E (LTM), P/S, P/B); src/osloquant/dashboard/stockpage.py:74-76 (fx = lc['currency']['fx'])
- **Reproduser:** sqlite testhjem/data/yahoo_currency_1d_kdata.db: USDNOK 9. nov. 2026 = 9,4102; i cases/EQNR.json er fx 9,3001 (4. nov.). Regn 384,70 × 2369,42 m / 9,4102 / 11,804 mrd.
- **Forventet:** P/E ved 384,70 med USDNOK 9,4102 (9. nov., lageret) er 8,2x.
- **Vist:** 8,3x (med USDNOK 9,3001 fra 4. nov.). Hoveren nevner ikke valutakurs eller dato. BAKKA: DKKNOK 1,3967 mot 1,4090.
- **Årsak:** live_multiples tar valutakursen fra lett-casen, men kursen fra i dag.

### #36 /health melder at rå-tabellen er à jour («siste 9. nov. 2026»), men 63 av 64 aksjer slutter 19. okt. 2026

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /health (Lageret: «raw : siste 9. nov. 2026, 64 instrumenter»); src/osloquant/dashboard/datahealth.py:105-112 (get_coverage gir høyeste dato over alle aksjer)
- **Reproduser:** sqlite testhjem/data/yahoo_stock_1d_kdata.db: select code,max(timestamp) from stock_1d_kdata group by code.
- **Forventet:** «raw: 63 av 64 aksjer slutter 19. okt. 2026 (bare KIT til 9. nov.), OUTLT mangler.» Kalibreringen leser rå-tabellen (se funnet om dagens kurs i kalibreringen).
- **Vist:** «raw : siste 9. nov. 2026, 64 instrumenter, 304632 rader» uten varsel.
- **Årsak:** Maksimum over alle aksjer skjuler at de fleste ligger etter. Rå-tabellen tas bare opp med oq record --raw.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #37 GSF: rå-tabellen har en splitt 2:1 som ikke er rettet bakover, og StockAction har ingen splitt-rad for den

*Alvor lav, sikkerhet middels; status: avvist av kontrollen.*

- **Hvor:** testhjem/data/yahoo_stock_1d_kdata.db og yahoo_stock_action.db (GSF); påvirker judgements.score (raw_s/raw_e) og utbytterevisjonen på /health
- **Reproduser:** sqlite: select timestamp,close from stock_1d_kdata where code='GSF' and timestamp between '2026-04-15' and '2026-04-22'. Sammenlign med stock_1d_adj_kdata. select * from stock_action where code='GSF' and split>0.
- **Forventet:** Rå-tabellen er splitt-justert slik Yahoos Close er (ca. 35,8 den 17. apr. 2026), eller det finnes en splitt-rad 20. apr. 2026.
- **Vist:** Rå: 71,60 (17. apr.) → 34,28 (20. apr.). Justert er sammenhengende: 35,96 → 34,28. Forholdet justert/rå er 0,5023 til og med 17. apr., deretter 1,0. Ingen GSF-splitt i StockAction.
- **Årsak:** Rå-tabellen ble ikke lastet ned på nytt etter splitten, og splittraden ble aldri lagret.
- **Kontrollen:** There is no split. The drop on 20 Apr 2026 from 71.60 to 34.28 is an extraordinary dividend of NOK 35.63715 per share. Yahoo publishes it as a dividend event, and we have stored it as a dividend row in StockAction (stock_ol_GSF_2026-04-20).

The raw table is correct as it stands. It is identical to Yahoo's unadjusted Close (71.60 on 17 Apr), and Yahoo's Close is never adjusted for dividends. The expected "about 35.8 on 17 Apr in the raw table" is therefore wrong, and so is "a split row on 20 Apr".

The suggested fix is harmful. A /health rule that flags a jump of more than 20 % in the adjusted/raw ratio without a split row would raise a false alarm on correctly stored large dividends like this one.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #38 RSI 14 avviker fra Wilder på korte historikker: OUTLT viser 63, Wilder gir 58

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/OUTLT/teknisk (alle nye aksjer); src/osloquant/signals.py:45-49 (ewm(alpha=1/14, adjust=False) startet på første endring); technicals.py:83-85 (vises fra 16 sluttkurser, med teksten «Wilder-glatting»)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_a4_rsi_seed.py"
- **Forventet:** 58.0 på OUTLTs 33 sluttkurser (Wilder: snittet av de første 14 endringene som start, deretter (n−1)/n-glatting, som TA-Lib og TradingView). Lange serier gir likt resultat (SATS 65.3 begge veier)
- **Vist:** 63 (63.2)
- **Årsak:** EWM-startverdien er første endring alene, og den veier tungt de første rundt 50 øktene

### #39 Samme 12-måneders topp vises med to tall: Oversikt 46.23 (sluttkurs) og Teknisk «52 ukers høy» 46.90 (intradag-høy), ingen av dem merket – duplikat av #31

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/SATS (Oversikt → Nøkkeltall «12 m lav / høy») og /aksje/SATS/teknisk («52 ukers høy»); technicals.py (bruker high-kolonnen), stockpage.py nøkkeltall (bruker close)

### #40 «Kurs nå» / «Nå» på feilgjennomgang og kalibrering viser kursen ved horisonten for endelige vurderinger – duplikat av #22

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /review og /calibration (Per vurdering) ; review.py:109-110, render.py:1049

### #41 Desk-sidens datakvalitet viser UTC-tid som norsk tid (én time feil)

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /desk og /desk/run/<id> ; deskpage.py:81 (str(q['asof'])[:19] kutter «Z»)
- **Reproduser:** GET /desk: «✓ børsmeldinger (NewsWeb): 9. nov. 2026 17:47 – fetched 9. nov. 2026 18:47» – samme hentetidspunkt to ganger. Test: test_desk_quality_line_shows_utc_stamps_as_oslo_time.
- **Forventet:** Begge 18:47 (Oslo, UTC+1 i november), som «hentet 9. nov. 2026 18:47» på aksjesiden.
- **Vist:** 17:47 og 18:47 på samme linje.
- **Årsak:** [:19] fjerner «Z», så datopasset tolker stempelet som lokal tid.

### #42 Bunnteksten «Generert» bruker maskinens lokale tid, resten av siden Oslo-tid – duplikat av #23

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: alle sider ; render.py:216 (dato_tid(datetime.now())), mot datahealth.py:275 og :390

### #43 ELK: «Etter rapporten» viser «Vekst prisen krever −38.6 %» mens lett case på samme side sier at ingen vekstrate gjelder

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/ELK/rapporter ; afterreport.py (block_html viser lagret snapshot fra cases/afterreport/ELK.json, kjørt 3. nov.)
- **Reproduser:** GET /aksje/ELK: Rapporter → Etter rapporten: «Vekst prisen krever \| -38.6 % \| -38.6 %». Verdsettelse → Lett case (bygget 4. nov.): «5 % return on capital is below the 9.0% cost of capital … not for growth»; cases/ELK.json har reverse.implied_g = null, kind below_wacc. SATS: after-report −0.4 % mot lett case −0.2 %.
- **Forventet:** Etter-rapport-boksen sier at lett case er bygget på nytt etter kjøringen (4. nov. 19:34 > 3. nov. 20:26) og viser «–» der dagens regel ikke gir en vekstrate.
- **Vist:** Et tall fra den gamle regelen (før D42) uten merknad, i strid med teksten to faner unna.
- **Årsak:** Snapshotet lagres med verdiene fra kjøringstidspunktet og vises uten sjekk mot dagens lett case.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

## Feil logikk

### #44 Utfallsodds gir dommen «klart mot kill-nivået» når det ikke finnes noen simulering (nylig notert aksje, OUTLT)

*Alvor høy, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /aksje/OUTLT (kortet Utfallsodds); src/osloquant/dashboard/render.py:673-681 (odds_block: decided/share/gap/lean); src/osloquant/dashboard/odds.py:182-195 (_case_odds_cached setter note='' selv om simulate/analogues sier 'too little history'); src/osloquant/dashboard/desk.py:603-605 (samme tilfelle i desk-teksten)
- **Reproduser:** 1) Åpne /aksje/OUTLT og les kortet «Utfallsodds». Alle cellene for simulering og historikk viser «–» (too little history), men break-even-linjen sier «Simuleringen over 12 mnd (EST): – – klart mot kill-nivået». 2) cd <feilsok>\odds-dcf\rene && PYTHONPATH=<worktree>/src <venv python> -m pytest -q -p no:cacheprovider test_odds_kjent.py -k "new_listing or without_decided". Begge feiler: én for en ny notering med 120 økter, én for et kjent 12-månedersutfall på mål 0 %, kill 0 % og ingen 100 %.
- **Forventet:** Når ingen baner er avgjort (0 av 0) skal kortet ikke ta stilling til noen retning. Det skal vise «for kort historikk (N økter) – ingen simulering» eller la break-even-dommen være ute.
- **Vist:** «Simuleringen over 12 mnd (EST): – – klart mot kill-nivået.» står på OUTLT (Outlet, kopi) uten at det finnes én eneste simulert bane. I desk-teksten blir samme tilfelle «simuleringen 12 mnd: 0 % avgjorte (ingen av nivåene nås)». Det påstår at nivåene ikke nås, når det egentlig mangler data.
- **Årsak:** decided = s12.target + s12.kill blir NaN (eller 0). Uttrykket `share = s12.target / decided if decided else nan` gir da NaN. Både abs(NaN) < 0.05 og abs(NaN) < 0.15 er False, så koden havner i else-grenen. Der er gap > 0 også False, og resultatet blir «klart mot kill-nivået». CaseOdds.note settes bare når kursen ligger utenfor nivåene, ikke når simuleringen har n = 0.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #45 Oppdateringsløkka (D48) aksepterer en oppdatering etter at horisonten er ute og scorer den i etterpåklokskap

*Alvor høy, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/updates.py:80 (write tar latest_by_code uten horisontsjekk), :110-118 (scoring bruker siste oppdatering uansett dato); server.py:527-543 POST /stock/<code>/update
- **Reproduser:** 1) Known-answer: ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_loops.py::test_an_update_written_after_the_horizon_is_not_scored_with_hindsight. 2) Ende til ende på kopi (...\kalibrering\hjem-oppd): /stock/DNB viser «Har sannsynligheten din endret seg?» for vurdering #4 av 1. aug. 2025 (horisont ute 2026-08-01, scoret som bull til 305,00). POST /stock/DNB/update p=0.05/0.05/0.9 gir 303 og rad 12. /calibration viser da «DNB #4 1 0.875 0.015 bedre».
- **Forventet:** Oppdateringer etter horisontslutten avvises («vurderingen er avsluttet – skriv en ny vurdering») og telles ikke. Paret for en endelig vurdering bruker bare oppdateringer datert <= horizon_end.
- **Vist:** Oppdateringen skrives (hash-kjedet, kan aldri fjernes). Brier for siste oppdatering blir 0,015 mot 0,875 opprinnelig og står som «bedre», regnet mot et utfall som var kjent da oppdateringen ble skrevet.
- **Årsak:** Verken write() eller scoring() sammenligner oppdateringsdatoen med vurderingens horizon_end (start + horizon_months). pending() ber dessuten om nettopp denne oppdateringen, se neste funn.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #46 Oppdateringsskjemaet (D48) kaster de nye sannsynlighetene stille hvis «endret» ikke er krysset av, og skriver de gamle til den uforanderlige loggen

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/KOG/vurdering («Har sannsynligheten din endret seg?»); src/osloquant/dashboard/updates.py:89-90 (probs = form hvis changed, ellers view) og 62-75 (form_problems)
- **Reproduser:** testhjem-flyt: POST /stock/KOG/update med p_bear=0.10, p_base=0.50, p_bull=0.40, reason=«FIKTIV: bull-sannsynligheten opp etter Q3 (test)», uten changed → 303 /stock/KOG?updated=13. Uten reason → 400 «say in a sentence why the news does not change the probabilities». Kjør tester/t_skjema.py (sjekk 1).
- **Forventet:** Feilmelding «du skrev nye sannsynligheter – kryss av for endret» (eller at de skrevne 0.10/0.50/0.40 lagres)
- **Vist:** Rad #13: changed=false, p_bear/base/bull = 0.25/0.5/0.25 (de gamle); historikken viser «25% / 50% / 25% (uendret – …)». Uten begrunnelse sier feilmeldingen at nyheten ikke endrer noe, selv om tre nye tall er skrevet inn
- **Årsak:** write() ser bare på avkrysningen; utfylte sannsynligheter ignoreres når changed mangler. Loggen er append-only med hash-kjede, så feil rad kan ikke rettes.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #47 Oppdateringsspørsmålet stilles for vurderinger som har passert horisonten, og Brier for en oppdatering skrevet etter horisonten settes som «bedre» (etterpåklokskap) – duplikat av #45

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: / (punkt 1 «Gjør først: DNB: har sannsynligheten endret seg etter Quarterly Report - Q3 (21. okt. 2026)?», punkt 7 for KOG), /aksje/DNB/vurdering, /calibration («Oppdateringer etter ny informasjon»); src/osloquant/dashboard/updates.py:41-56 (pending uten horisontsjekk) og 109-118 (scoring tar us[-1] uansett dato)

### #48 «nan», «inf» og «1e999» godtas som tall og skrives permanent i vurderingsloggen

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** POST /stock/<code>/judge og /stock/<code>/forecast ; server.py:30-36 (_num), book.py:187-189 (validate_form), judgements.py:131-133, forecasts.py:71-78 (form_problems)
- **Reproduser:** På en kopi av testhjemmet (krasj/hjem), Flask test_client: POST /stock/KIT/judge rating=HOLD target=nan rationale='En begrunnelse som er lang nok her.' kill='Omsetning faller under 900 EURm' premortem_1..3 fylt -> 303, rad #12 med "target": NaN. Samme med target=1e999 -> rad med "target": Infinity. POST /stock/OUTLT/forecast med low=-1e999 mid=2 high=3 (gyldig report_date) -> 303, rad med low -Infinity. Tester: test_judgement_form_rejects_nan_and_inf_target[nan/inf], test_forecast_rejects_infinite_interval.
- **Forventet:** 400 med «kursmålet må være et positivt tall» / «intervallet må ha endelige tall»; ingenting skrives.
- **Vist:** Radene skrives (hash-kjeden gjør dem permanente). Etterpå: aksjelinjen «Mitt syn HOLD · kursmål NOK inf · +inf%», forsiden og kalibreringen viser «nan» i kursmål-kolonnen, dekningssiden «du HOLD inf».
- **Årsak:** float('nan') og float('inf') passerer «<= 0»-sjekken og «bear <= target <= bull» hoppes over når bear/bull mangler; ingen math.isfinite-sjekk noe sted.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #49 Oppdateringsløkken (D48) gjelder også modne vurderinger – etterpåklok oppdatering scores som bedre Brier – duplikat av #45

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/DNB/vurdering, /aksje/KOG/vurdering, / (punkt 1 og 7), /calibration ; updates.py:41-58 (pending uten horisontsjekk), :74-95 (write uten horisontsjekk), :106-120 (scoring tar siste oppdatering uansett dato)

### #50 Teknisk-fanen merker «(utløst nå)» ut fra tilstand, ikke ut fra det målte signalet (kanalraden ser ikke på MA20, drawdown og MA-kryss gjelder i dager etter selve hendelsen)

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/technicals.py:105-111 (Kanal 120 d: active=bool(signal), altså bare helningen); technicals.py:74-81 (MA 20/60: kryss innen 10 kalenderdager); technicals.py:98-100 (Fall fra 60 dagers høy: tilstanden < −10 %). Det målte signalet: signals.py:109-110, 116, 119-120 (_edge = første dag; kanalen krever også close > MA20 eller < MA20). Visningen: stockpage.py:429-430
- **Reproduser:** Se /aksje/AKRBP/teknisk: «SMA 20 363.76 – kursen -14.0 % fra snittet» står samtidig med «Kanal 120 d +36 %/år … Rising channel entry (utløst nå)». BWE ligger 22.6 % under SMA20 og har likevel «Rising channel entry (utløst nå)». KIT viser «Falling channel entry (utløst nå)», men signalet ble sist utløst 15.10.2026. ELK viser «Drawdown 10% from 60d high (utløst nå)», sist utløst 07.10.2026. Testene: data/test_ekte_avvik.py::test_utlost_naa_matches_the_measured_signal (6 tilfeller feiler) og rene/test_perioder_teknisk_kjent.py::test_channel_row_active_although_signal_needs_close_above_ma20 (helning +73 %/år og sluttkurs under MA20: signal_frames gir False, raden sier active=True).
- **Forventet:** «(utløst nå)» bare når sg.signal_frames(P)[signal] er True på siste økt. Det er den hendelsen oddsene i signal_odds.yaml er målt på. 9.11.2026 i kopien av testhjemmet ble Rising/Falling channel entry utløst for én aksje (AUTO).
- **Vist:** Kanalraden viser «(utløst nå)» for 45 av 65 aksjer samme dag. Over 549 økter er kanalraden «aktiv» 13 214 aksjedager, mot 829 faktiske signaldager. Drawdown-raden sier «(utløst nå)» flere uker etter signaldagen, selv om detaljteksten sier «målt ved første dag under −10 %».
- **Årsak:** technicals.rows bygger signalvilkårene opp på nytt for hånd i stedet for å lese signal_frames. Kanalen sjekker bare helningen, ikke sluttkurs mot MA20 og ikke om det er første dag. Drawdown og MA-kryss bruker tilstand eller et vindu på 10 kalenderdager.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #51 «60 dagers lav» og volumkravet for 60-dagers brudd regnes på en annen måte enn det målte signalet de henter odds fra

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/technicals.py:101-104 (lo60 = minste SLUTTKURS siste 60 økter) mot signals.py:84,117 (lo60 = minste LOW). technicals.rows får ingen low-serie (server.py:142). technicals.py:126-132 (_volume_confirms bruker snittet av de 20 øktene FØR i dag) mot signals.py:85,108 (vol20 = rolling(20) MED dagen i dag)
- **Reproduser:** Se /aksje/AKRBP/teknisk: raden «60 dagers lav 316.80 … Breakdown below 60d low (utløst nå)». Boksen «Signaler siste 10 økter» på samme fane viser at signalet sist ble utløst 5.11.2026, med «the 60-day low 327.70» regnet fra low. BWE er likt (46.80, utløst nå; signalet sist 5.11). Kjente svar: rene/test_perioder_teknisk_kjent.py::test_sixty_day_low_row_uses_closes_but_signal_uses_lows (sluttkurs 100 i 199 økter, low 97, i dag 99: signalet utløses ikke, raden sier utløst) og ::test_breakout_volume_rule_excludes_today_but_signal_includes_it (volum 100 i 20 økter, i dag 152 og kurs over 60-dagers topp: signalet regner 152 > 1,5 × 102,6 = 153,9 og gir nei, raden regner 152 > 150 og gir ja).
- **Forventet:** Raden bør bruke samme definisjon som signalet: low-serien for 60-dagers bunn, og vol20 med dagen i dag. Fanen bør vise ett og samme «60-dagers lav».
- **Vist:** Over 549 økter i kopien var 608 av 1 251 aksjedager med «60 dagers lav (utløst nå)» ikke signaldager. For bruddregelen var det 40 av 563. 9.11.2026 er AKRBP og BWE feilmerket, og samme fane viser to ulike 60-dagers bunner.
- **Årsak:** technicals.py har en egen implementasjon med andre serier og vinduer enn signals.indicators.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #52 5Å er alltid deaktivert med forklaringen «for kort historikk i lageret», og «Maks» dekker bare 548 økter (fra 2.9.2024) – duplikat av #12

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

Hvor: src/osloquant/dashboard/market.py:54 (snapshotet laster now − 800 dager) mot charts.py:81-82 (5Å = 1 250 økter, CHART_SESSIONS = 1 260) og DECISIONS D57 («the overview chart holds five years of closes»); charts.py:97-107; stockpage.py:105-117

### #53 Kalibreringen regner dagens kurs for høyt når et utbytte er gått ex etter synet og rå-tabellen ligger etter – duplikat av #6

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

Hvor: src/osloquant/judgements.py:259-260 (factor = raw_s/adj_s ved start; price_now = adj_e * factor); brukes i vs_target, target_reached, in_band, scenario_hit og brier (/calibration, /review)

### #54 Avsluttede vurderinger (horisont passert) telles som åpne: «Gjør først»-oppdatering på forsiden, «Ikke oppdatert» på kalibreringen, R05 = 50 %, malspor «4 av 4»

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/updates.py:47 (pending: alle latest_by_code); today.py:230 (habit_items); chief.py:108-113 (R05); server.py:666 + judgements.py:407-412 (fingerprint over bk.cases() views)
- **Reproduser:** 1) / (crawl1\page_.html): punkt 1 «Gjør først update · DNB: har sannsynligheten endret seg etter Quarterly Report - Q3 (21. okt. 2026)?». Punkt 14 på samme side: «DNB: the view is 465 days old past its horizon – renew or retire it». 2) /calibration på kopien ...\kalibrering\hjem (render_calib.py hjem /calibration): «Ikke oppdatert ...: DNB (Quarterly Report - Q3, 19 d)» og «probabilities 25%/50%/25% in 4 of 4 views: DNB, KOG, OUTLT, SATS». 3) ...\kalibrering\chief_metrics.py: R05 = (0.5, 2). 4) test_kal_loops.py::test_an_expired_view_is_not_pending_an_update.
- **Forventet:** DNB #4 (2025-08-01) og KOG #2 (2025-06-02) er utløpt. Riktig er «Ikke oppdatert: ingen», ingen D48-oppgave for DNB på forsiden, R05 = 1 av 1 = 100 %, og malspor «2 av 2 views: OUTLT, SATS». Syntetisk test: pending() = [].
- **Vist:** DNB er første «Gjør først» med urgency 0 og står 4 ganger i planen. Kalibreringen sier «Ikke oppdatert: DNB». R05 er 50 % (1 besvart + 1 «forfalt») og står som brudd mot målet 90 %. Malspor teller 4 av 4 views. Syntetisk: [('AAA', 1, 42, True)].
- **Årsak:** Ingen av løkkene bruker vurderingens horisont. Bare today.decisions (stale-view) og judgements.score kjenner den. Denne løkka fører rett inn i etterpåklokskapsfunnet over.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #55 Feilmønstrene «for tidlig inn» og «for sent ut» måler justert kursbane mot notert kurs og kill-nivå

*Alvor middels, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/learn.py:70-87 (path = prices.adjusted; rel = path / j['price'] - 1; _crossed(path * raw_factor=1.0, kill)); vises i /calibration «Feilmønster» og brukes av deskens Bear («Mitt feilmønster fra kalibreringen», desk.py:740-746)
- **Reproduser:** ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_learn.py: BUY @100 notert 2025-01-02, kill-nivå 86. Notert kurs faller til 89,5 (-10,5 %), utbytte 5 ex 2025-09-01 (faktor 0,947). Notert kurs når aldri 86, og total-avkastnings-drawdown er -10,5 %.
- **Forventet:** Ingen «early» (drawdown < 15 %) og ingen «late_out» (kill-nivået aldri krysset)
- **Vist:** ['early', 'late_out', 'no_kill_check']: 89,5 x 0,947 = 84,79 leses som -15,2 % og som en sluttkurs under 86. På ekte lagerdata starter en notert BUY i DNB 2025-08-01 til 257,70 på justert 242,65, altså -5,8 % allerede første dag.
- **Årsak:** Kursbanen er den tilbakejusterte serien (senket med alt utbytte frem til i dag). Vurderingskursen, kill_level og bear er noterte tall. raw_factor = 1.0 er en rest som aldri ble regnet ut.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #56 En halvferdig dagsbar fra en kjøring i åpningstiden vises som «siste sluttkurs», mens oddsene på samme side dropper den

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/market.py:52-65 (ingen regel for uferdig økt); odds.py:133-139 (complete_sessions, brukt bare i _long_closes); live/engine.py:169-183 (record_market_data skriver dagens bar også før stengetid); scripts/schedule_live.ps1:9-11, 35 (07:30-kjøringen starter når maskinen våkner, -StartWhenAvailable); server.py:70-72 (forsiden setter last_seen_session = asof)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_d3_unfinished_session.py"
- **Forventet:** Kl. 12:00 9. nov. 2026 bruker hele siden samme regel: enten leser alt 6. nov. som siste sluttkurs, eller baren merkes «ikke endelig» (Oslo stenger 16:20, odds.py regner baren som endelig fra 16:40)
- **Vist:** Oddsblokken leser 6. nov. Kursbaren, periodeknappene, /sectors og signalskannet leser 9. nov. og kaller den «Yahoo Finance via oslo-quant-lageret (daglig sluttkurs, forsinket), 9. nov. 2026». Forsiden setter last_seen_session = 9. nov., så signaler på den endelige baren for 9. nov. vises aldri som nye. Sammen med cachefeilen blir formiddagskursen stående
- **Årsak:** complete_sessions finnes, men brukes ikke av market.snapshot() eller today.signals_since. Live-motoren selv bruker bare «last completed session», men lagrer den uferdige baren
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #57 Teknisk-raden «60 dagers lav» bruker sluttkurser, mens oddsene den viser er målt på intradag-low

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/TGS/teknisk (og alle aksjer); src/osloquant/dashboard/technicals.py:101-104 (lo60 = c.iloc[-61:-1].min()) mot src/osloquant/signals.py indicators: lo60 = L.rolling(60).min().shift(1)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_a3_60d_low.py"
- **Forventet:** Nivået for «Breakdown below 60d low» 9. nov. 2026 (laveste low de 60 foregående øktene, egen pandas i avkastning\tech.py): TGS 122.00, SATS 39.20, KIT 82.00, ELK 29.22, PROT 393.75, BAKKA 418.80
- **Vist:** TGS 127.41 («kursen +4.1 % fra bunnen»), SATS 39.50, KIT 83.20, ELK 29.50, PROT 395.53, BAKKA 421.60. Ved en sluttkurs på 125.00 ville TGS-raden stått som utløst med signalets odds, mens signalet ikke fyrer
- **Årsak:** Raden over («60 dagers høy») bruker high slik signalet gjør, men «60 dagers lav» bruker closes, fordi tc.rows ikke får low-serien

### #58 Varselet om gamle kurser på «I dag» slår ut dagen etter hver børsfridag, men ikke en ukedagskveld da dagens sluttkurs mangler

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / ; src/osloquant/dashboard/render.py:236-243
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_d2_stale_banner.py"
- **Forventet:** Ingen varsel tirsdag 7. apr. 2026 (siste økt 1. apr.; 2., 3. og 6. apr. stengt), 2. jan. 2026 (siste 30. des. 2025), 29. des. 2025 (siste 23. des.) og 15. mai 2026 (siste 13. mai). Lageret har ingen barer på disse fridagene (avkastning\dates_check.py). Varsel tirsdag 10. nov. hvis mandagens kurs mangler
- **Vist:** «Siste sluttkurs i lageret er fra … – eldre enn siste virkedag» alle fire fridagsmorgenene (4 feil av 6 tilfeller). Mandag 9. nov. kl. 19 med fredagens kurs gir ikke varsel, selv om mandagens sluttkurs skal være der fra ca. 17:30
- **Årsak:** «expected» er forrige ukedag uten børskalender, og bare datoen sammenlignes, ikke klokkeslettet
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #59 6M og 5Å teller økter i stedet for kalendermåneder: 6M for SATS viser +6.0 %, der seks måneder gir +10.3 %

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/<kode>, periodeknappene; src/osloquant/dashboard/charts.py:81 (PERIODS 21/126/250/1250), 85-108; /sectors og /watchlist «Uke»/«Måned» (market.py:81-82, 5 og 21 økter)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_a5_period_bases.py" ; avkastning\periods.py for alle sju aksjer
- **Forventet:** Én regel for alle knapper. Med kalenderregelen (siste sluttkurs på eller før samme dato N måneder tilbake): SATS 6M fra 8. mai 2026 +10.28 %, KIT −15.3 %, TGS −7.4 %, PROT +4.2 %, ELK +5.0 %, BAKKA +5.1 %; SATS 5Å fra 9. nov. 2021 +120.04 %
- **Vist:** 6M = 126 økter fra 13. mai 2026: SATS +5.98 %, KIT −14.7 %, TGS −9.0 %, PROT +7.6 %, ELK +6.4 %, BAKKA +3.5 %. 5Å = 1250 økter fra 17. nov. 2021 (SATS +94.49 %). 1M (21) og 1Å (250) treffer kalenderdatoen i dag, så knappene følger i praksis to regler, mens YTD følger kalenderen
- **Årsak:** Faste øktantall forutsetter 21 økter i måneden og 252 i året. Mai 2026 har tre børsfridager (1., 14. og 25. mai), og Oslo har rundt 250 økter i året, så 126 ≠ et halvt år

### #60 «other» (ingen driver gjenkjent) telles som delt kill-driver: forsiden og analysesjefen varsler at urelaterte syn «dør av samme driver»

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / («Boken samlet»: «3 views can die from the same driver – other: DNB, OUTLT, SATS»; punkt 13 «Analysesjefen … Øverst: Flere caser deler kill-driver»), /stock/SATS/pretrade punkt 5; src/osloquant/dashboard/portfolio.py:70 (shared), chief.py:228-233 (R25)
- **Reproduser:** Åpne forsiden på testhjem. Kjør tester/t_forside.py (sjekk 3): exposure() med to BUY-syn med kriteriene «Kontrakten med hovedkunden fornyes ikke» og «Fabrikken i Kina stenger».
- **Forventet:** Ingen delt driver (begge er «other» = ikke gjenkjent); ingen R25-forslag
- **Vist:** shared_drivers = {'other': ['AAA', 'BBB']}; forsiden: «3 views can die from the same driver – other»; R25 blir analysesjefens øverste forslag
- **Årsak:** shared tar alle drivere med ≥ 2 caser, inkludert sekkeposten «other».
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #61 Etter en oppdatering viser syn-boksen, oddsene og Før du kjøper fortsatt de gamle sannsynlighetene

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/DNB/vurdering (etter rad #14) og /aksje/SATS/vurdering (rad #8: 20/50/30); src/osloquant/dashboard/render.py:378 (view_box leser c.view), odds-blokken «Ditt syn: bear 25 % …», pretrade «Scenarioene i vurderingen»
- **Reproduser:** testhjem-flyt: POST /stock/DNB/update med changed=1, 0.20/0.50/0.30 → /stock/DNB?updated=14. Les boksen øverst på Min vurdering. Kjør tester/t_oppdatering.py (sjekk view box).
- **Forventet:** «Sannsynlighet bear / base / bull 20% / 50% / 30%» (siste oppdatering) – eller begge med dato
- **Vist:** «25% / 50% / 25%»; de nye tallene finnes bare som en rad i historikktabellen. Brukeren kan tro oppdateringen ikke ble lagret
- **Årsak:** view_box og odds bruker vurderingsraden; updates.block_html bruker siste oppdatering – to sannheter på samme side.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #62 Ugyldig desk-POST (ukjent kode) lagrer en tom kjøring som blir «Dagens kjøring» på /desk og forsiden

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** POST /desk/run ; server.py:609-621, desk.py:1031-1066 (run skriver før serveren sjekker), desk.py:284-287 (latest) og :1138-1146 (front_summary)
- **Reproduser:** På kopien: POST /desk/run code=ZZ9 -> 400 «no close for ZZ9 on the newest session …», men desk/index.jsonl får en ny linje (scanned 1, stocks {}) og runs/20261109T194538-manual.json skrives. GET /desk: «Dagens kjøring 1 Skannet 0 Flagget … Speideren flagget ingenting i dag». GET /: «Desk i dag: Skannet 1, flagget 0, drept 0 … kl. 20:45 (manual)». Test: test_invalid_desk_post_writes_no_run.
- **Forventet:** 400 og ingen fil skrevet; forsiden og /desk viser fortsatt kveldskjøringen 20261109T174805-daily (Skannet 65, flagget 43, drept 1, parkert 42).
- **Vist:** Den tomme kjøringen erstatter dagens kjøring i morgensjekken. (Også en gyldig manuell kjøring på én aksje fra aksjesiden gjør det samme, siden latest(session) tar siste rad uansett trigger.)
- **Årsak:** desk.run(write=True) lagrer før serveren vet om aksjen fantes; front_summary/latest foretrekker ikke daily-kjøringen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #63 Utfallsodds gir dommen «klart mot kill-nivået» uten data (OUTLT, 33 økter) – duplikat av #44

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /aksje/OUTLT/vurdering og /stock/OUTLT/pretrade ; render.py:670-683 (odds_block: decided = NaN er truthy, gap = NaN faller til siste gren), render.py:684-689 («siden ?»)

### #64 «Uendret»-oppdatering kan ikke logges for en vurdering uten sannsynligheter – duplikat av #46

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: POST /stock/<code>/update ; updates.py:87-94 (probs fra synet, None filtreres bort), judgements.py:115-117 (REQUIRED update krever p_*)

### #65 Uklassifiserte kill-kriterier («other») regnes som felles kill-driver – duplikat av #60

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: / (Boken samlet), /stock/<code>/pretrade (Delt driver), /chief (R25 øverst) ; portfolio.py:29-38 (driver_of → ('other','none')), :71 (shared tar med 'other')

### #66 Et SELL-syn uten kill-nivå får bear-verdien som kill-nivå (på samme side av kursen som kursmålet), og dermed aldri utfallsodds

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/odds.py:206-213 (kill_level ser ikke på rating). learn.py:79 bruker motsatt regel (SELL gir bull). Funksjonen brukes av server.py:91, desk.py:586 og pretrade.py:109/152
- **Reproduser:** Kjør rene/test_odds_kjent.py::test_kill_level_for_a_sell_view_without_kill_level_is_on_the_wrong_side og ::test_sell_view_without_kill_level_gets_no_odds med synet {rating SELL, target 80, bear 70, bull 130}, uten kill_level, på en kjent kursserie.
- **Forventet:** D15 sier at kill-nivået for en SELL ligger over kursen, og learn.py:79 bruker bull. Forventet kill = 130 (bull), og oddsene regnes ut.
- **Vist:** kill_level gir 70 («bear value (no kill level set)»). case_odds svarer med «the price … is not between the target … and the kill level …» og ingen odds, og overskriften sier at bear-verdien er stedfortreder.
- **Årsak:** Stedfortrederen er alltid bear, uansett rating.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #67 Lett case sier «the price needs growth at or above the cost of capital» når den løste veksten ligger under (SALM: 8,33 % mot 8,5 %)

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/lightcase.py:61 (g < wacc − 0.005, ellers None) og lightcase.py:92-93 (teksten for above_wacc). Vises på /aksje/SALM/verdsettelse og i «Hva prisen krever» under Min vurdering
- **Reproduser:** Åpne /aksje/SALM/verdsettelse. Den lette casen sier «the price needs growth at or above the 8.5% cost of capital (EST)». Testen data/test_ekte_avvik.py::test_salm_reading_says_at_or_above_wacc_although_g_is_below feiler. Syntetisk: rene/test_lettcase_kjent.py::test_implied_growth_just_under_wacc_is_called_at_or_above (EV 10 000, NOPAT 60, ROIC 12 %, WACC 9 % gir g = 8,84 %).
- **Forventet:** Fra SALM-casefilen: EV 102,3 mrd, NOPAT 3,226 mrd, ROIC 8,80 % og WACC 8,5 % EST gir g = (N − EV·W)/(N/R − EV) = 8,33 % i året. Setter man den inn igjen, gir formelen nøyaktig EV. Teksten bør si at prisen krever 8,3 % vekst, 0,2 pp under kapitalkostnaden.
- **Vist:** «at or above the 8.5% cost of capital» – påstanden peker feil vei.
- **Årsak:** Grensen på 0,5 pp skal hindre at formelen eksploderer nær WACC, men teksten for None sier «at or above».
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #68 value_reading gir meningsløse lesninger på kantinput: ROIC None gir «at or above WACC», og EV ≤ 0 gir et negativt avkastningskrav

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/lightcase.py:85-93. compute setter roic None når egenkapital pluss netto gjeld er ≤ 0 eller egenkapitalen mangler (lightcase.py:350-352)
- **Reproduser:** rene/test_lettcase_kjent.py::test_value_reading_without_roic_says_growth_at_or_above_wacc (EV 1000, NOPAT 60, ROIC None, WACC 9 %) og ::test_value_reading_negative_ev (EV −100, NOPAT 60, ROIC 12 %).
- **Forventet:** ROIC None: ingen påstand om vekst over WACC. Med ROIC → ∞ gir formelen g = W − N/EV = 3,0 %, eller lesningen kan bli no_answer («ingen ROIC»). EV ≤ 0: no_answer (netto kontanter over børsverdien).
- **Vist:** ROIC None gir kind above_wacc: «the price needs growth at or above the 9.0% cost of capital». EV −100 gir below_capital: «the price pays for a -1.8 % return».
- **Årsak:** NaN-ROIC sendes videre til implied_growth, og None tolkes som «over WACC». EV ≤ 0 stoppes ikke før below_capital.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #69 «Før du kjøper» beskriver odds-metoden feil: universet bruker volatilitetsskalerte avstander, ikke «like nivåer» eller «samme prosentavstander»

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/pretrade.py:193 (kolonnetittelen «Alle aksjer i lageret, like nivåer») og pretrade.py:195 («analogiene bruker samme prosentavstander»), mot odds.py:105,119. render.py:690 beskriver det riktig
- **Reproduser:** Åpne /stock/SATS/pretrade, seksjon 2: kolonnen heter «Alle aksjer i lageret, like nivåer», og kildelinjen sier «analogiene bruker samme prosentavstander».
- **Forventet:** «Alle aksjer: nivåene like langt unna, målt i hver aksjes volatilitet den gang». Bare «Egen historikk» bruker samme prosentavstander.
- **Vist:** «analogiene bruker samme prosentavstander»
- **Årsak:** Teksten er skrevet uavhengig av odds.analogues.

### #70 Periodeknappene er én økt for strenge: med n+1 sluttkurser deaktiveres perioden n

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/charts.py:100,107 (enough = base_i > 0)
- **Reproduser:** rene/test_perioder_teknisk_kjent.py::test_period_enough_off_by_one: med 6 sluttkurser har 5D 5 økter og avkastning +5.0 %, men enough=False.
- **Forventet:** enough når len(c) − 1 ≥ n.
- **Vist:** Knappen er deaktivert med «for kort historikk».
- **Årsak:** Feil med én i grensesjekken.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #71 Størrelseskalkulatoren i skjemaet (JS) ignorerer max_loss_per_group og tilbyr en størrelse serveren avviser

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/render.py:986-988 (lim har maks tap / maks andel / fri papirsum / samlet tap, ingen gruppe); sizing.py:81-83 og :107-110 (serveren har gruppegrensen)
- **Reproduser:** ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_sizing.py::test_js_applies_the_group_loss_limit_like_the_server (kjører det ekte <script> fra sizing_box i node v24 med en DOM-stub): kurs 100, kill 90, max_loss_per_group 3000, åpen BUY i samme gruppe med loss_at_kill 2900.
- **Forventet:** Største tillatte 9 aksjer, bindende «loss in the Seafood group»: (3000-2900)/10,5 = 9,5, som sizing.size
- **Vist:** «Største tillatte: 190 aksjer (bindende: maks tap) ... tap hvis kill-nivået nås: NOK 1 995». Ved innsending avviser serveren 190 med «the open views in the Seafood group would together lose more than NOK 3 000».
- **Årsak:** D27 la gruppegrensen til sizing.py og desken, men ikke i JS-formelen eller data-attributtene (ingen gruppe eller gruppetap i sz). Uten gruppegrense gir JS og sizing.py samme svar (190 aksjer, NOK 1 995 ved 100/90).

### #72 «bedre/ikke bedre» i oppdateringstabellen gjør Brier 0,0 om til 9

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/updates.py:153 ((p['brier_updated'] or 9) < (p['brier_view'] or 9))
- **Reproduser:** ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_loops.py::test_a_perfect_update_is_shown_as_better (brier_view 0,875, brier_updated 0,0)
- **Forventet:** «bedre» (0,000 < 0,875)
- **Vist:** «ikke bedre». Omvendt blir brier_view 0,0 mot en hvilken som helst oppdatering vist som «bedre».
- **Årsak:** `x or 9` er ment for None, men treffer også 0.0

### #73 Kvartalsprognose (D52) kan besvares av feil rapport: answer() ser ikke på prognosens rapportdato

*Alvor lav, sikkerhet middels; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/forecasts.py:111-120 (første lesing innen 120 dager etter prognosedatoen som har tallet)
- **Reproduser:** ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_loops.py::test_forecast_answered_only_by_the_report_it_forecast: prognose 2026-11-01 for rapporten 2026-11-20. Lesingen av den rapporten mangler 'revenue'. Neste kvartals lesing 2027-02-20 (111 dager etter) har revenue 150.
- **Forventet:** Ubesvart («ikke avgjort ennå»): neste kvartals tall er ikke fasiten
- **Vist:** Besvart med 150: utenfor, bom +50 %
- **Årsak:** Vinduet er 120 dager fra prognosedatoen, og f['report']['date'] brukes ikke. En prognose logget mindre enn ca. 30 dager før rapporten kan derfor få neste kvartal som fasit.

### #74 «Kill-kriterium handlet på» teller norske ord som «beholdt» som handling

*Alvor lav, sikkerhet middels; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/judgements.py:297 og :348; render.py:1061; learn.py:90 (kill_ignored); chief.py:161: bare de engelske ordene held/none/nothing/ignored regnes som «ikke handlet»
- **Reproduser:** ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_loops.py::test_a_held_breach_written_in_norwegian_is_not_counted_as_acted_on (kill_check breached=True action='beholdt', som oq book kill --breached --action beholdt skriver)
- **Forventet:** kills_acted 0, og mønsteret «kill-kriterium brutt og ignorert» slår inn
- **Vist:** kills_acted 1. kill_ignored slår ikke inn, og /calibration sier «1 breached, 1 acted on».
- **Årsak:** Fritekstfeltet «action» sammenlignes med en engelsk ordliste. Siden og brukeren er norske (testhjemmet skrev selv «beholder»).

### #75 Forsiden kaller en vurdering «past its horizon» 4–6 dager før horisonten (360 dager mot 12 kalendermåneder)

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/today.py:93 (age > 30 * horizon_months)
- **Reproduser:** ...\kalibrering\tests> <venv python> -m pytest -q -p no:cacheprovider --rootdir . test_kal_today.py: vurdering 2025-11-13, i dag 2026-11-09 (361 dager)
- **Forventet:** Ingen stale-view: horisonten er 2026-11-13 (start + DateOffset(months=12), som judgements.score), og kalibreringen sier provisional
- **Vist:** «Alpha: the view is 361 days old – past its horizon – renew or retire it.»
- **Årsak:** 30 x 12 = 360 dager i today.py, mens kalibreringen bruker kalendermåneder (365/366 dager)

### #76 «Utbytte siste 12 m» og direkteavkastningen dobles i dagene etter et årlig utbytte som kom tidligere enn året før

*Alvor lav, sikkerhet middels; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/<kode>/oversikt → Nøkkeltall; src/osloquant/dashboard/stockpage.py:96-101 (vindu asof − 365 dager), 247-248
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_a9_dividend_window.py" ; omfang: avkastning\divscan.py
- **Forventet:** DNB 24. apr. 2026 (sluttkurs 277.20): ett årlig utbytte, NOK 18.00 og 6.5 %
- **Vist:** NOK 34.75 og 12.5 % i 8 dager (22.–29. apr. 2026), fordi utbyttet fra 30. apr. 2025 (16.75) også er med. Dette skjer 30 ganger for 20 aksjer med årlig utbytte i 2023–2026, for YAR i 17 dager i 2026
- **Årsak:** Vinduet er 365 kalenderdager. Når eks-datoen flytter seg noen dager tidligere, ligger begge de årlige utbyttene i vinduet. Tallet stemmer med etiketten, men som direkteavkastning er det misvisende
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #77 /sectors: gruppens «snitt … i år» tar med avkastning fra notering uten å merke det

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /sectors (Consumer, telecom & real estate); src/osloquant/dashboard/render.py:337, 344; aksjesidens YTD-knapp for OUTLT har ingen * (stockpage.py:110, bare i hover)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_b2_ytd_avg_listing.py"
- **Forventet:** −2.4 % i år (snittet av de sju med ekte YTD: ENTRA −12.07, EPR −10.02, KID +12.80, NAS −19.61, ORK −2.20, SATS +15.63, TEL −1.53 %; egen pandas), eller et merke på snittet
- **Vist:** «8 aksjer · snitt … / −1.0 % i år». OUTLTs +9.2 % fra første kurs 24. sep. 2026 er med i snittet. På aksjesiden står YTD +9.2 % uten *
- **Årsak:** avg = sub[k].mean() over alle radene; ytd_from_listing brukes bare til stjernen på raden
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #78 Periodeknappen trenger én sluttkurs mer enn /sectors for samme periode (feil med én for nye aksjer)

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/charts.py:100, 107 («enough»: base_i > 0) mot market.py:80-82 (len(c) > n)
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_a7_first_sessions.py"
- **Forventet:** Med 22 syntetiske sluttkurser 100 → 121 er 1M aktiv med +21.0 %, som på /sectors. Med 6 sluttkurser er 5D aktiv med +5.0 %
- **Vist:** 1M og 5D er deaktivert med «for kort historikk», mens market.returns (/sectors, /watchlist) viser +21.0 % for samme serie
- **Årsak:** base_i = max(len − 1 − n, 0) og enough krever base_i > 0. Når len == n + 1 er base_i = 0 likevel riktig base

### #79 Dekningslinjen på forsiden (universet, full/lett case, under plan) forsvinner helt når Claude ikke har noe syn

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / (under «Research book mot kursmål»); src/osloquant/dashboard/render.py:278-281
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_c1_front_counts.py" (del 2)
- **Forventet:** «Dekning: 6 selskaper …; universet 65 selskaper – 3 full case, 62 lett case, 0 følges» vises også når Claude har 0 syn
- **Vist:** Ingen linje når coverage['claude'] == 0. I testhjemmet vises den bare fordi Claude har syn på EQNR og MOWI
- **Årsak:** Hele uttrykket er betinget av cov.get('claude'), ikke bare Claude-delen

### #80 Kill-driveren gjettes med delstreng-treff: «strategi» → rates, «Sektoren» og «nok» → fx

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/portfolio.py:13-24 (_RULES uten ordgrenser) og 29-38 (driver_of); brukt på forsiden, i Før du kjøper og i desk.py:730/812
- **Reproduser:** Kjør tester/t_forside.py (sjekkene driver_of): driver_of('Ledelsen bytter strategi uten å si hvorfor'), driver_of('Sektoren faller mer enn indeksen'), driver_of('Kursen er nok for høy til å kjøpe').
- **Forventet:** management, other, other
- **Vist:** ('rates', 'inferred'), ('fx', 'inferred'), ('fx', 'inferred')
- **Årsak:** Mønstrene «rate», «sek», «nok» matcher inne i ord (st-rate-gi, sek-toren, «nok» = adverb); rekkefølgen gjør at rates slår ledelse.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #81 Overvåkningslisten godtar koder som ikke finnes i lageret – duplikat av #106

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: POST /watchlist ; book.py:128-139 (add_watch)

### #82 En perfekt oppdatering (Brier 0) merkes «ikke bedre» – duplikat av #72

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: /calibration (Oppdateringer etter ny informasjon) ; updates.py:153 ((p['brier_updated'] or 9) < (p['brier_view'] or 9))

### #83 Prognose-POST stoler på skjulte felter: rapportdato og -navn kan settes fritt – duplikat av #73

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: POST /stock/<code>/forecast ; server.py:517-519, forecasts.py:63-68 og :82-92

## Brukbarhet

### #84 Aksjesiden er over 2 s på serveren og 3–7 s i nettleseren; signals_since for hele universet og Excel-lesing på hver forespørsel dominerer

*Alvor høy, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** Alle /aksje/<code> og /stock/<code>; server.py:76-119 (stock_context), today.py:314-337 (signals_since → signals.indicators/channel_slope signals.py:52-58), casefile.py:11-31 (reverse_dcf: openpyxl.load_workbook hver gang), technicals.py:59, contract/api.py:185 (get_coverage)
- **Reproduser:** crawl1: server 1.0–2.5 s, nettleser 3.2–7.0 s for alle 17 URL-er × 7 aksjer (SATS første 3 104 ms). 8065 over HTTP: /stock/DNB 8 433 ms første, /stock/SATS 6 071 kald / 3 325 varm. In-process varm (prof.py): SATS 3.1–3.4 s, KIT 2.3–2.5, TGS 2.5–2.6. cProfile varm /aksje/SATS 2 882 ms (prof2.py, prof/aksje_SATS.prof). Navigasjonstid (navtid.py): SATS server 1.6–1.9 s + 1.7–1.8 s i nettleseren etter svaret; KIT 1.1 + 0.6 s. tester/t_ytelse.py.
- **Forventet:** Under 2 s for en side (oppdragets grense)
- **Vist:** signals_since 730 ms (25 % av forespørselen; regner alle 65 aksjers indikatorer for å vise én aksjes signaler – channel_slope rolling.apply med 28 052 Python-kall = 342 ms); reverse_dcf 549 ms (19 %, åpner hele Toolkit-arbeidsboken); render 309 ms (11 %); technicals.rows 247 ms (9 %); get_coverage 2× 259 ms (9 %); company_news 176 ms; _insiders 165 ms. I nettleseren tegnes 9 Plotly-grafer ved lasting, 8 av dem i skjulte faner
- **Årsak:** Ingen cache for indikatorer/signaler per siste sluttkurs; arbeidsboken leses på nytt hver gang; alle sju faner rendres på serveren og alle grafer tegnes ved lasting.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #85 Oppdateringsskjemaet (D48) godtar ikke desimalkomma og viser en rå Python-feil – duplikat av #88

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

Hvor: src/osloquant/dashboard/updates.py:67 (float(p)); jf. server.py:30-36 _num som godtar komma i vurderingsskjemaet; forecasts.py:72 samme for prognoser

### #86 Skjema med feil åpner siden på Oversikt: feilmeldingen står øverst, men skjemaet med det du skrev er skjult på en annen fane

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** POST /stock/<code>/judge, /pass, /forecast, /update (svar 400); src/osloquant/dashboard/server.py:485-491, 505-509, 522-526, 542-546 (ctx['tab'] settes ikke), stockpage.py:576 (standard «oversikt»)
- **Reproduser:** testhjem-flyt: send «Ny vurdering» for SATS uten begrunnelse (POST /stock/SATS/judge). Skjermbilde: <feilsok>/brukbarhet/shots/etter_feil_post-1400.png. Kjør tester/t_feilside_fane.py (4 tilfeller).
- **Forventet:** 400 med fanen der skjemaet er åpen: Min vurdering (judge, pass, update), Rapporter (forecast)
- **Vist:** 400 med «Oversikt» åpen i alle fire; brukeren ser feilmeldingen over en tom graf og må selv finne «Min vurdering»
- **Årsak:** Feil-grenene bygger ctx uten ctx['tab']; bare redirect-grenene (?logged= osv.) åpner vurderingsfanen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #87 Oppdaterings-, prognose- og unnlatelsesskjemaet glemmer det du skrev når serveren avviser det

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/<code>/vurdering (D48-oppdatering, Lar du være?), /aksje/<code>/rapporter (Prognose for neste rapport); updates.py:133-139, forecasts.py:147-149, passes.stock_html – ingen form-verdier sendes inn
- **Reproduser:** testhjem-flyt: POST /stock/DNB/update med 0.20/0.50/0.30 uten avkrysning → 400, inputene er tomme; POST /stock/KOG/forecast med low=14 000, mid tom → 400, tomme felt; POST /stock/TGS/pass reason=«for dyr nå» → 400, tomt felt. tester/t_feilside_fane.py sjekker update-verdien.
- **Forventet:** Skjemaet fylles ut igjen med verdiene (som vurderingsskjemaet gjør)
- **Vist:** Tomme felt; oppdateringsfeltene har heller ikke placeholder «0.25» (vurderingsskjemaet har)
- **Årsak:** block_html-funksjonene tar ikke imot form-verdier; bare render.py-vurderingsskjemaet gjør det.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #88 Desimalkomma og mellomrom i tall: vurderingen godtar «0,25» og «13 500», oppdateringen gir en rå Python-feil og prognosen avviser

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** POST /stock/<code>/update og /forecast; updates.py:70 (float(p)), forecasts.py:71 (float(form[k])) mot server.py:30-36 (_num)
- **Reproduser:** Kjør tester/t_skjema.py (sjekk 2 og 3); eller på testhjem-flyt skriv «0,2» i oppdateringsfeltet med «endret» krysset.
- **Forventet:** Samme parsing som vurderingsskjemaet: _num('0,25') = 0.25, _num('13 500') = 13500.0
- **Vist:** Oppdatering: feilmeldingen «could not convert string to float: '0,2'»; prognose «13 000 / 13 500 / 14 000»: «give the low end, the middle and the high end … as numbers» (dashbordet viser selv tall som «1 324»)
- **Årsak:** To skjemaer bruker float() direkte i stedet for server._num.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #89 Forsidens lenker lander på Oversikt; handlingen ligger på Min vurdering eller Rapporter, og etter en prognose sendes du til feil fane

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / (alle beslutningspunkt lenker til /stock/<code>); render.py:239-247 (title_link → link(code)); stockpage.py:579 (merke bare for ventende oppdatering); server.py:430 (forecast-redirect åpner «vurdering»); reportpdf.py:157 («logg en ny vurdering i skjemaet under» – står på Rapporter, skjemaet er på Min vurdering)
- **Reproduser:** Klikk «DNB: har sannsynligheten endret seg…» → /stock/DNB åpner Oversikt (skjemaet er på Min vurdering, merket «1»). Klikk «KOG: logg kvartalsprognosen» → Oversikt, ingen merke; prognoseskjemaet er under Rapporter. Etter POST /stock/KOG/forecast → /stock/KOG?forecast=15 åpner Min vurdering, der prognosen ikke vises (den står under Rapporter). «SATS: … read the analysis on the stock page» → Oversikt, analysen er under Rapporter.
- **Forventet:** Lenken åpner fanen der handlingen gjøres (/aksje/<code>/vurdering#… eller /rapporter), og etter lagring vises raden der den ble skrevet
- **Vist:** Alltid Oversikt; merket på fanen finnes bare for D48-oppdatering; prognose-redirect til Min vurdering; foreldet tekst «skjemaet under» på Rapporter
- **Årsak:** D57 delte siden i faner, men forsiden og redirectene bruker fortsatt den gamle /stock/<code>-adressen og én vurderingsfane.

### #90 Forsiden ber om handlinger dashbordet ikke har: «log a kill check», «close the case», «renew or retire it»

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / (punkt «SATS … read the analysis on the stock page and log a kill check», «DNB reached the target … set a new view or close the case», «the view is 465 days old – past its horizon – renew or retire it»); today.py:78, 94, 124; ingen rute for kill-sjekk/avslutning i server.py
- **Reproduser:** Følg lenkene fra forsiden til /aksje/SATS, /aksje/DNB: det finnes skjema for vurdering, oppdatering, prognose og unnlatelse, ikke for kill-sjekk eller å avslutte et syn. Eneste hint om kill-sjekk står nederst på /calibration: «Log a check with oq book kill …». Ingen CLI-kommando for å avslutte et syn.
- **Forventet:** Teksten sier hva som faktisk løser punktet («logg en ny vurdering» – som fjerner punktet, verifisert: rad #12 fjernet SATS’ tre punkter – eller «kjør oq book kill …»)
- **Vist:** Instruksjoner uten knapp; et utløpt syn blir stående som «Kan vente» hver dag
- **Årsak:** Tekstene i today.py er fra før skjemaene; kill-sjekk finnes bare i CLI (cli.py:1859), avslutning finnes ikke.

### #91 Beslutningslisten teller samme selskap flere ganger: «15 ting, omtrent 180 minutter» er 4 selskaper + analysesjefen

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / («Dette krever en vurdering fra deg (15)»); today.py:266-274 (merge_items fjerner bare re-assess/post-report-par); render.py:244-257 (minutter summeres per punkt)
- **Reproduser:** Åpne forsiden på testhjem: DNB 4 punkt (update 5 + re-rate 15 + re-assess 10 + stale-view 10 min), KOG 4, OUTLT 3, SATS 3. På testhjem-flyt fjernet én vurdering (rad #12) alle tre SATS-punkt. Kjør tester/t_forside.py (sjekk 2).
- **Forventet:** Ett punkt per selskap som én vurdering avgjør (med grunnene listet), og et tidsestimat for det
- **Vist:** 15 punkt / 180 min; oppsummeringen «1) DNB 2) OUTLT 3) SATS 4) DNB 5) DNB 6) KOG 7) KOG 8) KOG …»
- **Årsak:** Hver regel lager sitt eget Item; dedupliseringen dekker bare to par.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #92 Rekkefølgen «i denne rekkefølgen» er alfabetisk innen hastegrad, ikke etter frist

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /; src/osloquant/dashboard/today.py:274 (sorted by (urgency, code))
- **Reproduser:** testhjem-flyt etter flyten: OUTLT-prognosen med rapport om 3 dager er punkt 6, bak DNB re-rate, DNB re-assess og KOG pre-report med 11 dager igjen. Før flyten: punkt 10 av 15. Kjør tester/t_forside.py (sjekk 1).
- **Forventet:** Innen samme hastegrad: nærmeste frist først (OUTLT 12. nov. før KOG 20. nov.)
- **Vist:** OUTLT forecast #6, KOG pre-report #4
- **Årsak:** Sorteringsnøkkelen er (urgency, code); Item har ingen frist.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #93 Desk-blokken på forsiden lister 42 parkerte, men navngir ikke den ene som ble drept – din egen BUY i SATS

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / («Desk i dag: Skannet 65, flagget 43, drept 1 …»); desk.py:1138-1146 (front_summary har ready_codes og parked_codes, ikke killed), deskpage.py:184-195
- **Reproduser:** Åpne forsiden; les «Desk i dag». Kjør tester/t_forside.py (sjekk desk).
- **Forventet:** «Drept: SATS» med lenke (den viktigste linjen for en aksje i research book)
- **Vist:** «drept 1» uten navn; «Parkert: AFG, AKRBP, …» (42 koder)
- **Årsak:** front_summary samler ikke killed-koder.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #94 «Før du kjøper» bruker 1.5–3.7 s: snapshot()/get_coverage kalles 8 ganger fordi _groups() kalles én gang per case

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /stock/<code>/pretrade; src/osloquant/dashboard/pretrade.py:117 (bk._groups() inne i dict-comprehension per case) og 112; book.py:300-307; market.py:59-65 (snapshot kjører get_coverage hver gang); contract/api.py:185-200 (COUNT, COUNT DISTINCT, MIN, MAX over hele tabellen)
- **Reproduser:** crawl1: OUTLT 3 209 ms, PROT/BAKKA 2 616, TGS 2 467; 8065: SATS 3 539 ms. cProfile varm /stock/SATS/pretrade 2 658 ms (prof/prof_ovrige.txt). tester/t_ytelse.py teller get_coverage-kall.
- **Forventet:** ≤ 2 get_coverage-kall og under 2 s
- **Vist:** 8 get_coverage-kall = 1 105 ms (42 %); snapshot 7 kall 962 ms (36 %); position→_groups 6 kall 839 ms (32 %); signals_since 958 ms (36 %); reverse_dcf 487 ms (18 %)
- **Årsak:** N+1: _groups() per case, og hvert snapshot()-kall spør databasen om dekning (full tabellskanning) for å finne cache-nøkkelen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #95 Første side etter oppstart er treg: I dag 4.4–5.1 s, Desk 2.4–4.7 s, Porteføljer 2.3–2.7 s, Datahelse 2.5 s

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / (server.py:39-73), /desk (desk.py:1070 veto_stats → odds.long_closes, odds.py:142-154), /funds (import av osloquant/allocation.py), /health (datahealth.py:272 overview, price_health :28)
- **Reproduser:** crawl1: / 5 140 ms (første forespørsel), /desk 2 351, /funds 1 899, /health 1 519. 8065: / 4 376 ms kald, 1 724–1 971 varm. Ny prosess (prof_kald.py): / 2 377 ms, /desk 2 685, /funds 2 345; in-process kald /desk 4 718, /funds 2 713, /health 2 492.
- **Forventet:** Morgenbesøket (appvinduet starter serveren, D45) under 2 s
- **Vist:** / kald: snapshot 825 ms (35 %), signals_since 707 (30 %), load_odds YAML 427 (18 %); varm: signals_since 791 av 1 332 ms (59 %). /desk kald: long_closes → load_panel fra 2010 2 264 ms (84 %), varm 0.3 s. /funds kald: import allocation.py 1 267 ms (54 %). /health varm 1.2–1.8 s: price_health 529 ms (44 %), get_coverage 4× 386 ms (32 %)
- **Årsak:** Tunge laster og importer skjer i første forespørsel; signals_since og get_coverage gjentas på hver side (se de to funnene over).
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #97 Feilmeldinger er engelske, rå Python-tekster eller mangler – og 404 er Flasks standardside

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** server.py (alle POST), forecasts.py:67 (pd.Timestamp på skjemaverdi), server.py:579 (float(mv)), judgements.py:117, stockpage.py:575 (siden uten kurs dropper ctx['errors']), Flask 404/500
- **Reproduser:** POST på 8064 (ingenting ble skrevet, sjekket med hash): /stock/OUTLT/forecast report_date=abc → «Unknown datetime string format, unable to parse: abc»; /chief/decide metric_at=abc → «could not convert string to float: 'abc'»; /stock/KIT/judge tom → «choose BUY, HOLD or SELL; a target price is required; …»; /stock/ZZ9/judge og /stock/ZZ9/pass → 400 uten melding; /desk/run/<id>/OUTLT, /aksje/SATS/foo, /aksje/SATS.OL → «404 Not Found … check your spelling» uten meny; /aksje/XXXX svarer 200; /go?code=Kitron → «Ingen kurser for KITRON … Legg den til i universe.yaml» (KIT finnes).
- **Forventet:** Norske meldinger som sier hva som var galt og hva man gjør («Datoen «abc» er ikke en dato – bruk ÅÅÅÅ-MM-DD»), 404 med dashbordets meny og lenke tilbake, 404-status for ukjent kode.
- **Vist:** Blanding av engelsk, Python-unntakstekst og ingen melding.
- **Årsak:** str(e) fra ValueError vises direkte; ingen errorhandler for 404/500.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #99 Kurser og avkastning på /sectors og forsiden har ingen hover med kilde og tidspunkt, og hovrene på aksjesiden har ISO-datoer

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** /sectors (0 title-attributter), / (tabellen over syn); aksjesidens fliser, f.eks. Børsverdi «lett case bygget 2026-11-04» og BAKKA P/E «LTM til 2026-06-30 (FY 2025 + YTD − prior YTD)»
- **Reproduser:** grep -c 'title="' crawl1/page_sectors.html (= 0). Hold over Børsverdi på /aksje/SATS.
- **Forventet:** Hver kurs eller avkastning har kilde og tidspunkt i hover, som på aksjesiden, og datoer i formen fra D58 («4. nov. 2026»).
- **Vist:** Bare en bildetekst for hele siden («Avkastning til sluttkursen 9. nov. 2026 (Yahoo Finance, forsinket)»). «Forsinket» står synlig på /, /sectors, /screen, /coverage og /watchlist. Aksjesidens hovrer blander «2026-11-04» med «4. nov. 2026».
- **Årsak:** D57 la hover bare på aksjesidens nye tall. D58 rører ikke attributter, og periode() kjenner ikke formen «(FY … + YTD − prior YTD)».

### #101 /calibration laster hele prisgrunnlaget tre ganger per visning

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/server.py:663 (jg.calibration -> load_prices), :671 (learn: load_prices igjen), passes.py:62 (pss.scoring: load_prices en tredje gang)
- **Reproduser:** ...\kalibrering: Flask-testklient på kopien med jg.load_prices pakket inn: GET /calibration to ganger
- **Forventet:** Én innlasting delt mellom blokkene; siden godt under 2 s
- **Vist:** status 200, totalt 1,94 s og 1,17 s; load_prices kalt 3 ganger [0,57, 0,37, 0,08 s] og [0,41, 0,37, 0,15 s]. Første måling med render_calib.py: 2116 ms.
- **Årsak:** Hver blokk (D36 learn, D54 passes) henter prisene selv i stedet for å få Prices-objektet fra calibration()

### #102 Forsiden: «110 signaler på andre aksjer – vis» åpner bare 60

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** / («Nye signaler siden sist»); src/osloquant/dashboard/render.py:324
- **Reproduser:** PYTHONIOENCODING=utf-8 python "<feilsok>\avkastning\tests\test_c1_front_counts.py" (del 1); crawl1\page_.html
- **Forventet:** Etiketten sier hvor mange som vises («60 av 110»), eller alle vises
- **Vist:** «110 signaler på andre aksjer – vis» med 60 rader inni og ingen tekst om kuttet (syntetisk test: etikett 70, 60 rader)
- **Årsak:** Listen er rest[:60], mens etiketten bruker len(rest)

### #103 Fire sider viser kurser uten dato: /coverage, /watchlist, /screen og papirfondenes NAV på /funds

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/render.py:1364 (/coverage «Kurs: Yahoo via lageret (forsinket)»), 1175 (/watchlist «Kurser: Yahoo Finance via lageret, forsinket»), 1300 (/screen), 1553-1559 (/funds «Papirfondene siden de ble skrevet», NAV uten «til»-dato)
- **Reproduser:** Åpne /coverage, /watchlist, /screen og /funds (lagret i crawl1\page_coverage.html, page_watchlist.html, page_screen.html og page_funds.html), og let etter datoen for kursene
- **Forventet:** «… forsinket, 9. nov. 2026» som på / og /sectors (mk.price_label(asof)); NAV-tabellen «til 9. nov. 2026»
- **Vist:** Ingen dato for kursene på de fire sidene. /funds har bare byggedatoen (2. nov., kurser til 30. okt.), ikke datoen for siste NAV
- **Årsak:** Kildetekstene er skrevet fast uten mk.price_label

### #105 Blandet språk og en feilmelding som peker på en avkrysning som ikke finnes («tick «I know»»)

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** book.py:162-197 og 211-212, updates.py:62-75, forecasts.py:63-79, server.py:433-439 (OK-meldinger), today.py:71-191, render.py:880, render.py:1162, pretrade punkt 5, /calibration «Kill-kriterier» og «Malspor», status final/provisional/no prices yet
- **Reproduser:** testhjem-flyt: POST /stock/SATS/judge med BUY uten ack_triggered → «already over the line … – tick «I know» to log the view anyway»; avkrysningen heter «Jeg vet det – logg et BUY-syn likevel». Etter lagring: «Logged as row #12 in the judgement log.» Før du kjøper: «Grenser i aksjer: max loss: 157 max position: 549 free paper sum: 2197».
- **Forventet:** Norske meldinger som bruker samme ord som skjemaet (D56: norske etiketter)
- **Vist:** Engelske feil- og OK-meldinger, forsidepunkter («log your view before the report…», «reached the target…»), «not in the store», «no new signals on research-book stocks»; /review lagrer derimot med norsk melding
- **Årsak:** D56 oversatte overskrifter og tabeller, ikke meldingene fra validering og forsidereglene.

### #106 Overvåkning godtar en ticker som ikke finnes («ZZZZ added.»), og den kan ikke fjernes; søkefeltet sender ugyldig kode stille til forsiden

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** POST /watchlist (book.py:128-139), /watchlist-tabellen (render.py:1162 «not in the store»); GET /go (server.py:407)
- **Reproduser:** testhjem-flyt: POST /watchlist code=zzzz → 200 «ZZZZ added.», raden viser «not in the store»; ingen fjern-knapp eller rute. Kjør tester/t_skjema.py (sjekk 4, med QQQQ9 – skriver ingenting). GET /go?code=xx-1 → 302 til / uten melding.
- **Forventet:** Avvis eller advar når koden ikke har kurser i lageret; ugyldig søk gir en melding
- **Vist:** Lagres stille i watchlist.yaml; søket går til forsiden uten forklaring
- **Årsak:** add_watch sjekker bare isalnum; /go redirecter til / ved ugyldig kode.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #107 Tekst kuttes midt i ord uten «…», også i det som lagres på vurderingsraden

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** today.py:153 (ev['what'][:70] → «Kids st»), afterreport.py:299 ([:60] → «(base case 36.9% i», «(13 clubs thr»), book.py:324 (rapporttittel [:40] → «Profit up on higher va», lagres i triggered_at_entry), desk-tabellen «SATS ASA Q3 2026: Prof»
- **Reproduser:** Forsiden testhjem punkt 2; /aksje/SATS/rapporter «Etter rapporten»; /aksje/SATS/vurdering (boksen «Et kill-kriterium er allerede over streken»); rad #12 i testhjem-flyt/judgements.jsonl
- **Forventet:** Hele ord med «…», og full tekst på raden i loggen
- **Vist:** Ordkutt uten markering; den kuttede tittelen er skrevet permanent i loggen
- **Årsak:** Faste skivekutt [:N].
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #108 Tallformat sprikker: prognoser «13000 – 13500», historikk «45.5» mot «45.50», og :g gir 1.23457e+06 over seks sifre

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** forecasts.py:143 og 158 (f'{x:g}'), vurderingshistorikken (render, «Kurs 45.5»)
- **Reproduser:** /aksje/KOG/rapporter etter rad #15: «omsetning: 13000 – 13500 – 14000»; /calibration «13000 – 13500 – 14000»; /aksje/SATS/vurdering historikk «#12 … 45.5»; tester/t_skjema.py (sjekk 5).
- **Forventet:** «13 000 – 13 500 – 14 000» og «45.50» som ellers på sidene
- **Vist:** Uten tusenskille; f'{1234567.0:g}' = «1.23457e+06»
- **Årsak:** :g-format i stedet for sidens tallformat.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #109 Kalibreringssiden viser Brier på tre skalaer med ulike referansepunkter; vanskelig å vite om et tall er godt

*Alvor lav, sikkerhet middels; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /calibration (toppen «0.71 (0 = perfekt, 0,67 = uniform)», «Oppgitt sannsynlighet» «0.236 … 0.25 er å si 50 %», «Per case» «0.67 er å si en tredjedel», «Oppdateringer» «2 er verst»)
- **Reproduser:** Åpne /calibration (på testhjemmene må byggerens prognoserad filtreres, se kalib_inproc.py). Regnet: snitt (0.375+0.875+0.875)/3 = 0.708; binær 0.708/3 = 0.236; uniform 2·(1/3)²+(2/3)² = 0.667 – tallene stemmer.
- **Forventet:** Én skala, eller samme referanse («uniform = 0.67») skrevet likt overalt; desimalpunkt overalt
- **Vist:** Tre forklaringer, «0,67» med komma ved siden av «0.71» med punkt
- **Årsak:** Blokkene er skrevet i ulike faser (D21, D36, D48).

### #110 Oppsett: vurderingshistorikken klemmes i et halvbredt kort (datoer over tre linjer) og «Jeg vet det»-avkrysningen står løsrevet midt på egen linje

*Alvor lav, sikkerhet middels; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/SATS/vurdering; skjermbilder <feilsok>/brukbarhet/shots/crop_historikk.png og crop_triggered.png
- **Reproduser:** Headless Edge 1400 px: shots.ps1 -pages "SATS_vurdering\|/aksje/SATS/vurdering\|5200"
- **Forventet:** Datoer på én linje, avkrysningen ved sin etikett
- **Vist:** «9. / nov. / 2026» over tre linjer, begrunnelsen høyrejustert i smal kolonne; avkrysningsboksen sentrert over etiketten
- **Årsak:** Tabellen ligger i en grid2-kolonne; label-CSS for checkbox i den gule boksen.

### #111 plotly.min.js (4.8 MB) lastes synkront i <head> på alle sider, også sider uten grafer

*Alvor lav, sikkerhet middels; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** render.py:211 (page() legger inn /static/plotly.min.js uansett side)
- **Reproduser:** curl /static/plotly.min.js → 4 815 814 byte. navtid.py: forsiden bruker 192–196 ms etter svaret før lasting; /chief og /calendar har ingen grafer men laster skriptet.
- **Forventet:** Skriptet bare på sider med grafer (eller defer)
- **Vist:** Lastes og parses på hver navigasjon (cachet 1 døgn, men parse/kompilering hver gang)
- **Årsak:** page() har ingen flagg for grafer.

### #113 Datopasset gjør om datoer inne i Windows-stier

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /health (Frosne testdata) ; dates.py:109 (_ISO lookbehind utelater «\»)
- **Reproduser:** GET /health: «…\testdata\22. okt. 2026, prices to 22. okt. 2026». dates.norske_datoer(r'<p>C:\x\testdata\2026-10-22</p>') -> «testdata\22. okt. 2026». Test: test_date_pass_leaves_windows_paths_alone.
- **Forventet:** Stien uendret (D58: filnavn røres ikke).
- **Vist:** Stien endret til en sti som ikke finnes.
- **Årsak:** Lookbehind (?<![\w/.\-]) mangler bakstrek.

### #114 Bekreftelsen «Logged as row #…» vises fra URL-en uten å sjekke loggen

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /stock/<code>?logged=… / passed / forecast / updated ; server.py:430-437
- **Reproduser:** GET /aksje/SATS?logged=abc → «Logged as row #abc in the judgement log.» (engelsk, og ingen rad #abc finnes).
- **Forventet:** Bekreftelse bare når raden finnes, på norsk, med rad og tidspunkt.
- **Vist:** Falsk bekreftelse ved oppfrisking/bokmerke.
- **Årsak:** Meldingen bygges fra query-parameteren.

### #115 «Siste rapport» og «Neste rapport» er tomme for ikke-fulgte aksjer uten at siden sier hvorfor eller hva man gjør

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/KIT, /aksje/TGS, /aksje/PROT, /aksje/BAKKA (Oversikt og Rapporter) ; afterreport.py:85-107 (newest_report), feeds.py:135-140 (followed_codes)
- **Reproduser:** GET /aksje/PROT: «Siste rapport –», «Neste rapport –», Rapporter: «Siste rapport \| ingen funnet», mens nyhetslisten på samme side har «21. okt. 18:50 Q3 2026: CR 82.7% …». TGS: «22. okt. TGS Announces Q3 2026 Results»; BAKKA: «2. nov. Strong Faroese performance…».
- **Forventet:** Tom tilstand med neste steg: «Finanskalenderen hentes bare for research book og overvåkning – legg PROT på Overvåkning».
- **Vist:** «–» / «ingen funnet» / «ikke i kalenderen».
- **Årsak:** Kalenderfeeden hentes bare for followed_codes, og newest_report leser ikke meldingsbufferen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #116 «Før du kjøper»: kommaer fjernes fra gruppenavn og lister, og «fra før» teller aksjen selv

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /stock/<code>/pretrade seksjon 5 ; pretrade.py:235-242 (.replace(',', ' ') på hele HTML-biten), pretrade.py:119-122 (exposure inkluderer koden)
- **Reproduser:** GET /stock/SATS/pretrade: «Sektorgruppe Consumer telecom & real estate : 2 åpne BUY-syn fra før (OUTLT SATS)».
- **Forventet:** «Consumer, telecom & real estate: 1 åpent BUY-syn fra før (OUTLT)» (eller «2 inkludert dette»).
- **Vist:** Gruppenavnet og kodelista uten komma; SATS telles som «fra før» på SATS-siden. Kill-status står som «nå 0.3726 mot 0.37» der aksjesiden skriver «37.3 % vs > 37.0 %».
- **Årsak:** Tusenskille-erstatning brukt på hele teksten; same_group ekskluderer ikke code.

### #117 Negativ null i tallformat («-0.00 R», «-0», «-0%», «-0.0%»)

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/SATS/teknisk, /aksje/TGS/regnskap/kontantstrom, /screen ; render.py bracket_line ({mean_R:+.2f}), stockpage._m, screen-formatering
- **Reproduser:** GET /aksje/SATS/teknisk: «snitt -0.00 R etter 0,5 % kostnad»; /aksje/TGS/regnskap: «Tilbakekjøp \| -7 \| -54 \| -0 \| 0»; /screen: Entra «2% / -0%», Stolt-Nielsen «-0.0% /år».
- **Forventet:** «0.00 R», «0», «0 %».
- **Vist:** Fortegn på null.
- **Årsak:** Format av små negative tall uten avrunding til null først.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #118 Desk-tabellen på aksjesiden viser bare klokkeslett, så en kjøring 8. nov. ser ut som 6. nov.

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /aksje/<KODE>/vurdering (Desk) ; deskpage/stockpage desk_runs-rad
- **Reproduser:** GET /aksje/SATS/vurdering: «6. nov. 2026 \| kl. 11:16 · daily» foran «6. nov. 2026 \| kl. 14:21 · daily»; kjøringen 20261108T101629 gikk søndag 8. nov. på fredagens sluttkurs.
- **Forventet:** «Kjørt 8. nov. 11:16» med dato.
- **Vist:** Samme sluttkursdato, klokkeslett i tilsynelatende feil rekkefølge.
- **Årsak:** Kolonnen «Kjørt» viser klokke uten dato.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

## Kode

### #119 Skjemaene godtar POST fra hvilken som helst nettside (ingen CSRF-/Origin-sjekk), og Host-headeren sjekkes ikke

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/server.py:351 (create_app, ingen before_request), POST-ruter server.py:446 /stock/<code>/judge, :493 /pass, :511 /forecast, :528 /update, :573 /chief/decide, :590 /review/<seq>, :609 /desk/run, :741 /watchlist
- **Reproduser:** PYTHONPATH="<worktree>\src" "<venv>\python.exe" <feilsok>\kode\csrf_demo.py <feilsok>\kode  (nytt tomt hjem; POST /watchlist med Origin https://evil.example, Sec-Fetch-Site: cross-site). Host: "<venv>\python.exe" ...\feilsok\kode\host_check.py <testhjem> (bare GET, testhjemmet ble ikke endret)
- **Forventet:** En POST fra en annen opprinnelse avvises (403) og ingenting skrives; en forespørsel med fremmed Host (attacker.example) avvises.
- **Vist:** status 200, watchlist.yaml skrevet med notatet «planted by another site»; GET /watchlist med Host attacker.example:8060 gir 200 med innhold fra research book.
- **Årsak:** Flask-appen har ingen token-, Origin/Referer- eller Sec-Fetch-Site-sjekk og ingen Host-hviteliste; host=127.0.0.1 beskytter bare mot nettverket, ikke mot skjemaer som nettleseren sender fra en annen side. Vurderingsloggen er en hash-kjede som bare kan legges til, så en forfalsket rad (judge/pass/forecast/update – samme kodemønster, ikke kjørt) kan ikke fjernes uten å bryte kjeden.

### #120 11 except-blokker svelger feil uten logg; en kodefeil vises som falsk tom tilstand («for kort historikk»)

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/server.py:143, :152, :156, :161; render.py:920, :929; book.py:248, :307; desk.py:1082; reportpdf.py:67; reports.py:311. Ingen modul i src/osloquant/dashboard importerer logging. Vises på http://127.0.0.1:<port>/aksje/<kode>/teknisk
- **Reproduser:** PYTHONPATH="<worktree>\src" "<venv>\python.exe" <feilsok>\kode\test_silent_except_known.py <testhjem>  (planter ZeroDivisionError i technicals.rows i prosessen, ber om /aksje/SATS/teknisk; ingen skriving i testhjemmet)
- **Forventet:** Teknisk-fanen sier at indikatorene ikke kunne regnes og hvorfor, og serverloggen har tracebacken.
- **Vist:** status 200; fanen viser «Grad for kort historikk» for SATS, som har flere års sluttkurser; verken siden eller loggen nevner feilen (page mentions the failure: False, log mentions the failure: False).
- **Årsak:** `except Exception:` uten `as e` og uten logging setter feltet til []/None, som sidene tolker som «ingen data». De andre stedene i dashbordet (chief.py:353, desk.py:1049, datahealth.py:112) viser feilen – disse 11 gjør det ikke.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #121 9 tester hoppes alltid over i CI, og de leser ~/osloquant-home/testdata uansett OSLOQUANT_HOME (to av dem bruker en kopi av den ekte research book)

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/testdata.py:24-26 (Path.home()/osloquant-home/testdata/2026-10-22 når OSLOQUANT_TESTDATA mangler); tests/test_dashboard.py:240-246 (personvern-skann av research book), tests/test_desk.py:385-390, tests/test_odds.py:105,109,129,138 (bl.a. at den committede signal_odds.yaml kan reproduseres), tests/test_reports.py:102,106,131,140, tests/test_insiders.py:83,87; .github/workflows/ci.yml (uv run pytest -q på ubuntu)
- **Reproduser:** cd worktree; GUARD_LOG=... OSLOQUANT_HOME=<tom mappe> OSLOQUANT_TESTDATA=<finnes ikke> PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src;<feilsok>\kode\guard" "<venv>\python.exe" -m pytest -q -p no:cacheprovider -p netguard -rs  (som i CI)
- **Forventet:** CI dekker personverngarantien for det offentlige repoet og at signal_odds.yaml (som tallene på Teknisk-fanen kommer fra) stemmer med beregningen; tester leser bare fiktive data inne i testhjemmet (Oscars faste regel).
- **Vist:** 478 passed, 9 skipped; alle 9 med «no frozen ... on this machine». skipif evalueres ved import og ser i Path.home()-stien; test_desk og test_dashboard laster testdata/2026-10-22/researchbook.yaml, en kopi av den ekte boken, ikke fiktive data.
- **Årsak:** De frosne dataene er private og ligger bare på eierens maskin; default_dir() bruker Path.home() i stedet for jg.home()/en testfixture.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #122 Frosne testdata leses fra den ekte hjemmappen selv når OSLOQUANT_HOME peker på et testhjem

*Alvor middels, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** /health (Frosne testdata) ; dashboard/testdata.py:24-26 (Path.home() / 'osloquant-home' / 'testdata')
- **Reproduser:** GET /health (OSLOQUANT_HOME=testhjem): «present – ~/osloquant-home\testdata\22. okt. 2026 …».
- **Forventet:** jg.home() / 'testdata' / DEFAULT (testhjemmet har sin egen kopi), og ingen privat absolutt sti i koden.
- **Vist:** Siden sjekker og viser den ekte hjemmappens sti.
- **Årsak:** default_dir ignorerer OSLOQUANT_HOME/oq_env.

### #123 Kalibreringssiden har ingen isolasjon per blokk: én rad med uventet form i den uforanderlige loggen gir 500 på hele siden – duplikat av #3

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

Hvor: src/osloquant/dashboard/server.py:660-686 (ingen try/except rundt D48/D52/D54-blokkene; jf. server.py:300-306 der forsiden fanger feil i de samme løkkene); forecasts.py:158

### #124 sizing.py-docstringen viser max_loss_per_group utenfor sizing:-blokken

*Alvor lav, sikkerhet høy; status: bekreftet av en uavhengig kontroll.*

- **Hvor:** src/osloquant/dashboard/sizing.py:19 (4 mellomrom i stedet for 6)
- **Reproduser:** Les docstringen sizing.py:14-19 og kopier eksemplet inn i dashboard.yaml
- **Forventet:** max_loss_per_group innrykket under sizing:, som koden leser (cfg = yaml['sizing']; sizing.py:81) og desk.py:946 sier («dashboard.yaml sizing.max_loss_per_group»)
- **Vist:** Eksemplet gir en toppnivånøkkel som sizing.config() aldri leser, så gruppegrensen er stille av
- **Årsak:** Innrykksfeil i dokumentasjonen

### #125 «Neste rapport» plukkes på fem steder med ulike regler; aksjesidens topplinje kaller enhver research-book-hendelse «Neste rapport»

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/server.py:98 (topplinjen, filtrerer ikke på rapport), server.py:224-226 og :709-712 (dekning), forecasts.py:51-55 (filtrerer på rapportord), today.py:289; vist i stockpage.py:137-141
- **Reproduser:** PYTHONPATH="<worktree>\src" "<venv>\python.exe" <feilsok>\kode\test_next_report_known.py <testhjem>  (erstatter calendar.events i prosessen med én case-hendelse «Capital Markets Day» om 5 dager for SATS; testhjemmet endres ikke)
- **Forventet:** En Capital Markets Day vises ikke som neste rapport (forecasts.upcoming gir None for samme hendelse).
- **Vist:** stock_context next_event = «Capital Markets Day»; topplinjen: «Neste rapport 14. nov. 2026» med hover «Capital Markets Day – research book». forecasts.upcoming: None.
- **Årsak:** Samme utvalg er kopiert fem ganger; bare forecasts.upcoming sjekker at en case-hendelse faktisk er en rapport.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #126 Målte signalodds caches til serveren startes på nytt i render._odds(), mens andre deler leser filen på nytt – to versjoner på samme server

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/render.py:765-767 (@lru_cache(maxsize=1) uten nøkkel) og render.py:490 (_insider_study); brukes av stockpage.py:423 (Teknisk), render.py:697/721/749/751/761/1128 (forsiden, brackets); leser på nytt: today.py:323, desk.py:338, technicals.py:65
- **Reproduser:** PYTHONPATH="<worktree>\src" "<venv>\python.exe" <feilsok>\kode\test_odds_cache_known.py <feilsok>\kode  (simulerer at signal_odds.yaml er skrevet på nytt ved å bytte signals.load_odds; repo-filen røres ikke)
- **Forventet:** Etter at filen er oppdatert (oq signals score --write) ser alle lesere ny round_trip_cost 0.0123.
- **Vist:** today.py/desk.py/technicals.py: 0.0123; render._odds(): 0.005 (første lesing) til prosessen startes på nytt. Dashbordet på 8060 går som bakgrunnsprosess i dager (D45).
- **Årsak:** lru_cache uten argument; inversion.py:137 viser mønsteret som virker (filtid i nøkkelen).
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #127 Desk-regelen «verdien må ha et tall» får koden til å skrive 0 for ukjente verdier («dag 0 %», «ROIC 0 %»)

*Alvor lav, sikkerhet middels; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/desk.py:178-179 (regelen), desk.py:459 ('0 %' når dagsendringen er ukjent), desk.py:572 (actual_roe or 0, coe_est standard 0), desk.py:576-577 (wacc_est standard 0, roic or 0), desk.py:688 (roic or 0); vises på /desk/run/<id>/<kode>
- **Reproduser:** PYTHONPATH="<worktree>\src" "<venv>\python.exe" <feilsok>\kode\test_desk_zero_known.py <feilsok>\kode  (desk.scout med en fiktiv aksje som har én økt, forced=True)
- **Forventet:** Ukjent dagsendring sies å være ukjent («dag –»), slik D41 krever for omsetning («unknown is said to be unknown, not printed as zero»).
- **Vist:** Funnverdien er «1 økter; dag 0 %». Samme mønster gir «ROIC 0 %», «har 0 %» og «WACC EST 0 %» når light-casen mangler feltet (ikke truffet i testhjemmets 74 light cases).
- **Årsak:** Finding.__post_init__ krever et siffer i verdien; der verdien mangler setter koden inn 0 eller '0 %' for å bestå regelen.
- Kan komme igjen med nye data: kandidat for datahelse-siden.

### #128 Prosent- og tusenformat kommer fra 16 hjelpefunksjoner med tre former, blandet på samme side

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** Uten mellomrom («+0.7%»): render.pct render.py:189, judgements._p judgements.py:434, signals_page._pct signals_page.py:57, weekly._p weekly.py:106 og 35 f-strenger med «:.1%». Med mellomrom («1.0 %»): technicals._pct technicals.py:55, desk._pct desk.py:400, deskpage._pc deskpage.py:108, render._pc render.py:1457, render._p render.py:646, review._p review.py:135, baserate._pc baserate.py:172, baserate._share :212, discipline.pc discipline.py:218, cli._pct cli.py:48 og 100 inline f-strenger. Tusenskille U+202F: render._int render.py:642; vanlig mellomrom: render._nok :357, render._mn :1180, stockpage._f stockpage.py:53, reportpdf._n reportpdf.py:182, desk._nok desk.py:391, sizing.nok sizing.py:37
- **Reproduser:** "<venv>\python.exe" <feilsok>\kode\fmtpage.py <feilsok>\crawl1\page_aksje_SATS.html  (og fmtex.py for eksempler); grep -c på mønstrene i src/osloquant/dashboard
- **Forventet:** Én form for prosent og én for tusenskille på hele siden (D58: tallene holder sidens egen form).
- **Vist:** /aksje/SATS: 148 «x%» (f.eks. «+0.30 (+0.7%)», «kursmål NOK 52 · +14%») og 145 «x %» (f.eks. «Shortposisjonene 0.59 %», «EBIT-margin 1.0 %»); tusen «Volum 474 974» (mellomrom) og «1 934» (U+202F, 23 ganger i Teknisk). Forsiden: 811 «x%» mot 143 «x %».
- **Årsak:** Hver modul har sin egen formatterer i stedet for én felles i dates.py/render.py.

### #129 Duplisert kode: identiske hjelpere og konstanter kopiert mellom moduler

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** judgements._p judgements.py:434 ≡ render.pct render.py:189 ≡ signals_page._pct signals_page.py:57 (samme kropp); desk._nok desk.py:391 ≡ sizing.nok sizing.py:37; baserate._share baserate.py:212 ≡ discipline.pc discipline.py:218; cli._pct cli.py:48 ≡ ui/app.py:78; judgements.home judgements.py:55 ≡ signals.home signals.py:512; goats.home goats.py:147 ≡ store.home store.py:53; market_now i goats.py:198, health.py:34, session.py:44, intraday/engine.py:259; label intraday/engine.py:1220 ≡ live/engine.py:346; load_state intraday/engine.py:944 ≡ live/engine.py:189; lightcase._num lightcase.py:147 ≈ baserate._f baserate.py:81; render._x render.py:1184 og stockpage._x stockpage.py:57 skiller seg bare på NaN-vakt; E = html.escape definert i 12 dashboard-moduler; D46-datoen "2026-11-05" hardkodet tre ganger (chief.py:38, discipline.py:120, variant.py:20)
- **Reproduser:** "<venv>\python.exe" <feilsok>\kode\dupes.py "<repo>\src\osloquant"  (AST-identiske funksjonskropper) + grep -n "^E = html.escape" src/osloquant/dashboard/*.py
- **Forventet:** Én definisjon per hjelper og én konstant for innføringsdatoen.
- **Vist:** 9 grupper AST-identiske funksjoner på tvers av moduler, 12 kopier av E, 3 kopier av datoen (én av dem ubrukt).
- **Årsak:** Moduler skrevet hver for seg over flere netter (D31–D58) med lokale hjelpere.

### #130 Død kode: ubrukte funksjoner, felt, parametere og en «if False»-gren med ødelagt HTML

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** render.view_rail render.py:361 og render.case_block render.py:801 (D57 beholder dem «for anything that calls them», men ingenting kaller dem); render.NAV render.py:186 (ingen leser); dates.today_words dates.py:89; chief.m_health chief.py:263 (ingen regel bruker den); desk StockResult.by_role desk.py:203; book.Case.claude_history book.py:42 (aldri satt eller lest); discipline.anchor_text discipline.py:92 (bare tester kaller den); lightcase.UNIT lightcase.py:40; variant.SINCE variant.py:20; pretrade.py:177 og goats.py:1257 («... if False else ...», i pretrade med '<div class="card>'); ubrukte parametere: calendar.events watch calendar.py:69 (docstring lover overvåkede selskaper; /calendar viser dem bare med ticker, f.eks. «FRO», «GJF», «ELK»), updates.write cases/cal_doc updates.py:77, allocation.walk_forward step_months allocation.py:214 (ignoreres, alltid månedlig), today-parameteren i render.py:1244/1376/1515; 49 ubrukte «# noqa» (ruff RUF100), 41 av dem «noqa: BLE001» for en regel konfigurasjonen ikke slår på
- **Reproduser:** uvx vulture src/osloquant --min-confidence 60; "<venv>\python.exe" <feilsok>\kode\refs.py "<repo>"; python -m ruff check --no-cache --select ARG,RUF100 src
- **Forventet:** Ingen funksjoner eller parametere som ingenting bruker; parametere som tas imot, brukes.
- **Vist:** refs.py: chief.m_health, dates.today_words, render.view_rail, render.case_block med 0 referanser i src og tester; discipline.anchor_text bare i tests/test_discipline.py:49,53; vulture 100 %: allocation.py:214, pretrade.py:177, goats.py:1257.
- **Årsak:** Rester etter D56/D57-omleggingen og etter at D46/D55-felter ble lagt inn andre steder.

### #131 flask og scipy importeres direkte, men står ikke i pyproject.toml

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/server.py:16 (from flask import ...), src/osloquant/allocation.py:16 (from scipy.optimize import minimize); pyproject.toml [project].dependencies (linje 15-29)
- **Reproduser:** grep -rnE "^\s*(from\|import) (flask\|scipy)" src; grep -n "flask\\|scipy" pyproject.toml
- **Forventet:** Pakker koden importerer direkte står i dependencies.
- **Vist:** Begge mangler; de kommer bare transitivt via dash (som bare brukes av den gamle ui/app.py, oq ui) og scikit-learn. Alle deklarerte pakker brukes (dash: ui/app.py:11; scikit-learn: allocation.py:39, ml/ml.py:126; openpyxl: casefile.py:17, inversion.py:31, reports.py:338; pypdf: reportpdf.py:64, reports.py:175).
- **Årsak:** Flask kom inn via dash da dashbordet ble skrevet om fra Dash til Flask.

### #132 dashboard/calendar.py skygger standardbibliotekets calendar når Python startes fra dashboard-mappen

*Alvor lav, sikkerhet høy; status: ikke kontrollert i fase 1 (kontrollrunden stoppet på brukskvoten) – kontrolleres av testen i fase 2.*

- **Hvor:** src/osloquant/dashboard/calendar.py (navnet), src/osloquant/dashboard/desktop.py:196 (har __main__, kan kjøres som fil)
- **Reproduser:** cd "<repo>\src\osloquant\dashboard" && "<venv>\python.exe" -c "import pandas"
- **Forventet:** pandas importeres fra hvilken som helst arbeidsmappe.
- **Vist:** AttributeError: module 'calendar' has no attribute 'day_abbr' (Python 3.14 sier selv: «consider renaming ...dashboard\calendar.py since it has the same name as the standard library module»). Å kjøre desktop.py som fil fra mappen vil feile på samme måte (utledet, ikke kjørt).
- **Årsak:** sys.path[0] blir dashboard-mappen, og _strptime i standardbiblioteket importerer calendar.

## Byggeforslag (ikke feil – ting som burde bygges)

- **#96 BYGG: et skjema for kill-sjekk og en måte å avslutte/pensjonere et syn på** – Ikke bygget.
- **#98 Reverse DCF «Markedet priser inn» regnes ved modellens kurs, ikke dagens. «Før du kjøper» setter tallet i kolonnen «Markedet (kursen)» med etiketten «siste år» for 2033E** – reverse_dcf leser bare de bufrede verdiene ved modellens kurs.
- **#100 Bør bygges: lagre notert (rå) kurs hver dag, eller utled den fra justert kurs og StockAction** – Rå-tabellen er valgfri i oq record.
- **#104 1D kan vises fra 15-minuttersbarene lageret allerede har, i stedet for en avslått knapp** – Stock15mKdata er ikke koblet til aksjesiden
- **#112 BYGG: fjern-knapp på Overvåkning** – Ikke bygget.
- **#133 Byggeforslag: les siste rapportdato fra meldingsbufferen for aksjer uten finanskalender** – Funksjonen finnes ikke.
- **#134 Byggeforslag: formsjekk av loggrader per kind på datahelse-siden** – Ingen formsjekk finnes.
- **#135 Byggeforslag: navnesøk i kodeboksen (/go?code=Kitron → KIT)** – Bare kode, ikke navn.
