# Aksjesiden: inventar og plassering (9. nov 2026)

Alt som står på dagens `/stock/<kode>` – i rekkefølgen det vises – og hvor det havner i den nye siden med
klebrig topplinje og sju faner (`/aksje/<kode>/<fane>`). Ingen rad uten plassering. «Ny» er elementer brevet
ber om som ikke fantes; de bygges bare av data lageret allerede har, ellers står de som «ikke tilgjengelig».

Fanene: **1 Oversikt · 2 Regnskap · 3 Verdsettelse · 4 Teknisk · 5 Rapporter · 6 Eiere · 7 Min vurdering.**
`/stock/<kode>` fortsetter å virke og viser Oversikt (eller Min vurdering rett etter at et skjema er sendt inn).

| # | Element i dag (kilde i koden) | Hvor det havner |
|---|---|---|
| 1 | Linje «gruppe · kode · kurskilde» (`stock_page` head) | Topplinjen: gruppe som grå tekst, kode som chip; kilden og tidspunktet ved hover på kursen og i «forsinket»-merket |
| 2 | `h1` selskapsnavn | Topplinjen, venstre |
| 3 | Siste kurs med endring 1 d, 20 d og i år (`.price`) | Topplinjen: kurs, endring i NOK og % (1 d). 20 d og i år flyttes til raden «Avkastning» under grafen i Oversikt |
| 4 | Lead: synets tese (`.lead`) | Min vurdering → «Investeringscase», kolonnen «Vårt syn» (sto der også) |
| 5 | Meldinger `ok`/`err` (rad logget, feil) | Rett under topplinjen, over fanene – uansett fane |
| 6 | Spørsmålet «har sannsynligheten endret seg?» etter rapport (`update_html`, D48) | Min vurdering, øverst; fanen får et lite merke «1» når spørsmålet venter |
| 7 | Kursgraf 12 mnd med MA20/MA60, volum og kjegle til bear/kursmål/bull (`price_chart`) | Deles i to: Oversikt får grafen med periodeknapper (5D–Maks, 5 års sluttkurser, MA20/MA60, volum, uten kjegle); Verdsettelse får 2 års kurs med 12-måneders-kjeglen og konsensus når det er logget |
| 8 | Investeringscase: Nedside (kill-kriterier), Vårt syn, Oppside (`case_columns`) | Min vurdering → «Investeringscase» (uendret innhold) |
| 9 | Kill-listen mot modellen (`killlist.block_html` under kill-kolonnen) | Følger med #8 til Min vurdering |
| 10 | Nøkkeltall: år som kolonner + LTM (`key_figures`) | Regnskap → underfane Oversikt |
| 11 | Høyre spalte: synet stort (rating, TP, opp-/nedside, bear/bull, sannsynligheter, horisont, syn fra, kill-nivå, konsensus) (`view_rail`) | Topplinjen får rating, kursmål og oppside i kortform; hele boksen står øverst i Min vurdering |
| 12 | Høyre spalte: Kapitalstruktur (markedsverdi, aksjer, netto gjeld, EV, EV/EBIT, P/E, P/B, FCF-yield, valuta) (`view_rail`) | Regnskap → Oversikt («Kapitalstruktur»); markedsverdi, P/E, P/B og aksjer vises også i Oversikts nøkkelrutenett og nøkkeltabell, regnet på dagens kurs |
| 13 | Høyre spalte: Neste hendelse (`view_rail`) | Topplinjen («neste rapport» med dato) og Rapporter («Siste og neste rapport») |
| 14 | Teknisk: 60 d høy/lav, RSI 14, MA20/MA60, trendord (`keys` i `stock_page`) | Teknisk, som rader med verdi, målt odds der signalet er målt, ellers «ingen målt odds» |
| 15 | Aktive signaler siste 10 økter med odds og bracket-linje (`ctx["alerts"]`) | Teknisk → «Signaler siste 10 økter» (uendret innhold, ingen merkelapper) |
| 16 | Børsmeldinger og nyheter (`fd.company_news`) | Oversikt → «Meldinger og nyheter» med filter Alle / Børsmeldinger / Innsidehandel / Short / Nyheter; innsidehandler og shortendringer flettes inn med egen type |
| 17 | Innsidehandler, meldepliktige siste 12 mnd + studielinjen (`insider_block`) | Eiere → «Innsidehandler» (og som filter i #16) |
| 18 | Shortposisjoner med graf (`insider_block`, `short_chart`) | Eiere → «Shortposisjoner over tid» |
| 19 | Rapporter: mine PDF-er, estimatrevisjon, avvik mot research book (`reportpdf.block_html`) | Rapporter → «Mine rapporter» |
| 20 | Etter rapporten: hva løkken gjorde, lett case før/etter, leseren (`afterreport.block_html`) | Rapporter → «Etter rapporten» |
| 21 | Research book: nåværende syn med stige og kill-kriterier (`case_block`, venstre kort) | Min vurdering → «Synet i research book» |
| 22 | Hva priser markedet inn – reverse DCF fra Toolkit-modellen (`case_block`, høyre kort) | Verdsettelse → «Hva prisen krever (modellen)» |
| 23 | Vurderingshistorikk, append-only (`case_block`, nederste kort) | Min vurdering → «Vurderingshistorikk» |
| 24 | Fortelling mot tall (`story.stock_html`) | Min vurdering, etter historikken |
| 25 | Inversjon: hva må gå galt for 30 % tap (`inversion_html`, D51) | Verdsettelse, under reverse DCF (samme modell som kilde) |
| 26 | Siste kvartalsrapport lest mot forrige, konsensus og casen (`report_block`) | Rapporter → «Siste kvartalsrapport» |
| 27 | Utfallsodds: mål først / kill først / ingen (`odds_block`) | Min vurdering → «Utfallsodds» |
| 28 | Prognose for neste rapport, 80 %-intervall (`forecast_html`, D52) | Rapporter, nederst (den gjelder neste rapport; skriver en rad som før) |
| 29 | «Lar være»-skjemaet (`pass_html`, D54) | Min vurdering, over vurderingsskjemaet |
| 30 | Base rates for estimatene (`baserate_html`, D47) | Rapporter, under «Siste kvartalsrapport» |
| 31 | Lett case – grunnlaget for tallene (`lightcase_block`) | Verdsettelse → «Lett case: multipler mot gruppen og hva prisen krever» |
| 32 | Claudes syn, foldet (`claude_view_block`) | Min vurdering, like over skjemaet (fortsatt foldet) |
| 33 | Desk: kjøringer og «Kjør desk»-knapp (`deskpage.stock_block`) | Min vurdering → «Desk» |
| 34 | Vedlagt desk-debatt når siden åpnes fra en kjøring (`deskpage.attached_html`) | Min vurdering, rett over skjemaet (som før) |
| 35 | Ny vurdering-skjemaet med «Før du kjøper»-advarsel, sjekkliste, base rate, fortelling, variant, konsensus, pre-mortem, Claude-spørsmål, posisjon (`judge_form`) | Min vurdering, nederst; «Før du kjøper» får i tillegg en egen knapp øverst i fanen |
| 36 | Fotnote: generert-tidspunkt, kurskilde «forsinket», privat-notis (`page`) | Uendret, under alle faner |

## Nye elementer (bare fra data som finnes)

| Element | Fane | Kilde |
|---|---|---|
| Periodeknapper 1D 5D 1M 6M YTD 1Å 5Å Maks | Topplinje + Oversikt | Lagerets daglige sluttkurser (5 år hentes). **1D er slått av**: lageret har bare dagskurser – dagens åpning/høy/lav står i rutenettet i stedet |
| Status: research book / overvåkning / ikke fulgt | Topplinje | `researchbook.yaml`, `watchlist.yaml` |
| Nøkkelrutenett: åpning, høy, lav, volum, omsetning, børsverdi, P/E, EPS, siste/neste rapport | Oversikt | Siste bar i lageret (justert); omsetning ≈ sluttkurs × volum (EST); børsverdi/P/E/EPS fra lett case på dagens kurs; rapporter fra kalenderen, leseren og research book |
| Nøkkeltabell: 12 m lav/høy, utbytte 12 m, direkteavkastning, siste eks-dato, P/S, P/B, ROE, antall aksjer | Oversikt | Sluttkurser; `StockAction` (Yahoo utbytter); lett case |
| Avkastning 5D 1M 6M YTD 1Å 5Å | Oversikt | Sluttkurser |
| Regnskap: Resultat, Balanse, Kontantstrøm – år og kvartal | Regnskap | `IncomeStatement`/`BalanceSheet`/`CashFlowStatement` i lageret (Yahoo) |
| Omsetning og resultat år↔kvartal, marginer over tid, foss fra omsetning til resultat, P/E og P/S mot egen historikk | Regnskap | Samme tabeller + årssluttkurser; aksjetall fra balansen (EST der det brukes) |
| Segmenter | Regnskap | **Ikke i lageret** – står som ikke tilgjengelig; for fulle caser ligger de i Toolkit-modellen |
| Utbytte: historikk per eks-dato og per år | Regnskap | `StockAction` |
| SOTP | Verdsettelse | Bare i Toolkit-modellen for fulle caser; vises som ikke tilgjengelig i dashbordet |
| Analytikerkonsensus | Verdsettelse | Bare det som er logget manuelt på en rad (kilde og dato) – merket «manuell»; ellers ikke tilgjengelig |
| SMA 20/50/200, RSI 14, MACD 12/26/9, volum mot snitt 1 u / 1 m / 3 m / 1 år | Teknisk | Regnet fra lagerets kurser (`technicals.py`); odds bare fra `signal_odds.yaml` der signalet er målt |
| Selskapets kvartals-/årsrapporter fra NewsWeb med lenker, webcast/presentasjon | Rapporter | `~/osloquant-home/reports/<kode>/` (lastet ned av leseren) og meldingsbufferen (120 dager) |
| Største aksjonærer | Eiere | **Ikke tilgjengelig gratis** – står som ikke tilgjengelig |

## Kontroller

- Ingen KJØP/SELG/NØYTRAL-merkelapper: Teknisk viser verdi, målt odds etter kostnad og antall tilfeller.
- Hvert nytt tall har kilde og tidspunkt ved hover (`title=`); de gamle blokkene beholder kildelinjene sine.
- Forsinkede kurser merkes «forsinket» i topplinjen, i grafens tittel og i fotnoten.
