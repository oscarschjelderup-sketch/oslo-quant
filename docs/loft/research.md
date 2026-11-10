# News and macro on the dashboard – desk research (10 Nov 2026)

Method: public product pages, help centres, documentation and terms pages only; endpoints tested with one plain GET each, no login, no key. "Verified" = I saw it respond or read it today. Anything else is flagged. Licence terms are paraphrased with a link (one short direct quote only); read the linked page before relying on it.

## A. Patterns per product

**Bloomberg Terminal** (source: Bloomberg's public product pages plus older university training PDFs; the terminal itself not seen)
- Top News is edited, not chronological: a short list of the day's biggest stories with curated charts and digests, and topic versions (oil, Europe, China).
- First Word compresses a story into bullet points; Daybreak is a morning briefing of overnight events plus what is scheduled today; Morning Report is built from the user's own security list.
- The economic calendar row is: date, time, event, period, survey, actual, prior. Surprise is measured as (actual − survey median) / survey standard deviation, so surprises are comparable across indicators.
- From a chart you mark a day and jump to the news for that day (training PDF, may be dated). News-volume and attention ranking ("News Trends") shows which companies are getting unusual coverage.
- Not verified: event icons on the price chart, relevance bars in the calendar.

**Koyfin** (help centre and feature pages)
- Market news is split into fixed tabs by kind: top, global markets, corporate events, industries, macro, world economy, analyst changes.
- Watchlist news: one feed of news, filings and transcripts restricted to the user's watchlist, with sources that can be switched off.
- Market dashboards put asset classes side by side on one screen (equity indices, sectors, yields, FX, commodities), each as its own block.
- Not verified: exact tile content (level, multi-period change columns, heat colouring).

**TradingView** (support articles, blog)
- Calendar row: time, country, a small importance bar, event name, then actual / forecast / prior. Filters: country, "high importance only" toggle, one-click period (today, tomorrow, this week), category (rates, inflation, labour).
- Events are placed on the chart's time axis (switched on under chart settings → Events); which events are offered depends on the asset type.
- A new headline for the instrument being viewed appears as a small notice in the corner of the chart; click opens the story.
- News Flow filters by watchlist, symbol, market, corporate-event type, region and provider.

**Nordnet stock page** (public page read today)
- A summary strip of badges above everything: next report date, last dividend, yield.
- News list newest first, each row with relative time ("i dag 09:12"), a type label (market comment, company event, analysis, flash) and a read count; an AI summary card sits on top.
- Company events as two lists, upcoming and historical, each typed report / dividend / other; the latest report is flagged near the chart with "n days ago".

**Finansavisen** (front page could not be read: it redirects to a sign-in service. Based on cached search snippets only)
- A persistent market bar on every page: Oslo Børs, Brent, currencies, gold, with change.
- Navigation separates "Siste" (pure chronology) from "Børs" and "Aksjer"; search by ticker or company.
- Not verified: price badges on articles, most-read list.

**Investtech** (their own pages need a subscription; based on Investtech articles published on Nordnet's blog)
- One chart per horizon (short, medium, long) rather than one chart with switches.
- The chart carries the conclusion: a computed trend channel plus support and resistance levels, and a one-sentence verdict in fixed wording.
- Insider activity is reduced to one score from −100 to +100.
- Not verified: insider markers drawn in the chart, colour coding.

## A2. Synthesis (8–10 patterns)

1. **Edited top, chronological below** – three to five ranked "what matters" items first, the raw stream under it, because a time-ordered feed cannot be read in ten seconds.
2. **Every headline carries time, source and a type label** (announcement, report, macro, analysis, news) – the label lets the eye skip whole classes.
3. **Filter the feed to the owner's own universe first** (watchlist/coverage), market-wide second – relevance beats volume.
4. **One macro strip, same cell everywhere: level, change, small sparkline** – identical cells make scanning automatic; group by rates, FX, energy, metals, freight.
5. **Calendar rows as time, importance, event, actual, expected, previous** – and show surprise as a signed number, since the surprise is what moves prices.
6. **Importance as a three-step bar plus a "high only" toggle** – most days only two or three releases matter.
7. **Events on the price chart's time axis** (reports, dividends, announcements, rate decisions) with the headline on hover – this answers "why did it move that day".
8. **Upcoming and historical events as two short lists on the stock page, with "next report in n days" as a badge** – the next date is the most-used fact.
9. **Bullet digests, not paragraphs** – two or three bullets per story or per morning ("overnight", "today's schedule", "your stocks").
10. **Sensitivity next to the macro figure** – beside each macro series, list the covered stocks most exposed (beta/correlation), so macro links to the portfolio; flag unusual news volume per company.

## B. Sources table

Status: USABLE = terms clearly allow automated private use. Key = API key/registration.

| # | Source | Endpoint / URL pattern | Returns, frequency | Key | Terms (paraphrased) and link | Status |
|---|---|---|---|---|---|---|
| 1 | Norges Bank MPR data workbook (policy-rate forecast) | Report page `norges-bank.no/en/news-events/publications/Monetary-Policy-Report/2026/mpr-32026/` → link "Data – Monetary Policy Report 3/2026" (`/contentassets/<hash>/data-mpr-3-26.xlsx`). Verified: sheet "Data A – Key policy rate, output gap, CPI and CPI-ATE", incl. previous report's path | Quarterly path to 2030, 4 times a year (next 17 Dec 2026). Hash changes per report, so the link must be read from the report page | No | Material may be reproduced if Norges Bank is given as source; no changes to content. norges-bank.no/en/disclaimer/ | USABLE (semi-manual) |
| 2 | Norges Bank API – government yields | `data.norges-bank.no/api/data/GOVT_GENERIC_RATES/B..GBON+TBIL.?format=csv&lastNObservations=1` (verified) | T-bills 3/6/12M, bonds 3/5/7/10Y, daily. Bills vs policy rate = free market-implied proxy | No | Same disclaimer; listed as NLOD on data.norge.no (version not confirmed) | USABLE |
| 3 | Norges Bank API – decisions, zero-coupon curve, financial conditions | `.../api/data/ANN_KPRA?format=csv`, `.../GOVT_ZEROCOUPON?format=csv`, `.../FINANCIAL_INDICATORS?format=csv` (all verified) | Decision dates and changes; curve 12M–10Y daily; financial conditions index daily | No | As above | USABLE |
| 4 | Norges Bank calendar | `norges-bank.no/en/news-events/calendar/` (HTML, verified; no feed found) | Rate decisions, reports, surveys with date and time | No | As above | USABLE (enter by hand, 8 meetings a year) |
| 5 | US Treasury daily par yields | `home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv` (verified); XML: `.../pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=YYYYMM` | 1M–30Y, daily after US close | No | Official feed; no licence sentence found on the page (unverified) | UNCLEAR (use row 6) |
| 6 | Federal Reserve H.15 | `federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78&lastobs=5&from=&to=&filetype=csv&label=include&layout=seriescolumn` (verified) | Treasury constant-maturity yields, daily | No | Board information is public domain, cite the Board. federalreserve.gov/disclaimer.htm | USABLE |
| 7 | New York Fed Markets API | `markets.newyorkfed.org/api/rates/unsecured/effr/last/3.json`, `.../rates/secured/sofr/last/1.json` (verified) | Effective fed funds rate, target range, SOFR, daily | No | Content may be accessed manually or by automated process; keep source. newyorkfed.org/privacy/termsofuse | USABLE |
| 8 | FRED | API `api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=…`; keyless `fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` (verified for DGS10, DFF, SOFR, VIXCLS, T10Y2Y, DCOILBRENTEU, DHHNGSP, PCOPPUSDM, PALUMUSDM, PNGASEUUSDM) | Daily rates and VIX; monthly IMF copper, aluminium, EU gas | API: yes (free) | Personal non-commercial use allowed; scraping of the site discouraged; API needs key. fred.stlouisfed.org/legal/ | API: USABLE with key. Keyless CSV: UNCLEAR |
| 9 | hvakosterstrommen.no | `www.hvakosterstrommen.no/api/v1/prices/YYYY/MM-DD_NO1.json` (NO1–NO5; verified incl. tomorrow) | Hourly day-ahead price, NOK and EUR per kWh, from ENTSO-E | No | «Fritt tilgjengelig for hvem som helst, til hva som helst»; credit if shown publicly. hvakosterstrommen.no/strompris-api | USABLE |
| 10 | Energy-Charts (Fraunhofer) | `api.energy-charts.info/price?bzn=NO2&start=YYYY-MM-DD&end=YYYY-MM-DD` (NO1–NO5 verified) | Day-ahead EUR/MWh, 15-min | No | NO2: CC BY 4.0; other zones private and internal use only. api.energy-charts.info | USABLE (private only; backup) |
| 11 | NVE reservoir statistics | `biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligDataSisteUke` (verified) | Filling per price area, weekly Wed 13:00 | No | NLOD. api.nve.no/doc/magasinstatistikk/ | USABLE |
| 12 | SSB table 08799 (trade by commodity number) | `data.ssb.no/api/v0/en/table/08799` (POST query; metadata verified). Codes: 72022100_2019 ferrosilicon, 28046900_1988 silicon, 76011000_1988 aluminium | Monthly export value and kg → unit price in NOK/kg; about 6 weeks late (latest 2026M09) | No | CC BY 4.0, credit SSB. ssb.no/en/diverse/lisens | USABLE |
| 13 | SSB CPI and upcoming releases | CPI: `data.ssb.no/api/pxwebapi/v2/tables/14700` (verified; 03013 is closed). Calendar: `ssb.no/en/kommende-publiseringer` (JSON embedded in the page; month number is zero-based) | CPI monthly; release dates for CPI, national accounts, labour force | No | CC BY 4.0. No official calendar API found; page parsing is fragile | USABLE (calendar: fragile) |
| 14 | Eurostat | Data: `ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?format=JSON&geo=EA&coicop=CP00&lastTimePeriod=2`; calendar: `ec.europa.eu/eurostat/o/calendars/eventsIcal?theme=0&category=0` (both verified) | Euro-area inflation etc.; release calendar as iCalendar | No | Reuse authorised with source (CC BY 4.0). ec.europa.eu/eurostat/help/copyright-notice | USABLE |
| 15 | ECB Data Portal | `data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV?lastNObservations=2&format=csvdata` (verified) | Deposit rate and other series; meeting calendar is HTML | No | Free use if ECB is cited and changes stated. ecb.europa.eu/services/disclaimer | USABLE |
| 16 | Fed meeting calendar | `federalreserve.gov/monetarypolicy/fomccalendars.htm` (HTML, verified) | Meeting dates | No | Public domain (row 6) | USABLE (by hand) |
| 17 | BLS | `api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0` (verified); schedule `bls.gov/schedule/news_release/bls.ics` returned "Access Denied" to a script | US CPI, payrolls; release schedule | No (v1) | Terms not read | UNCLEAR; calendar blocked |
| 18 | Sodir FactPages | `factpages.sodir.no/public?/Factpages/external/tableview/field_production_totalt_NCS_month__DisplayAllRows&rs:Command=Render&rc:Toolbar=false&rc:Parameters=f&IpAddress=not_used&CultureCode=en&rs:Format=CSV&Top100=false` (verified) | Norwegian shelf production per month; synchronised daily | No | NLOD. factpages.sodir.no | USABLE |
| 19 | US Treasury Fiscal Data | `api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates` (verified) | Debt and rates data, monthly | No | Open, no token, free without restriction. fiscaldata.treasury.gov/api-documentation | USABLE (low relevance) |
| 20 | World Bank Pink Sheet | `thedocs.worldbank.org/en/doc/<hash>/related/CMO-Historical-Data-Monthly.xlsx` (link on worldbank.org/en/research/commodity-markets; verified) | Monthly prices: metals, energy incl. European gas; hash changes monthly | No | Page points to CC BY licence; licence page not opened | UNCLEAR-to-usable |
| 21 | EIA open data | `api.eia.gov/v2/…` | Weekly US oil and gas stocks, spot prices | Yes (free) | Free of charge; reuse policy not opened | UNCLEAR |
| 22 | ENTSOG transparency | `transparency.entsog.eu/api/v1/…` (responds without key) | Gas flows at Norwegian exit points, daily | No | Terms not read | UNCLEAR |
| 23 | IMF PortWatch | ArcGIS FeatureServer `services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query` (responds) | Daily ship transits by type at chokepoints – a volume proxy for tankers and bulk | No | Terms page did not load | UNCLEAR |
| 24 | GIE AGSI gas storage | `agsi.gie.eu/api` | EU storage, daily | Yes | Not read | UNCLEAR |
| 25 | ENTSO-E Transparency | `web-api.tp.entsoe.eu/api` | Day-ahead prices, flows | Yes (registration + token) | Terms page did not load; row 9 relays the same prices | UNCLEAR |
| 26 | Nord Pool | data portal | Day-ahead prices | – | Website terms forbid automatic extraction. nordpoolgroup.com/en/About-us/terms-and-conditions-for-useofwebsite/ | NOT ALLOWED |
| 27 | Baltic Exchange indices | – | Dry, tanker, LPG indices | Subscription | Licensed | NOT ALLOWED |

**Yahoo symbols** (one light request each, all listed today): `ALI=F` aluminium (COMEX), `HG=F` copper (USD/lb), `TTF=F` Dutch TTF gas (EUR/MWh), `^TNX` US 10-year yield, `^VIX`, `ZQ=F` 30-day fed funds futures (100 − price = implied rate), `BDRY` dry-bulk freight-futures ETF, `BWET` tanker freight-futures ETF. Same unofficial status as the existing yfinance use.

## B2. Recommended to build now (terms clear, no key)

- Norway rates block: rows 2–3 (bills 3/6/12M and bonds vs policy rate, decision history), plus row 1 loaded by hand four times a year to draw Norges Bank's path against the market proxy.
- US rates: row 6 (curve) and row 7 (fed funds, SOFR, target range).
- Power: row 9 for NO1–NO5 (daily average and spread between areas), row 11 for reservoir filling.
- Metals and silicon: Yahoo `ALI=F`, `HG=F`; row 12 for ferrosilicon/silicon export unit price (monthly, lagged, an average of contract and spot – a proxy, not a market price).
- Gas and freight via Yahoo: `TTF=F`, `BDRY`, `BWET`, `^VIX`, `^TNX`.
- Calendar: rows 3–4 (Norges Bank), row 13 (SSB releases), row 14 (Eurostat iCalendar), row 16 (Fed) and row 15 (ECB). "Actual" and "previous" come from the official series; there is no free consensus forecast, so use Norges Bank's own projection as "expected" for CPI where it exists, otherwise leave blank.
- Energy: row 18 for monthly shelf production.

## B3. Worth building later

- FRED API (row 8) once the owner has registered a free key: one source for US series and monthly IMF metals.
- World Bank Pink Sheet (row 20) for a monthly metals and gas cross-check after reading the licence page.
- EIA weekly stocks (row 21), GIE storage (row 24): need a key the owner registers.
- IMF PortWatch (row 23) and ENTSOG (row 22) after reading terms: volume proxies for shipping and gas.
- BLS API (row 17) after reading terms.

## B4. Rejected and why

- Nord Pool: terms forbid automatic extraction; hvakosterstrommen.no gives the same prices.
- Baltic Exchange (dry, tanker, LPG): licensed. No free index found for car carriers or LPG; use listed peers' share prices as proxy and company-reported rates.
- Market-implied NOK path from swaps/FRA and Nibor: no free official source found (not verified in detail today); the bill curve in row 2 is the substitute.
- Consensus forecasts and ready-made calendars (Bloomberg, Trading Economics, Investing.com and similar): proprietary; terms not checked today, treated as not allowed.
- Silicon/ferrosilicon spot prices: no free source found.
- FRED keyless CSV: works technically, but the site terms discourage automated extraction; use the keyed API instead.
- BLS release calendar file: refused a scripted request.
