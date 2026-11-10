# Desken: reglene i D69 spilt av på de ti siste øktene

Kjørt 10. nov. 2026 med `desk.replay(10)` på en kopi av lageret og feedene (testhjemmet). Kurspanelet er kuttet ved
hver økt, og børsmeldingene og makroseriene er lest per den datoen. Ingenting ble skrevet.

- Speideren og filteret er eksakte i avspillingen.
- Bjørnens side bruker dagens shortregister og dagens lette caser, så «parkert» er omtrentlig.
- Perioden 27. okt.–5. nov. er rapportsesongen for tredje kvartal. Den gir flere tunge utløsere enn en vanlig uke.

| Økt | Flagget | Drept | herav svak utløser | Parkert | Klar | Klar (utløservekt) |
|---|---|---|---|---|---|---|
| 27. okt. | 62 | 25 | 24 | 32 | 5 | AUTO 10, ELK 11, EQNR 12, KID 9, SCATC 14 |
| 28. okt. | 63 | 26 | 25 | 32 | 5 | AKSO 10, BRG 20, ELK 11, EQNR 12, OKEA 11 |
| 29. okt. | 63 | 30 | 29 | 28 | 5 | BRG 9, ELK 11, EPR 14, KOG 20, SCATC 12 |
| 30. okt. | 60 | 29 | 28 | 26 | 5 | BONHR 9, BOUV 16, EQNR 10, MOWI 12, SCATC 13 |
| 2. nov. | 62 | 36 | 35 | 21 | 5 | AUTO 8, BAKKA 8, MOWI 12, NAS 9, SCATC 8 |
| 3. nov. | 62 | 24 | 23 | 33 | 5 | BWE 10, MOWI 15, OKEA 12, PEN 12, SCATC 11 |
| 4. nov. | 58 | 26 | 25 | 27 | 5 | BOUV 16, DNO 10, MOWI 14, NAS 11, SCATC 12 |
| 5. nov. | 58 | 34 | 33 | 19 | 5 | AKRBP 18, AUTO 10, HEX 9, KID 16, NAS 11 |
| 6. nov. | 59 | 43 | 42 | 12 | 4 | DNB 8, HEX 17, ORK 9, PROT 8 |
| 9. nov. | 53 | 41 | 40 | 11 | 1 | AUTO 12 |

## Mot de gamle reglene

De faktiske kjøringene med reglene fra D41, fra loggen til kveldsoppgaven:

| Økt | Flagget | Drept | Parkert | Klar |
|---|---|---|---|---|
| 9. nov. | 43 | 1 | 42 | 0 |
| 10. nov. | 40 | 1 | 39 | 0 |

## Hva tallene sier

- **Filteret gjør nå jobben.** Det dreper 24–43 av de flaggede hver dag, nesten alle fordi utløseren veier under 5.
  Før drepte det én.
- **Speideren flagger flere enn før, ikke færre.** En uvanlig uke i en driver flagger hver aksje som følger den, og
  en shortendring flagger også. Alene veier de 2, så de drepes av filteret. Det er meningen: observasjonen står i
  loggen, og støyen kommer ikke videre.
- **Klar: fem i rapportsesongen, én til fire ellers.** Taket på fem slår inn åtte av ti dager i denne perioden. Det
  er rapportsesongens skyld. I en vanlig uke er det terskelen på 8 som avgjør, og de to siste øktene ga fire og én.
- **Terskelene** (`dashboard.yaml`, `desk:`): `min_trigger` 5, `ready_trigger` 8, `max_ready` 5. Med `min_trigger` 4
  og `ready_trigger` 7 ga de samme øktene fem klar hver dag unntatt den siste, og 14–30 drept. Det var for løst.
- **Det avspillingen ikke sier:** om en utløst vurdering er verdt mer enn en tilfeldig. Det kan først måles når det
  finnes vurderinger å sammenligne (se D69).
