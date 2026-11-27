# Ferieplan for dashbordet (fra 12. november 2026)

Oscar er på ferie noen dager. Hver gang han skriver «jobb», tas neste steg i planen, og bare det steget.

## Slik fungerer det

1. Planen ligger her, med en avkrysningsboks per steg.
2. Når Oscar skriver «jobb»: les FERIEPLAN.md, finn første steg som ikke er krysset av, og gjør det ferdig. Kryss det
   av med dato og tre linjer om hva som ble gjort.
3. Blir steget ikke ferdig: skriv under «Hvor jeg stoppet» hvor arbeidet stoppet, og fortsett der neste gang.
4. Alt arbeid går på grenen `ferie-2026-11`, med én pull request per steg inn i den grenen når CI er grønn. Ingenting
   slås sammen til main mens Oscar er borte. Dashbordet på main skal virke som i dag.
5. Hvert steg avsluttes med en kort melding til Oscar: hva som er nytt, et skjermbilde hvis det er noe å se, og om noe
   trenger en beslutning. Beslutninger samles under «Venter på Oscar», og arbeidet går videre uten dem.
6. De faste reglene gjelder som før: ekte tall med kilde og tidspunkt, bare overskrift og lenke fra nyhetskilder,
   ingen kjøp- eller selg-merkelapper, og private data holdes utenfor git. Dashbordet åpnes og det som er laget sees
   på før et steg kalles ferdig.

## Status 12. november 2026

På main (fa57025): makrosiden med FRED-data, vektede nyheter, ny meny, fondsgrafene, desken som leser nyheter og
makro, og rettelsen av de to gule varslene. Ingen åpne PR-er. En CI-kjøring tidligere i dag ble avbrutt uten at
årsaken er sjekket.

## Planen

- [x] **Steg 1: Trygt grunnlag og makrokalender** – ferdig 13. nov. 2026 (PR inn i `ferie-2026-11`, D71)
  - Den avbrutte kjøringen var ikke CI, men «goats session» (papirkontoene, som ikke skal røres). Den ble avbrutt
    fordi en nyere kjøring kom i samme kø, slik arbeidsflyten er laget. Det er ingen feil hos oss. CI på main
    (fa57025) er grønn fra 11. nov.
  - Rentemøtene til Norges Bank, Fed og ESB ligger i hver sin kildefil, kopiert fra bankenes egne sider med dato.
    SSBs tallslipp (KPI, AKU, BNP, detaljomsetning) hentes fra SSBs publiseringskalender med makrofeeden. Dashbordet
    varsler når en møteplan går tom.
  - Alt vises på /makro («Det som kommer»), /calendar (nå med norske typer) og i et nytt kort på «I dag», «Makro de
    neste sju dagene». Underveis ble to tallfeil rettet: «CC BY 4.0» og «kl. 10.00» ble vist som «4,0» og «10,00».
    Før- og etter-bilder: `Pareto Equity Research/ferie-2026-11/steg1/`.
  - Finn ut hvorfor CI-kjøringen ble avbrutt, og rett det hvis det er en feil hos oss. Bekreft at main er grønn.
  - Opprett feriegrenen. (Grenen `ferie-2026-11` ble opprettet fra main fa57025 12. nov. for å holde denne filen.)
  - Bygg makrokalenderen: rentemøtene til Norges Bank, Fed og ECB, og SSBs kalender for tallslipp (KPI,
    arbeidsledighet, BNP og detaljomsetning). Vis den på makrosiden, og vis de neste sju dagene på «I dag».

- [x] **Steg 2: Renter** – ferdig 27. nov. 2026 (PR inn i `ferie-2026-11`, D73)
  - ESB-renten (innskuddsrenten) hentes nå fra ESBs egen dataportal med makrofeeden og vises som eget kort under
    «Renter». Rentebanene fra de ti siste pengepolitiske rapportene (2/24–3/26) er skrevet av fra Norges Banks
    figurdata til en kildefil; dashbordet varsler når en ny rapport er lagt frem og filen ikke er fylt på.
  - /makro har fått «Styringsrenten mot rentebanen»: graf med faktisk styringsrente mot banene, og en tabell over hva
    hver rapport signaliserte og hva som skjedde. Renten har endt over banen for alle rapporter fra 2/24 til 4/25.
  - «Renter og sektorene» måler hver sektorgruppe mot 3 mnd statskasseveksel og 10 års stat over 156 uker, og
    rapportdagene (9). Målbart bare for 10 års stat (shipping, energi, konsum/eiendom, industri); resten står som
    «ingen målbar følsomhet». Før- og etter-bilder: `Pareto Equity Research/ferie-2026-11/steg2/`.
  - Hent ECB-renten fra ECBs egen dataportal og Norges Banks rentebane.
  - Vis styringsrenten mot rentebanen på makrosiden, slik at Oscar ser hva Norges Bank har signalisert og hva som
    faktisk har skjedd.
  - Koble rentene til sektorene som er mest følsomme for dem, målt på våre egne data.

- [ ] **Steg 3: Rapportene som har kommet** (Outlet-delen er gjort 12. nov. etter Oscars ønske, se under)
  - Outlet la frem Q3 12. november. Kjør rapportanalysen (privat, utenfor git) og oppdater casen mot forutsetningene
    og kill-kriteriene.
  - Gjør det samme for andre selskaper i research book og på overvåkningslisten som har rapportert siden sist.
  - Ikke skriv vurderinger for Oscar. Legg alt klart under «Krever en vurdering fra deg».

- [ ] **Steg 4: Felles stil på grafene på aksjesiden**
  - Kursgrafen er standarden. Gi alle andre grafer på aksjesiden samme tema: farger, skrift, rutenett, hover, og
    norsk tall- og datoformat.
  - Ta før- og etter-bilder av hver fane for SATS, Kitron og Elkem.

- [ ] **Steg 5: Måling av deskens utløsere**
  - Det som krever Oscars vurderinger, må vente. Bygg målingen nå, slik at den fylles automatisk etter hvert som
    vurderingene kommer.
  - Mål det som kan måles allerede: Flyttet kursen seg mer etter utløste hendelser enn ellers, per type utløser, på
    historiske data?
  - Vis resultatet på desksiden med antall tilfeller. Skriv det rett ut hvis en utløser ikke har hatt verdi.

- [ ] **Steg 6: Full gjennomgang**
  - Gå gjennom hele dashbordet som bruker: hver side og fane, for fem aksjer.
  - Rett det som krasjer, viser feil tall, har skrivefeil eller ser uferdig ut.
  - Sjekk at alle datakilder har hentet som de skal mens Oscar har vært borte, og at datahelse-siden viser riktig
    status.

- [ ] **Steg 7 og videre: Én forbedring per dag**
  - Velg den forbedringen som gir mest, fra researchen 10. november (`docs/loft/research.md`) eller fra det som er
    sett underveis. Skriv under «Forbedringer» hva som ble valgt og hvorfor, og bygg den.
  - Gjenta hver gang Oscar skriver «jobb», til han er tilbake.

### Når Oscar skriver «tilbake»

Lag en oppsummering på én side: hva som er bygget per steg, med skjermbilder, alt som står under «Venter på Oscar», og
hva som anbefales slått sammen til main først. Vent med sammenslåingen til Oscar sier ja.

## Hvor jeg stoppet

Steg 1 og 2 er ferdige. Neste «jobb» starter steg 3 (rapportene som har kommet, utenom Outlet).

**Etter 17. des. 2026:** Norges Bank legger frem PPR 4/26. Da sier /makro og datahelse-siden at rentebanen må fylles
på: kopier banen fra rapportens figurdata inn i `src/osloquant/resources/norges_bank_rate_path.yaml` (se D73).

**Outlet Q3 (del av steg 3) er gjort 12. nov.:** rapportanalysen ligger privat i Toolkit-mappen
`OUTLET/Q3_2026_rapportanalyse.md` (utenfor git). Steg 3 gjenstår for de andre selskapene i research book og på
overvåkningslisten.

**Notert til steg 6 (gjennomgangen):**
- Engelsk tekst: «No insider …», etter-rapport-blokken og advarslene i lett case er rettet på main 25. nov. (PR #17 og
  #18, D72). Gjenstår: lett case-avlesningen («the enterprise value pays for …») og kvalitetsgrunnene («cyclical
  group …», «investment company …») på alle aksjesider, og ukesoppsummeringen i markdown.
- Rapportleseren kan ikke lese Outlets rapport: tusenskilletegn med komma (som «1,234.5») og rader med bare prosent.

## Forbedringer (steg 7 og videre)

Ingen ennå.

## Krever en vurdering fra deg

- **Outlet etter Q3:** sju punkter i avsnitt 6 i den private rapportanalysen (`OUTLET/Q3_2026_rapportanalyse.md` i
  Toolkit-mappen, utenfor git). Tall og funn står bare der, ikke i denne filen, siden repoet er offentlig.

## Venter på Oscar

- **Rentebanen for hånd (steg 2, 27. nov.):** Norges Bank har ingen fast maskinlesbar kilde for banen, så den skrives
  av for hånd etter hver rapport (fire ganger i året). Vil du heller at dashbordet prøver å finne figurdata-filen selv
  på rapportsiden (skjørt: filnavn og ark endres fra gang til gang), eller holder det med varselet? Bygges ikke uten
  svar.

- **Nettside andre kan åpne, og skykreditten til research (spurt 11. nov.):** Hvem er «andre»: venner og rekrutterere
  med en vanlig lenke (offentlig side med få, utvalgte sider), eller noen få med tilgang til alt (lukket side)? Ikke
  en del av ferieplanen; bygges ikke før svaret kommer.
