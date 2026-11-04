# Gap: oppsettet mot de 30 reglene

Nattøkt 4.–5. november 2026, fase 2. Reglene og kildene står i [beste-praksis.md](beste-praksis.md).

Revisjonen er gjort på oslo-quant main (d54e078), Toolkit main (ff1c431) og de private filene. Alt ble lest, ingenting
skrevet. Tallene ble målt samme natt: lageret har sluttkurser til 4. november 2026 (Yahoo, forsinket), og
vurderingsloggen har 12 rader. To av radene er Oscars (oktober), ti er Claudes (2. november). Detaljer fra den private loggen og de private casene står bare i morgenrapporten utenfor repoet.
Ingen vurdering har nådd horisonten.

## 1. Side for side og kjede for kjede

| Side / kjede | Hva den gjør godt | Hva de beste gjør som den ikke gjør | Regel |
|---|---|---|---|
| Vurderingsskjemaet (aksjesiden) | Kan ikke endres i ettertid; begrunnelse og kill-kriterium er påkrevd; blind/sett Claude; sjekkliste og desk-kobling | Ingen pre-mortem. Ingen sjekk mot forrige kursmål. Ingen base rate. Sannsynlighetene kan være malens 25/50/25 uten at det merkes. Kill-nivå er bare påkrevd når sizing er satt | R01, R02, R07, R21 |
| Kalibrering | Brier, pålitelighet, «slå kursen står stille», blind mot sett, feilmønstre, malmerker (D30) | Skiller ikke beslutning fra utfall (Duke). Ingen måling av oppdateringer. Overskriftstallene blander inn foreløpige vurderinger | R03, R15, R05 |
| Etter rapporten (D39) | Ser hvilke rapporter som er kommet og hvem som skylder et syn | Spør ikke om *sannsynligheten* er endret, og registrerer ikke at du lot være å oppdatere | R05, R06 |
| Desken (D41) | Tvinger tre tallfestede bear-grunner; veto; logg | Kan aldri gi «klar»: Risk blokkerer alt fordi sizing-grensene ikke er satt. BUY kan logges uten desken | R19, R24 |
| «Før du kjøper» (D35) | Hva prisen krever, odds, motargumenter, sjekkliste | Ingen ytre referanse for egne estimater; ingen invertering | R07, R09, R18 |
| Toolkit-modellen | Scenarioer, variant mot konsensus (VARIANT), kill-liste, omvendt DCF, følsomhetstabeller | Ingen base rate for veksten. Følsomhetstabellene brukes ikke til å spørre hva som gir et tap | R07, R08, R18 |
| Lette caser / «Prisen krever» (D42–D43) | Hele universet; sykliske på snittmargin; ærlig om at det ikke er testet | – (ble bygget kvelden før, etter samme regler) | R26 |
| Månedsrutine | Logghode, kalibreringsnotat | Ingen kvartalsvis feilgjennomgang med faste spørsmål; ingen ukentlig måling av reglene | R16, R17 |

## 2. Hva de beste gjør som oppsettet ikke gjorde (før natten)

1. **Pre-mortem før beslutningen** (Klein, Duke): skjemaet krevde det ikke.
2. **Ytre syn før indre** (Kahneman–Lovallo, Mauboussin): ingen base rate for vekst eller margin. Én av de fulle casene har en treårs vekstforutsetning over 80-persentilen i lagerets referanseklasse.
3. **Skille beslutning fra utfall** (Duke): kalibreringen målte bare utfall.
4. **Små, hyppige oppdateringer** (Tetlock): SATS-synet fra 6. oktober har ikke blitt oppdatert etter Q3-rapporten 27. oktober. Kursen er +12,8 % siden.
5. **Invertering** (Munger): ingen side spør hva som må gå galt for et tap.
6. **Fast feilgjennomgang** (Dalio, Mawer, Buffett): ingen kvartalsrutine med faste spørsmål.
7. **Måle seg selv mot egne regler hver uke** (Dalio: prinsipper som algoritmer): reglene sto i DECISIONS.md, men ble ikke målt.
8. **Mange prognoser med rask fasit** (Tetlock): med to egne vurderinger og tolv måneders horisont kommer første fasit i oktober 2027. Brier-skåren vil ikke si noe på flere år.
9. **Unnlatelser** (Buffett 1989): det du vurderte og lot være å kjøpe, logges ikke. Kostnaden av unnlatelse kan ikke måles.
10. **Katalysator med tidsvindu** (Klarman): finnes i Toolkit-teksten, men ikke som felt som kan sjekkes.

## 3. Hva oppsettet gjør som de beste ville droppet

- **Bredden er større enn beslutningene.** Oppsettet har:
  - 64 lette caser, 30 regler og seks desk-roller;
  - tolv sider, intradag-papirkontoer og 15-minutters signaler, modellporteføljer;
  - «Trading Goats».

  På 30 dager er det logget to egne vurderinger. Mauboussin og Tetlock ville flyttet tiden fra mer maskineri til flere og raskere prognoser, slik at maskineriet har noe å måle.
- **Signaloddsene ble svakere ved nærmere test** (natten 2. november). Intradagkontoene og signalvarslene tar plass på forsiden, men har ikke vist en fordel. Taleb og Marks ville ikke latt et ikke-påvist signal stå først.
- **Modellporteføljene:** ingen oppskrift slo likevekt utenfor utvalget (D33). De beste ville arkivert siden, ikke vist den i menyen.
- **Desken uten sizing-grenser er bare et ritual:** den kan ikke ende i «klar». Enten settes grensene, eller så bør desken si tydelig at den er avskrudd.

## 4. Hvor oppsettet lar deg lure deg selv

| Felle | Hva revisjonen fant | Hva som nå er bygget (gren `natt-analysesjef`) |
|---|---|---|
| **Ankring til eget kursmål** | SATS-rapporten 2. november har kursmål 58 mot 54 i synet. Kursen var 43,95 i rapporten mot 39,75 i synet: kursen +10,6 %, kursmålet +7,4 %. Begge synene deler kursmål (D30-merket). | D46: et nytt kursmål som flytter seg minst halvparten så mye som kursen, samme vei, merkes «følger kursen». Skjemaet viser forrige kursmål og grensen før du skriver. |
| **Resulting** | Kalibreringssiden viser bare utfall; overskriften tar med foreløpige vurderinger. | D46: rutenett for beslutning mot utfall. Bare avsluttede vurderinger teller, foreløpige står ved siden av og er merket. |
| **Bekreftelsessøk** | En BUY kunne logges uten at bjørnen var hørt. Begge synene er eldre enn sjekklisten. | Prosessmålet (D46) og R19 teller BUY uten desk eller nytt motargument. |
| **For få bear-argumenter** | Desken krever tre, men skjemaet krever null. | Pre-mortem med tre ulike grunner er påkrevd (D46). Inverteringen (D51) viser hva som må gå galt for −30 %. |
| **Ingen base rates mot egne estimater** | Én full case ligger over 80-persentilen i lageret for vekst; to ligger nær midten. | D47: sjekken i skjemaet, på aksjesiden og på raden. |
| **Malens sannsynligheter som egne** | Begge synene har Toolkit-malens standardsannsynligheter. Brier vil måle malen, ikke deg. | D46/R02: teller bare som egne når de er endret eller krysset av som bevisste. |
| **Gamle syn etter ny informasjon** | SATS-synet er eldre enn Q3-rapporten. | D48: spørsmålet står på aksjesiden. Etter 14 dager teller det som «ikke oppdatert». |

## 5. Rangering av tiltakene

Poengene går fra 1 (lite) til 3 (mye) for beslutning, måling og ærlighet; innsats går fra 1 (lite) til 3 (mye).
Summen er de tre første minus innsatsen.

| Tiltak | Beslutning | Måling | Ærlighet | Innsats | Sum | Bygget i natt |
|---|---|---|---|---|---|---|
| 2. Pre-mortem i skjemaet | 3 | 2 | 3 | 1 | 7 | ja, D46 |
| 3. Beslutning skilt fra utfall | 1 | 3 | 3 | 1 | 6 | ja, D46 |
| Ankringssjekk (fra §4) | 2 | 2 | 3 | 1 | 6 | ja, D46 |
| 1. Base rate-sjekk | 3 | 2 | 3 | 2 | 6 | ja, D47 (lageret og Mauboussin) |
| 4. Oppdateringslogg | 2 | 3 | 2 | 2 | 5 | ja, D48 |
| 7. Kvartalsvis feilgjennomgang | 2 | 3 | 2 | 2 | 5 | ja, D49 |
| Fase 4: analysesjefen | 2 | 3 | 2 | 2 | 5 | ja, D50 |
| 6. Invertering fra følsomheter | 3 | 1 | 2 | 2 | 4 | ja, D51 |
| Kvartalsprognoser med rask fasit | 1 | 3 | 2 | 2 | 4 | ja, D52 |
| Løkkene på forsiden «I dag» | 2 | 2 | 1 | 1 | 4 | ja (oppdatering, prognose, forslag, feilgjennomgang) |
| Skjørhet H (Taleb) i inverteringen | 1 | 1 | 2 | 1 | 3 | ja |
| Base rates i Toolkit-rapporten | 2 | 1 | 2 | 1 | 4 | ja (Toolkit-grenen) |
| 5. Fortelling mot tall | 2 | 1 | 2 | 2 | 3 | ja, D53 (påkrevd for full case: én setning og tre tall mot modellens) |
| Unnlatelseslogg («pass») | 1 | 2 | 2 | 2 | 3 | nei – foreslått |
| Katalysator med tidsvindu | 2 | 1 | 1 | 2 | 2 | nei |
