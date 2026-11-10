# Nattøkt 10. nov. 2026 – endringer

Hver endring står her **før** den gjøres: hva som er galt i dag, hva som endres, og hvordan det prøves. Grenen er
`natt-2026-11-10` fra main (2441501). Ingenting slås sammen eller pushes. Funn-numrene viser til
`docs/feilsok/funn.md` på grenen `feilsok-2026-11-09`.

## Del 1 – kursgrafen på aksjesiden

Oscar sa ja til TradingView «hvis det gjør det bedre» (10. nov.), og til å laste ned Lightweight Charts.

### K1 Kursgrafen tegnes med TradingView Lightweight Charts™ i stedet for Plotly

**Galt i dag:**
- Grafen bygger på kursbildet på 800 dager. Derfor er 5Å alltid av, og Maks er bare drøyt to år (funn #12; #9, #10,
  #11 og #52 er samme funn).
- Plotlys datoakse er en kalenderakse, så volumsøylene får hull i helger og på helligdager.
- Det finnes ingen lysestaker, ingen log-skala, ingen hendelser, ingen linjer for kursmål eller kill-nivå og ingen
  sammenligning.
- Hover-boksen («x unified») legger seg over linjen den beskriver.
- Periodeknappens `data-r` kan få NaN når volumet mangler, og da feiler JSON.parse (funn #4).

**Endring:**
- Biblioteket legges i `dashboard/static/`, med LICENSE og NOTICE ved siden av. Det er versjon 5.2.1 (Apache-2.0,
  198 kB) fra npm.
- Selve tegnekoden skriver jeg selv (`static/pricechart.js`). Den tegner lagerets egne justerte dagskurser; ingen
  data hentes fra TradingView.
- Lisensen krever kreditering, så TradingView-logoen står i hjørnet av grafen og NOTICE-teksten med lenke under den.
- Plotly blir værende for alle andre grafer, også kjeglen på Verdsettelse (det er del 2).

**Prøves med:** enhetstester av dataene grafen får, nettlesertester av tilstanden (periode, farge, log, serietype,
hendelser, linjer, hover-boksen) og et visuelt regresjonsbilde.

### K2 Grafen får hele historikken fra lageret

**Galt i dag:** se K1, 800 dager.

**Endring:** én spørring per aksje mot de justerte dagskursene, hurtiglagret. Hurtiglageret fornyes også når siste
sluttkurs endres for samme dato, slik at funn #8 ikke gjentar seg her. Finnes ikke aksjen i lageret, faller grafen
tilbake til kursbildet.

**Prøves med:** at 5Å er på og Maks starter på første kurs når historikken er lang nok.

### K3 Valgene som briefen ber om

- **Kurve og lysestaker:** kurve (linje med fyll) er standard, lysestaker er et valg. Volum står som søyler under.
- **Periodeknappene** flytter grafen og aksene og setter avkastningen i overskriften i samme klikk. Linjen er grønn
  når perioden er opp og rød når den er ned. Det samme gjelder når du selv zoomer eller drar.
- **Log-skala** er et valg bare for 5Å og Maks.
- **Rolig rutenett.** Siste kurs står på høyre akse, og forrige sluttkurs vises som stiplet linje.
- **Krysshår og hover-boks.** Boksen legger seg alltid til venstre eller høyre for punktet, aldri over det.
- **Hendelser** kan slås av og på:
  - rapporter (NewsWeb-finanskalenderen og de nedlastede rapportene; eldre rapportdatoer finnes ikke i lageret, og
    det står på knappen)
  - eks-utbytte (Yahoo via lageret)
  - innsidehandler (NewsWeb-bufferen)
  - egne vurderinger (Oscars rader i vurderingsloggen og synet i research book; Claudes rader tas ikke med)
- **Kursmål og kill-nivå** fra synet vises som linjer med prosentavstand fra dagens kurs. Aksen strekker seg så
  begge linjene alltid er synlige.
- **Sammenligning med OSEBX og sektoren,** rebasert til samme startdag. Sektoren er det likevektede snittet av de
  andre aksjene i gruppen og er merket som egen beregning. SMA 50 og 200 er av som standard.

**Kjent og ikke rettet her:** grafen viser de justerte kursene. Feilene i justeringen (USD-utbytter, funn #5; KOG,
funn #7) blir derfor med inn i grafen. De rettes i lageret, ikke i grafen.
