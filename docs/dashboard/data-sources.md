# Dashboard data sources

Free, legal data sources for the private Oslo Børs dashboard, each checked by fetching it from this laptop
on **22 Oct 2026, roughly 12:10 to 12:30 UTC**. Every URL and field below was seen in a live response unless
it is marked **unverified**. The throwaway test scripts are outside the repo (session scratchpad, `datasrc/`).

Status key:

- **VERIFIED**: fetched without a key, response parsed, fields as listed.
- **works with key**: the endpoint answered, but only with a (free) registered key.
- **blocked**: refused or reset from this machine.
- **paywalled**: data only behind a subscription or licence.

General rules for the dashboard:

1. Every number on screen shows **source + as-of timestamp + delay label**, e.g. `Norges Bank · 21.10.2026 · daily, published ~16:00 CET`.
2. Send an honest `User-Agent` such as `oslo-quant-dashboard/0.1 (private research)`. Do **not** spoof a browser UA (FRED resets the connection when you do, see section 4).
3. Cache locally and poll gently. Nothing here needs to be polled faster than every 5 minutes, and most sources need once a day.
4. The dashboard is **private**. Several terms below (NewsWeb, Yahoo, FRED, the media RSS feeds) allow private use only. Nothing fetched from them may go into the public GitHub repo, GitHub Pages or a shared artifact.

---

## 1. Oslo Børs NewsWeb: company announcements (børsmeldinger)

**Status: VERIFIED** (undocumented JSON API that the newsweb.oslobors.no single-page app calls itself).

| Item | Value |
|---|---|
| Base | `https://api3.oslo.oslobors.no/v1/newsreader/` |
| List | `POST https://api3.oslo.oslobors.no/v1/newsreader/list?issuer={issuerId or ticker}&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD&category={id}&market={code}&messageTitle={text}` |
| One message | `GET https://api3.oslo.oslobors.no/v1/newsreader/message?messageId={id}` |
| Issuer list | `POST .../v1/newsreader/issuers` (1,632 issuers on 22 Oct 2026) |
| Categories | `POST .../v1/newsreader/categories` |
| Markets | `POST .../v1/newsreader/markets` (XOSL Oslo Børs, XOAX Euronext Expand, XOAM Nordic ABM, ...) |
| Also seen in the app bundle, not tested | `attachment?messageId=&attachmentId=`, `pdf?messageId=&language=`, `announcement?clientAnnouncementId=`, `customQuery` |
| Format | JSON: `{"header": {...,"result.text":"OK"}, "data": {"messages": [...], "overflow": bool}}` |
| Auth | none |
| RSS | none found (no RSS link in the site or its JS bundle) |

**Use POST.** Observed behaviour on 22 Oct 2026:

| Query | GET | POST |
|---|---|---|
| no parameters | 84 messages, today only | 84 messages, today only |
| `issuer=1309` (Equinor) | **0** | 204 EQNR messages, 28 Oct 2025 to 20 Oct 2026 (about one year) |
| `issuer=EQNR` (ticker) | 0 | 204, identical to `issuer=1309` |
| `issuer=MOWI` / `issuer=5063` | 0 | 72 MOWI messages each |
| `issuer=1309&fromDate=2020-01-01&toDate=2026-10-22` | | **601, `overflow: true`**: the result is capped at about 600, so long ranges must be split into date windows |
| `fromDate=01.09.2026` (DD.MM.YYYY) | | HTTP 400: dates must be `YYYY-MM-DD` |

So filtering by issuer works with either the numeric `issuerId` or the ticker, when sent with POST.

Example:

```
curl -X POST -A "oslo-quant-dashboard/0.1" \
  "https://api3.oslo.oslobors.no/v1/newsreader/list?issuer=EQNR&fromDate=2026-09-01&toDate=2026-10-22"
```

Fields of a list message (sample, trimmed):

```json
{"messageId": 684373, "newsId": 636960, "title": "Equinor ASA: Tilbakekjøp av egne aksjer - tredje transje for 2026",
 "category": [{"id": 1007, "category_no": "UTSTEDERS MELDEPLIKT VED HANDEL I EGNE AKSJER", "category_en": "..."}],
 "markets": ["XOSL"], "issuerId": 1309, "issuerSign": "EQNR", "issuerName": "Equinor ASA",
 "publishedTime": "2026-10-20T06:00:11.447Z", "numbAttachments": 1, "correctionForMessageId": 0,
 "correctedByMessageId": 0, "clientAnnouncementId": "28e6d1fe-...", "infoRequired": 1, "oamMandatory": 1, "test": false}
```

`message?messageId=` adds `body` (full text) and `attachments` (`[{id, name}]`).
Issuer entries look like `{"issuerId": 1309, "symbol": "EQNR", "issuerSign": "EQNR", "name": "Equinor ASA", "isActive": 1}`.
Useful categories include 1007 (trading in own shares), 1101 (EX DATE), 1102 (mandatory notification of trade by primary insiders) and 1105 (adjustment of interest rate).

- **Update frequency / delay:** real time. Messages appear the moment the issuer publishes them, and the newest seen was 12:10 UTC on a 12:12 UTC request. Poll every 2 to 5 minutes during market hours, at most.
- **Terms:** NewsWeb's own copyright notice (shown on the site under "Disclaimer, copyright notice and privacy policy"; the text sits in `https://newsweb.oslobors.no/locales/en/translations.json`) says the database is protected under the Norwegian Copyright Act (åndsverkloven) and that its contents "may not be made available outside of the private sphere" without Oslo Børs' written consent. Downloading and storing counts as copying. The disclaimer also says Oslo Børs takes no responsibility for errors. **A private local dashboard is fine; republishing announcements (GitHub Pages, a public repo, a shared artifact) is not.** The API is undocumented and can change without notice. No robots.txt (api3 returns 404 for it).
- **Dashboard label:** `Oslo Børs NewsWeb · published 20.10.2026 08:00 CEST · real time` plus a link to `https://newsweb.oslobors.no/message/{messageId}`. Show title + time + category, and link out for the body.

---

## 2. Norges Bank open data (SDMX REST)

**Status: VERIFIED** (no key).

URL template: `https://data.norges-bank.no/api/data/{FLOW}/{KEY}?format={sdmx-json|csv}&lastNObservations=N&locale=en`
(or `&startPeriod=YYYY-MM-DD&endPeriod=YYYY-MM-DD`). `+` combines keys, e.g. `B.USD+EUR.NOK.SP`.
CSV is `;`-separated UTF-8, with `TIME_PERIOD;OBS_VALUE` as the last two columns. `&dataDetail=dataonly` also worked.

| Series | URL | Last values seen (22 Oct 2026) |
|---|---|---|
| Key policy rate | `https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R?format=sdmx-json&lastNObservations=3&locale=en` | 2026-10-19..21: 4.5 |
| NOWA (overnight) | `https://data.norges-bank.no/api/data/SHORT_RATES/B.NOWA.ON.R?format=sdmx-json&lastNObservations=3&locale=en` | 2026-10-19: 4.50, -20: 4.49, -21: 4.50 |
| 10-year government bond (generic yield) | `https://data.norges-bank.no/api/data/GOVT_GENERIC_RATES/B.10Y.GBON?format=sdmx-json&lastNObservations=3&locale=en` | 4.568, 4.539, 4.528 |
| USD/NOK and EUR/NOK | `https://data.norges-bank.no/api/data/EXR/B.USD+EUR.NOK.SP?format=sdmx-json&lastNObservations=3&locale=en` | USD 9.4036, 9.3843, 9.3573; EUR 10.5555, 10.5245, 10.512 |
| Import-weighted krone index I-44 (higher = weaker NOK) | `https://data.norges-bank.no/api/data/EXR/B.I44.NOK.SP?format=csv&lastNObservations=1&locale=en` | 2026-10-21: 108.6 |

CSV example (`EXR/B.USD.NOK.SP?format=csv&lastNObservations=2&locale=en`):

```
FREQ;Frequency;BASE_CUR;Base Currency;QUOTE_CUR;Quote Currency;TENOR;Tenor;DECIMALS;CALCULATED;UNIT_MULT;Unit Multiplier;COLLECTION;Collection Indicator;TIME_PERIOD;OBS_VALUE
B;Business;USD;US dollar;NOK;Norwegian krone;SP;Spot;4;false;0;Units;C;ECB concertation time 14:15 CET;2026-10-21;9.3573
```

SDMX-JSON shape: `data.dataSets[0].series["0:0:0:0"].observations{"0": ["4.5"], ...}`. The observation index maps to
`data.structure.dimensions.observation[0].values[i].id` (the date). Values are strings. `meta.prepared` holds the response timestamp.

- **Update frequency / delay:** business-daily. On 22 Oct at 12:12 UTC the latest observation everywhere was 21 Oct. Norges Bank says its exchange rates are published at "approximately 16:00 CET" (the series metadata calls the fixing "ECB concertation time 14:15 CET"). Fetch once a day, after 16:30 CET. NOWA and bond yields lag by one business day (observed). The publication time for those two is **unverified**.
- **Licence:** NLOD 2.0 (Norwegian Licence for Open Government Data), per the national catalogue: https://data.norge.no/en/datasets/23076ce8-b442-407c-817f-0d4ec3cbe744 ("can be used freely and requires no authentication"). Attribution: "Contains data under the Norwegian licence for Open Government data (NLOD) distributed by Norges Bank". Licence text: https://data.norge.no/nlod/en/2.0
- **Dashboard label:** `Norges Bank (NLOD) · 21.10.2026 · daily fixing, not live`. For live-ish FX use Yahoo (section 7) and label it differently.

---

## 3. SSB (Statistics Norway): salmon export price, table 03024

**Status: VERIFIED** for both the old v0 API and PxWebApi v2.

Table 03024: "Export of salmon, fish-farm bred, by commodity group, contents and week".
Variables: `VareGrupper2` (`01` = Fresh or chilled fish-farm bred salmon, `02` = Frozen), `ContentsCode` (`Vekt` = weight in tonnes, `Kilopris` = price per kg in NOK), `Tid` (weeks `2000U01` .. `2026U42`, 1,398 values).

**PxWebApi v2 (GET, preferred):**

```
https://data.ssb.no/api/pxwebapi/v2/tables/03024/data?lang=en&outputFormat=csv&valueCodes[VareGrupper2]=01&valueCodes[ContentsCode]=Kilopris&valueCodes[Tid]=top(3)
```

Response (CSV; URL-encode the brackets as `%5B` / `%5D`):

```
"VareGrupper2","Kilopris 2026U40","Kilopris 2026U41","Kilopris 2026U42"
"01",73.80,72.55,74.05
```

`outputFormat=json-stat2` also works. It returns `label`, `source: "Statistics Norway"`, `updated: "2026-10-21T06:00:00Z"`, `dimension`, `value`, and unit metadata (`base: NOK`, `refperiod: End of week`).
The `.../v2-beta/...` path still answered identically. Config: `https://data.ssb.no/api/pxwebapi/v2/config` → `maxDataCells: 800000`, formats `json-stat2, csv, px, xlsx, html, json-px, parquet`, CORS enabled, licence link `https://www.ssb.no/en/diverse/lisens`, source text "Source: Statistics Norway".
SSB's API page has mentioned a limit of 30 queries per 60 seconds. The live config reports `maxCallsPerTimeWindow: 0`, so treat 30/min as the ceiling.

**v0 (POST, legacy, still works):**

```
POST https://data.ssb.no/api/v0/en/table/03024
{"query":[{"code":"VareGrupper2","selection":{"filter":"item","values":["01"]}},
          {"code":"Tid","selection":{"filter":"top","values":["3"]}}],
 "response":{"format":"json-stat2"}}
```

→ `value: [30277, 27982, 27689, 73.8, 72.55, 74.05]` (weight for weeks 40-42, then NOK/kg for weeks 40-42), `updated: 2026-10-21T06:00:00Z`.
`GET https://data.ssb.no/api/v0/en/table/03024` returns the metadata.

- **Update frequency / delay:** weekly. Week 42 (12-18 Oct) was published Wednesday 21 Oct at 08:00 CEST, so data trail the end of the week by about 3 days. Fetch Wednesdays after 08:00.
- **Licence:** CC BY 4.0 ("Like the rest of ssb.no, the APIs use the license 'CC BY 4.0'", https://www.ssb.no/en/api). Attribute "Source: Statistics Norway".
- **Dashboard label:** `SSB 03024 · week 42 2026 (published 21.10) · weekly export price, NOK/kg`. This is an export price, not the spot price. Say so.

---

## 4. Brent crude

| Source | Status | Notes |
|---|---|---|
| Yahoo `BZ=F` via yfinance | **VERIFIED** | NYMEX-listed Brent future (Yahoo: exchange NYM, shortName "Brent Crude Oil Last Day Financ"), USD; a financially settled contract that tracks ICE Brent. `exchangeDataDelayedBy: 10`. Last 111.94 (22 Oct, 12:05 UTC). 15-minute bars available intraday. |
| FRED `DCOILBRENTEU` CSV, no key | **VERIFIED** (with a caveat) | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU&cosd=2026-10-01` → `observation_date,DCOILBRENTEU` rows; last `2026-10-20,115.22` on 22 Oct. **Works with the python-requests default UA or an honest UA; a browser-like UA got the connection reset (both curl and requests).** |
| FRED API | works with key | `api.stlouisfed.org/fred/series/observations` → HTTP 400 "Variable api_key is not set". Free key. |
| EIA API v2 | works with key | `api.eia.gov/v2/petroleum/pri/spt/data/?...facets[series][]=RBRTE` → HTTP 403 `API_KEY_MISSING`. Free registration. |
| EIA XLS history, no key | **VERIFIED** | `https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls` → sheet "Data 1", "Europe Brent Spot Price FOB (Dollars per Barrel)", 9,114 rows, last `2026-10-20 115.22`, file stamped 10/21/2026 11:22 AM. Needs `xlrd` to parse `.xls`. |

- **Delay:** Yahoo BZ=F about 10 minutes (the futures price). FRED and EIA give the **spot** assessment (Brent FOB, EIA source), daily, about 1-2 business days behind: the 20 Oct value was the latest on 22 Oct, and FRED updated it 21 Oct at 12:18 CDT.
- **Terms:**
  - EIA data are public domain ("U.S. government publications are in the public domain", https://www.eia.gov/about/copyrights_reuse.php). Citation requested: "Source: U.S. Energy Information Administration (date)".
  - FRED (https://fred.stlouisfed.org/legal/) allows personal, non-commercial use. It also prohibits storing, caching or archiving FRED content into a database, and excessive scripted access. The series itself is tagged "Public Domain: Citation Requested".
  - **Recommendation:** use the EIA XLS (public domain, cacheable) for the daily spot history and Yahoo BZ=F for the intraday futures level. Use FRED only for ad-hoc viewing, not a stored cache.
- **Dashboard labels:** `Brent fut. (Yahoo BZ=F) · 14:05 CEST · ~10 min delayed` and `Brent spot (EIA) · 20.10.2026 · daily, T+1-2`.

---

## 5. Norwegian financial media RSS (headline + link + time only)

Tested with an honest UA and parsed with `xml.etree`. `<item>` children are listed as seen.

| Outlet | Feed URL | Status | Items / freshness on 22 Oct | Item fields |
|---|---|---|---|---|
| E24 | `https://e24.no/rss2/` (`https://e24.no/rss` is identical) | **VERIFIED** | 39 items, 20 Oct 16:20 → 22 Oct 10:48 UTC. Categories: Børs og finans 24, Energi og klima 6, Næringsliv 4, ... | title, link (`?utm_medium=rss`), pubDate, guid, category, description, enclosure |
| E24 by section | `https://e24.no/rss2/?seksjon=...` | does not filter | `seksjon=boers-og-finans` and `seksjon=energi` returned the same items as the main feed. Filter on `<category>` client-side. | |
| DN (everything) | `https://services.dn.no/api/feed/rss/` | **VERIFIED** | 41 items, 21 Oct 14:16 → 22 Oct 13:41 CEST | title, link, pubDate, guid, category, author, description, content, identifier, modified, type |
| DN custom | `https://services.dn.no/api/feed/rss/?categories=børs&topics=` and `?categories=&topics=børs,olje,havbruk` | **VERIFIED** | 1 and 9 items respectively. The URL scheme comes from DN's own feed builder at https://services.dn.no/tools/rss; other values seen there include `energi`, `olje`, `havbruk`, `finans`, `makroøkonomi`, `etterbørs`, `børskommentar` | as above |
| Finansavisen | `https://ws.finansavisen.no/api/articles.rss` | **VERIFIED** | only 10 items (11:48 → 12:11 UTC, i.e. a ~20-minute window, much of it FaTV quarterly presentations). Poll every 5 min to avoid gaps. `https://www.finansavisen.no/rss` → 404. | title, link, pubDate, guid, category, creator, description (empty), modified |
| NRK | `https://www.nrk.no/toppsaker.rss`, `https://www.nrk.no/nyheter/siste.rss` | **VERIFIED**, but no økonomi feed | 99 and 20 items, current. `https://www.nrk.no/okonomi/toppsaker.rss` and `.../okonomi/siste.rss` → 404, and NRK's feed list (https://www.nrk.no/rss/) has no economy feed. Some `norge/toppsaker.rss` items lack `<link>`. | title, link, pubDate, guid, category, description, dc:date (+content) |
| Kapital | `https://ws.kapital.no/api/articles.rss` | responds but **dead** | 10 items, newest 22 Jan 2024. Not usable. `kapital.no/rss` → 404. | |
| Investtech | none found | not available | `investtech.com/rss/` and `/no/rss/` → 404, no RSS `<link>` on the site. Analyses are subscription-based (see the last section). | |

Terms and robots:

- **NRK** (https://www.nrk.no/rss/) explicitly allows free use of its RSS on your own site if items link straight to nrk.no and are labelled "NRK", headlines are not changed, and articles and images are not copied. Headline + link + time fits these terms.
- **E24**: robots.txt allows `User-agent: *` (`Disallow: /sok*?*`) but blocks AI crawlers and states that E24 "explicitly disallow[s] text and data mining" for AI training. No RSS-specific terms found.
- **DN**: the RSS page links to the general terms (https://www.dn.no/kundeservice/faq/vilkar-dnno/vilkar-dnno, which redirects to a login wall, so not read). robots.txt blocks AI crawlers. **Unverified** beyond that.
- **Finansavisen**: robots.txt sets `Crawl-delay: 10`. No RSS terms found (**unverified**).
- **Common rule for all four:** show headline + link + time in the private dashboard, link out to the article, store no article text, and do not pass feed text to an LLM or publish it.
- **Dashboard label:** `E24 · 22.10 12:48` with the headline as a link. No "delayed" label is needed for news; show the publish time.

---

## 6. Other sector drivers

| Driver | Source | Status | Details |
|---|---|---|---|
| Salmon spot index SISALMONI (weekly) and Fish Pool forwards | Fish Pool (Euronext) public site `salmonprice.com/fishpool` (fishpool.eu/prices and /sisalmoni redirect there) | **VERIFIED (undocumented JSON)** | `https://salmonprice.com/fishpool/servlets/newt/public/json/marketData` → `[{"id":"nos","label":"SISALMONI (w42)","value":6.56,"changePct":2.34,"time":"2026-10-20T14:33:35Z"},{"id":"fpi","label":"SSI NOK (w42)","value":70.00,...},...]`. `.../public/json/fpiPriceStatus?action=fpiIndex` → `[{"week":42,"indicative":false,"euro":6.56,"nok":6.56,"exchangeRate":10.6450,"exportThisYear":27689,...}]`. `.../public/json/closingPrices` → `{"id":"2026-10-21","spotCurrency":10.53,"forwardClosingPrices":[{"period":"2026-11","closingPrice":6490.00,"closingCurrency":11.10,"change":0.00},...]}`. **Units of `closingPrice` and the meaning of the duplicated `euro`/`nok` fields are unverified.** Check them against the website before charting. Weekly index, published Tuesdays; forward closes daily. No licence or terms page found, so treat it as private viewing only and poll once a day. |
| Salmon futures (Euronext, EUR) | euronext.com | not tested | Live futures quotes are exchange data. See the last section. |
| TTF gas | Yahoo `TTF=F` | **VERIFIED, thin** | "Dutch TTF Natural Gas Calendar ..." (NYM-listed mirror), EUR. Last 87.426 on 21 Oct; the last trade time was 21 Oct 15:11 UTC when checked at 12:20 UTC on 22 Oct, so it can be a day stale. `exchangeDataDelayedBy: 10`. ICE Endex official TTF is licensed. |
| Aluminium | Yahoo `ALI=F` | **VERIFIED, thin** | COMEX "Aluminum Futures, Jan-2027", USD/t, last 3088.0, last trade 08:16 UTC. LME official prices are licensed. |
| Other commodities | Yahoo `CL=F`, `NG=F`, `HG=F`, `GC=F` | **VERIFIED** | All returned 22 Oct data, 10 min delay. |
| NOK index | Norges Bank `EXR/B.I44.NOK.SP` | **VERIFIED** | See section 2 (daily). |
| Live-ish FX | Yahoo `NOK=X` (USD/NOK), `EURNOK=X` | **VERIFIED** | 9.362 / 10.492, `exchangeDataDelayedBy: 0`, timestamp 12:15 UTC. |
| Freight (dry bulk, tankers) | Baltic Exchange (BDI, BDTI, BCTI) | **paywalled/licensed** | No free official source. Proxies on Yahoo: `BDRY` (Breakwave Dry Bulk Shipping ETF, holds FFAs) and `BWET` (Breakwave Tanker Shipping ETF) both returned quotes. Label them as ETF proxies, not the index. |
| Salmon in Yahoo | `SALMON=F` | does not exist | 404 "Quote not found". |
| Oslo indices | Yahoo `OSEBX.OL`, `OBX.OL` | **VERIFIED** | OSEBX 2099.67 and OBX 2014.17 on 22 Oct, 15 min delay. `^OSEAX` returns no data. |

---

## 7. Yahoo Finance via yfinance (what oslo-quant already uses)

**Status: VERIFIED.** The repo calls Yahoo only from `src/osloquant/recorders/yahoo/client.py` (`yf.Ticker(...)`, with retries and a 5-minute history cache).
Installed yfinance is 1.1.0; PyPI has 1.7.0 (26 Aug 2026).

- **Oslo shares** (`EQNR.OL`, `MOWI.OL`, ...): `get_info()` gives `exchange: OSL`, `currency: NOK`, **`exchangeDataDelayedBy: 15`**. On 22 Oct at 12:24 UTC the latest 15-minute bar for EQNR.OL started at 12:00 UTC, consistent with a 15-minute delay.
- **Futures** (`BZ=F`, `CL=F`, `TTF=F`, `ALI=F`, `NG=F`, `HG=F`, `GC=F`): `exchangeDataDelayedBy: 10`.
- **FX** (`NOK=X`, `EURNOK=X`): delay 0 (indicative quotes, not an exchange feed).
- Fields used for labels: `regularMarketTime` (epoch seconds), `exchangeDataDelayedBy`, `currency`, `exchange`, `quoteType`. Daily and 15-minute history come from `Ticker.history(period=..., interval=...)`.
- **Terms caveat:** this is not an official API. The yfinance README says the Yahoo Finance API "is intended for personal use only" and refers to Yahoo's terms of use. Keep the data in the private dashboard. Do not redistribute raw prices (the public repo should hold code, not price dumps). Expect occasional breakage and rate limiting. Known gotchas from the project memory: quotes are zeroed overnight for some instruments, and Yahoo needs the existing cleaning rules.
- **Dashboard label:** `Yahoo Finance · EQNR.OL 14:00 CEST · 15 min delayed`. Always print the delay from `exchangeDataDelayedBy` rather than hard-coding it.

---

## Polling plan (summary)

| Source | Poll | As-of field |
|---|---|---|
| NewsWeb list (POST) | 2-5 min in market hours, 30 min otherwise | `publishedTime` (UTC) |
| Yahoo quotes | 5-15 min (data is 10-15 min delayed anyway) | `regularMarketTime` |
| Norges Bank | daily, after 16:30 CET | `TIME_PERIOD` |
| SSB 03024 | Wednesdays after 08:00 | `updated` + week code |
| EIA Brent XLS | daily | last date row |
| RSS (E24, DN, Finansavisen, NRK) | 5-10 min (Finansavisen's 10-item feed needs ≤5 min) | `pubDate` |
| Fish Pool JSON | daily | `time` / `id` |

---

## Det som bare finnes bak betalingsmur

Data the dashboard **cannot** get legally for free. Mark these as "ikke tilgjengelig" instead of scraping.

- **Real-time Oslo Børs prices and order book.** Euronext real-time and level-2 data are licensed market data. Free sources (Yahoo, Euronext's site) are delayed 15 minutes.
- **Baltic Exchange freight indices** (BDI, BDTI, BCTI, route assessments and FFA curves) are subscription-only. Only ETF proxies (BDRY, BWET) are free.
- **Official ICE Endex TTF, ICE Brent settlement data and LME aluminium official prices** are licensed exchange data. Yahoo's delayed futures quotes are the free substitute.
- **Euronext salmon futures in real time and the full Fish Pool / Sitagri SISALMONI reports.** Only the headline numbers on the public Fish Pool site are free to view. The underlying reports and history files go to subscribers, and the licence for reuse is unverified.
- **Full articles from DN, Finansavisen, Kapital and E24+.** These are paywalled. RSS gives headline, link and time only, and that is all the dashboard should use.
- **Investtech analyses and signals** are subscription-based (no RSS found).
- **Broker research and consensus estimates** (Pareto, DNB Carnegie, Arctic, Infront/Modular Finance, LSEG/FactSet) are licensed. Consensus estimates are not available from any verified free endpoint.
- **FRED API and EIA API** need a key. The key is free but needs registration and is not a paywall. The keyless alternatives above work.
