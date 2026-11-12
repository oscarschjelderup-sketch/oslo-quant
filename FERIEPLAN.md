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

- [ ] **Steg 1: Trygt grunnlag og makrokalender**
  - Finn ut hvorfor CI-kjøringen ble avbrutt, og rett det hvis det er en feil hos oss. Bekreft at main er grønn.
  - Opprett feriegrenen. (Grenen `ferie-2026-11` ble opprettet fra main fa57025 12. nov. for å holde denne filen.)
  - Bygg makrokalenderen: rentemøtene til Norges Bank, Fed og ECB, og SSBs kalender for tallslipp (KPI,
    arbeidsledighet, BNP og detaljomsetning). Vis den på makrosiden, og vis de neste sju dagene på «I dag».

- [ ] **Steg 2: Renter**
  - Hent ECB-renten fra ECBs egen dataportal og Norges Banks rentebane.
  - Vis styringsrenten mot rentebanen på makrosiden, slik at Oscar ser hva Norges Bank har signalisert og hva som
    faktisk har skjedd.
  - Koble rentene til sektorene som er mest følsomme for dem, målt på våre egne data.

- [ ] **Steg 3: Rapportene som har kommet**
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

Ingenting påbegynt ennå. Neste «jobb» starter steg 1.

## Forbedringer (steg 7 og videre)

Ingen ennå.

## Krever en vurdering fra deg

Ingen ennå. Tall og funn fra private caser (som Outlet) står ikke her, bare en henvisning til hvor de ligger utenfor
git.

## Venter på Oscar

- **Nettside andre kan åpne, og skykreditten til research (spurt 11. nov.):** Hvem er «andre»: venner og rekrutterere
  med en vanlig lenke (offentlig side med få, utvalgte sider), eller noen få med tilgang til alt (lukket side)? Ikke
  en del av ferieplanen; bygges ikke før svaret kommer.
