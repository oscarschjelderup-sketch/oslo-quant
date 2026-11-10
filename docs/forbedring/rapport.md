# Forbedring av dashbordet – rapport 10. nov. 2026

Grenen er `forbedring-2026-11-10` (bygger på kursgrafen, `natt-2026-11-10`). **Ikke slått sammen, ikke pushet.**
Forhåndsvisning på testhjemmet (kopierte kurser, fiktiv research book): http://127.0.0.1:8067/. Dashbordet ditt på
8060 er ikke rørt. Hele testsettet: 627 grønne (504 før). Etter-gjennomgangen av 103 sider ga null feil.

## Hva som var galt

| Gruppe | Funn | Rettet nå | Det viktigste |
|---|---|---|---|
| Krasj og feil | 4 | 3 | `/calibration` ga 500 på én loggrad; en tekstcelle i modellfilen tok ned alle sju faner; tomt lager ga 500 |
| Feil tall og logikk | 60 | 20 | USD-utbytter justert 9,6 ganger for lite; KOG-utskillelsen som kursfall; dagsendring og 12 m lav/høy på justerte kurser; «nan» godtatt i loggen |
| Datainnhenting | 14 | 14 | noterte kurser og regnskap ble aldri hentet av kveldsoppgaven; et mislykket forsøk etterlot ingen spor |
| Visuelt og tekst | 9 (+29 om brukbarhet fra 9. nov.) | 6 (+8) | engelske tall og setninger, rødt brukt til alt, tekst høyrejustert |
| Funksjoner og flyt | 6 | 4 | avvist skjema åpnet feil fane; bekreftelsen kom fra adressen, ikke loggen |
| Kode | 5 (+13) | 1 | ingen test åpnet sidene i en ekte nettleser |

Funnene står i `docs/forbedring/funn.md`, hver endring i `endringer.md` (E1–E21), valgene i `DECISIONS.md` D60–D64.

## Hva som er rettet

- **Krasj (E1–E3):** én rad eller én modellfil tar ikke lenger ned en side. Hver blokk på kalibreringen tegnes for
  seg. 404 og 500 er norske sider med meny og neste steg.
- **Tall (E7–E10, E16):** utbytter i USD og DKK justeres med riktig kronebeløp. Kontrollert mot ekte Yahoo-historikk
  uten å skrive: FRO 1 år +82,0 % → +107,5 % (noterte kurser pluss utbytter gir +107,3 %), HAFNI +41,8 → +61,0, DNB,
  Mowi og SATS uendret. KOG 15. apr. er tatt ut av avkastningen. Dagsendring og 12 m lav/høy bruker noterte kurser.
  Loggen avviser «nan» og «inf», og oppdateringsskjemaet kaster ikke lenger det du skrev.
- **Tall, andre runde (E19–E21):** 1M, 6M, 1Å og 5Å regnes etter kalenderen (6M for SATS var +6,0 % der kalenderen
  gir +10,3 %). «other» er ikke lenger en felles kill-driver. En oppdatering kan ikke skrives etter horisonten.
  «P/E ved kurs X» regnes på kursen i navnet. Kursgrafens volumakse viste prosent i sammenligningsmodus; rettet.
- **Visuelt (E12–E14):** norsk tallformat på alle sider (`+14,5 %`, `45,50`), én aksentfarge, grønn og rød bare for
  opp og ned, tekstkolonner til venstre og tall til høyre, «I dag» på norsk med lenker til riktig fane.
- **Flyt (E15, E17):** et avvist skjema åpner «Min vurdering» med det du skrev; bekreftelsen leses fra loggen.
- **Bilder:** `forbedring-2026-11-10/for` og `/etter`, 103 sider hver (alle sider og faner for SATS, Kitron, Elkem,
  Outlet-kopien og tre uten case). Se særlig `idag.png`, `health.png` og `calibration.png`.

## Datakildene

Ny tabell «Kilder» på Datahelse og varsel på «I dag»: sist hentet, sist forsøkt, feil av de siste 30, og hvilke tall
som påvirkes. Daglige kilder er utdaterte når de ikke er hentet siden forrige børsdags stengetid (helligdager kjent).

| Kilde | Før | Nå |
|---|---|---|
| Yahoo, justerte kurser | ok, men alder målt på nyeste rad i hele tabellen | måles per aksje |
| Yahoo, noterte kurser | **stoppet 19. okt. for 63 av 64 aksjer** | hentes hver kveld (`--raw`, ingen ekstra kall) |
| Yahoo, regnskap | **aldri hentet av oppgaven**, 35 selskaper uten 3. kvartal | hentes hver søndag |
| NewsWeb (meldinger, innsidehandler, kalender) | 0 feil på 17 kjøringer, rundt 160 kall per dag | bare det som er nytt; selskapshendelser leses ut |
| Norges Bank, SSB, Finanstilsynet, RSS | 0 feil, ingen nye forsøk | tre forsøk med pause; en avis nede vises som «delvis» |
| MFN (konsensus) | enhver feil ble «ingen konsensus» | nettfeil registreres som feil |

Nye kilder: **kronekursindeksen I44 fra Norges Bank er lagt til** (NLOD, samme API). Avvist: største aksjonærer og
kalender fra IR-sider (65 ulike vilkår, lisensierte lister), Euronexts nettside. Vurdert til senere:
Regnskapsregisteret som kilde nummer to for regnskap. Ny kontroll mellom kilder: valuta (Norges Bank mot Yahoo) og
siste sluttkurs (justert mot notert).

## Ikke gjort

- **40 funn om tall og logikk står åpne**, blant dem #8 (kurscachen fornyes ikke når dagens bar skrives om), #19 og
  #20 («Prisen krever» på gammel kurs og over perimeterbrudd), #32 (multippelhistorikk på justert kurs) og #50–#51
  (Teknisk-fanens «utløst nå»).
- **Ytelse:** første visning etter oppstart er fortsatt treg (`/funds` 21 s). Ingen laste-indikator.
- **Visuelt:** ett felles Plotly-tema, og hover med kilde og tid på fellessidene. Skjemaenes feilmeldinger er
  fortsatt engelske. Beslutningslisten er fortsatt lang.
- **Kode:** typesjekk, CSRF-vern på skjemaene (#119), unntak som svelges (#120).
- **Større ideer:** Regnskapsregisteret mot Yahoo-regnskap; skanning etter utskillelser Yahoo ikke justerer for;
  en «hent nå»-knapp på Datahelse; ukentlig endringslogg per kilde.

## Før du sier ja til sammenslåing

1. **Utbytteregelen endrer den justerte historikken** for 13 aksjer første gang `oq record` kjøres. Papirkontoene
   leser samme lager.
2. **Skriptene virker først etter sammenslåing.** Kjør `oq record --raw --finance` én gang for hånd etterpå.
3. Grenen inneholder også kursgrafen (D59), som heller ikke er slått sammen.
