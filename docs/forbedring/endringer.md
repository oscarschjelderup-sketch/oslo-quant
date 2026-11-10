# Endringer – forbedring av dashbordet

Hver endring står her før den gjøres: hvilket funn den løser (`funn.md`), hva som endres, og testen som viser det.

## Fase 2: krasj og feil tall

### E1 Én rad eller én modellfil skal ikke ta ned en hel side (#1, #3, #123, F6)
- **Problem:** `/calibration` gir 500 på én prognoserad med uventet form. En tekstcelle i modellfilen gir 500 på
  alle sju faner på aksjesiden.
- **Endring:**
  - `casefile.reverse_dcf` leser tallene som tall. Tekst i en tallcelle («n.a.», «outside range») blir `None` og
    teksten vises i kortet. En fil som ikke kan leses, eller en nøkkel som mangler i kartet, gir kortets egen
    feilmelding.
  - `forecasts.report_of` gir rapporten som `{date, what, source}` uansett form i loggen. `jg.append` avviser en
    prognose uten rapportdato.
  - `render.block` tegner en blokk for seg: feiler den, står det en feilmelding i blokken, feilen logges, og resten
    av siden vises. Brukes på hver blokk på kalibreringssiden.
- **Test:** `tests/test_forbedring.py`: kalibreringssiden svarer 200 med en tekst-rapport i loggen og viser de
  andre blokkene; aksjesiden svarer 200 med «n.a.» i modellen og med en modell uten kart-nøkkel.

### E2 Tomt lager gir en tom tilstand, ikke 500 (#2)
- **Problem:** «I dag» og «Sektorer» krasjer når lageret er tomt (ny installasjon, eller en ødelagt nedlasting).
- **Endring:** Begge sider viser «Lageret har ingen kurser» med kommandoen som fyller det.
- **Test:** begge sider svarer 200 på et tomt lager og nevner `oq record`.

### E3 Feilsider på norsk som sier hva man gjør (#97)
- **Problem:** 404 og 500 er Flasks engelske standardsider uten meny.
- **Endring:** Egne sider med menyen, hva som gikk galt, og neste steg. 500 logger feilen med sti.
- **Test:** ukjent adresse gir 404 med menyen; en rute som kaster, gir 500 med menyen og uten Python-sporing.
