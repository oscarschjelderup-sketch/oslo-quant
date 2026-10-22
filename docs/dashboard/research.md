# Dashboard research: what market products show, and what analysts actually use

Written 22 Oct 2026 for the private oslo-quant decision dashboard. Goal: a page that shows each day
what changed and what needs a decision, and logs every judgement so it can be measured. Not a copy of a quote page.

---

## 1. Method and sources

**Method.** Web searches (Norwegian, Swedish and English queries) plus direct reads of public product pages,
help centres, release notes, price lists, university Bloomberg guides, one academic slide deck and one vendor
factsheet. Finansavisen pages are rendered by JavaScript, so I downloaded the raw HTML and read the page
titles, meta descriptions, menu links and widget/component names from it (`curl`, 22 Oct 2026). PDFs were read by
extracting their text. I did not log in to any product and did not start any trial, so everything here describes
the public or marketing view. Anything behind a login is described only as far as the vendor's public text says.

**Access date.** Every source below was accessed on **2026-10-22**. "Read" means I read the page itself.
"Search only" means I could not open the page and the claim rests on the search engine's summary of it. Treat
those as weaker and check them before relying on them.

**Rules followed.** No features or numbers are invented. Everything is paraphrased. Vendor claims, for example
about returns, are labelled as vendor claims.

### Source list

| ID | Source | URL | Status |
|---|---|---|---|
| S1 | Nordnet DK blog: analysts' price targets in the app (24 Oct 2024) | https://www.nordnet.dk/blog/nyhed-se-aktieanalytikernes-kursmaal-og-anbefalinger-i-appen | Read |
| S2 | Nordnet NO: technical analysis services | https://www.nordnet.no/aksjer/teknisk-analyse | Read |
| S3 | Nordnet NO: Equinor stock page | https://www.nordnet.no/aksjer/kurser/equinor-eqnr-xosl | Read |
| S4 | Nordnet NO: stock inspiration hub | https://www.nordnet.no/aksjer/inspirasjon | Read |
| S5 | Nordnet NO: "this week's results" list (mid cap) | https://www.nordnet.no/aksjer/inspirasjon/lister/ukens-resultater-norge-mid-cap | Read |
| S6 | Nordnet NO FAQ: how to create a price alert | https://www.nordnet.no/faq/4253-hvordan-oppretter-jeg-en-kursalarm | Read |
| S7 | Nordnet NO FAQ: why some price alerts are delayed 15 min | https://www.nordnet.no/faq/handel/kursalarm/hvorfor-er-noen-kursalarmer-forsinket-med-15-minutter | Read |
| S8 | Nordnet SE FAQ: overview of all price alerts | https://www.nordnet.se/faq/4216-var-kan-jag-se-en-oeversikt-av-alla-mina-kurslarm | Search only |
| S9 | Nordnet NO price list | https://www.nordnet.no/kundeservice/prisliste | Read |
| S10 | Nordnet NO: the app | https://www.nordnet.no/tjenester/handelstjenester/nordnets-app | Read |
| S11 | Nordnet NO blog: five favourite app features (15 Jan 2026) | https://www.nordnet.no/blogg/mine-5-favorittfunksjoner-i-nordnet-appen-akkurat-na | Read |
| S12 | App Store (NO): Nordnet app listing | https://apps.apple.com/no/app/nordnet-aksjer-og-fond/id345038631 | Read |
| S13 | Nordnet NO: market page | https://www.nordnet.no/markedet | **Could not be read (HTTP 404)** |
| S14 | Investtech front page (NO) | https://www.investtech.com/no/ | Read |
| S15 | Investtech stock-analysis page, logged out | https://www.investtech.com/main/market.php?CompanyID=91201110&product=241 | Read (access-denied screen) |
| S16 | Nordnet blog (Investtech partner article): 20 strongest stocks on Oslo Børs (1 Sep 2026) | https://www.nordnet.no/blogg/de-20-sterkeste-aksjene-pa-oslo-bors | Read |
| S17 | Placera: Investtech analysis (9 Nov 2021) | https://www.placera.se/nyheter/tva-aktier-med-kopsignaler-ett-salj-2021-11-09 | Read |
| S18 | DNB: portfolio analysis with Investtech | https://www.dnb.no/dnbnyheter/no/bors-og-marked/portefoljeanalyse-aksjehandel | Search only |
| S19 | Infront news: Professional Terminal updates (13 Mar 2025) | https://www.infront.co/global/en/news-and-events/news/infront-professional-terminal-latest-updates-and-optimisations.html | Read |
| S20 | Infront news: product update (19 Jun 2025) | https://www.infront.co/global/en/news-and-events/news/infront-products-update-latest-features-whats-coming-next.html | Read |
| S21 | Infront help centre: release notes 8.7.100 | https://infront-professional-terminal.helpcenter.infront.co/en/infront-professional-terminal/8.7.200/release-notes-8-7-100 | Read |
| S22 | The Wealth Mosaic: Infront blog (30 May 2025) | https://www.thewealthmosaic.com/vendors/infront/blogs/powerful-updates-give-you-the-edge-with-infront-pr/ | Read |
| S23 | Infront: Direkt News Services | https://www.infront.co/global/en/solutions/modules/direkt.html | Read |
| S24 | Infront (2019): "smoother, smarter workflow" article | https://www.infrontfinance.com/news/get-a-smoother-smarter-workflow-in-the-infront-professional-terminal | **Could not be read (redirects to a news index)**, search only |
| S25 | Infront: example desktops | https://www.infrontfinance.com/products/professional-terminal/example-desktops/ | **Could not be read (redirects to home page)**, search only |
| S26 | Infront home page | https://www.infront.co/global/en.html | Read (no Professional Terminal product page linked) |
| S27 | Koyfin Help: getting started | https://www.koyfin.com/help/getting-started-with-koyfin/amp/ | Read |
| S28 | Koyfin: features | https://www.koyfin.com/features/ | Read |
| S29 | Koyfin: pricing | https://www.koyfin.com/pricing/ | Read |
| S30 | Koyfin: alerts feature page | https://www.koyfin.com/features/alerts/ | Read |
| S31 | Koyfin: LLM info page | https://www.koyfin.com/llm-info/ | Read |
| S32 | Koyfin blog: watchlist with analyst ratings, price alerts, valuation (updated 21 Aug 2026) | https://www.koyfin.com/blog/get-analyst-ratings-price-alerts-valuation-data-watchlist/ | Read |
| S33 | Koyfin Help: Earnings History snapshot | https://www.koyfin.com/help/earnings-history/ | Search only |
| S34 | Koyfin Help Center alerts article (alert quotas per plan) | URL not captured, koyfin.com/help domain | Search only |
| S35 | Finansavisen front page (HTML) | https://www.finansavisen.no/ | Read (raw HTML) |
| S36 | Finansavisen /bors market overview (HTML) | https://www.finansavisen.no/bors | Read (raw HTML) |
| S37 | Finansavisen /watchlist | https://www.finansavisen.no/watchlist | Read (raw HTML) |
| S38 | Finansavisen /screener | https://www.finansavisen.no/screener | Read (raw HTML) |
| S39 | Finansavisen /kalender | https://www.finansavisen.no/kalender | Read (meta only, content is JS) |
| S40 | Finansavisen /blokkhandler | https://www.finansavisen.no/blokkhandler | Read |
| S41 | Finansavisen /aksjonaerregister | https://www.finansavisen.no/aksjonaerregister | Read |
| S42 | Finansavisen /rapporter | https://www.finansavisen.no/rapporter | Read |
| S43 | Finansavisen /investorchat | https://www.finansavisen.no/investorchat/ | Read (title only) |
| S44 | Finansavisen /investor (URL given in the brief) | https://www.finansavisen.no/investor | **Could not be read: HTTP 404 on 22 Oct 2026** |
| S45 | App Store (NO): Finansavisen app | https://apps.apple.com/no/app/finansavisen/id434568179 | Read |
| S46 | Univ. of Delaware: Bloomberg functions list | https://lerner.udel.edu/seeing-opportunity/bloomberg-functions-list | Read |
| S47 | Corporate Finance Institute: Bloomberg functions list | https://corporatefinanceinstitute.com/resources/equities/bloomberg-functions-shortcuts-list/ | Read |
| S48 | Duke library: Bloomberg functions | https://guides.library.duke.edu/bloomberg/functions | Read |
| S49 | HKUST library: Bloomberg function codes | https://libguides.hkust.edu.hk/bloomberg/function-codes | Read |
| S50 | York Univ. library: Bloomberg equities | https://researchguides.library.yorku.ca/bloomberg/equities | Read |
| S51 | The Wealth Mosaic: Bloomberg Launchpad | https://www.thewealthmosaic.com/vendors/bloomberg/bloomberg-launchpad/ | Read |
| S52 | Bloomberg Professional: solutions for equity analysts | https://professional.bloomberg.com/solutions/equity-analyst | Read |
| S53 | Bloomberg webinar: earnings-season tools for analysts | https://professional.content.cirrus.bloomberg.com/professional2023/insights/webinar/navigating-earnings-season-essential-bloomberg-tools-for-analysts | Read |
| S54 | University library guides listing EVTS (events calendar) and ALRT | e.g. https://web.stevens.edu/hfslwiki/images/b/b0/Bloomberg_Tutorial_Commands.pdf | Search only (certificate error on fetch) |
| S55 | Third-party Bloomberg price estimates (eulerpool, costbench) | https://eulerpool.com/blog/bloomberg-terminal-cost ; https://costbench.com/software/financial-data-terminals/bloomberg-terminal/ | Search only |
| S56 | Ben-Rephael, Carlin, Da, Israelsen: "All in a day's work: what do we learn from analysts' Bloomberg usage?" (ABFER 2023 slides) | https://www.abfer.org/media/abfer-events-2023/annual-conference/slides-accounting/Presentation-Da.pdf | Read (PDF text) |
| S57 | Same paper, full PDF | https://academicweb.nd.edu/~zda/analyst_AWL.pdf | **Could not be read (fetch failed)**, search only |
| S58 | Vault: day in the life, research associate (Deutsche Bank) | https://legacy.vault.com/investment-banking-research-associate/day-in-the-life-of | Read |
| S59 | eFinancialCareers: day in the life, Citadel equities analyst (1 Sep 2022) | https://www.efinancialcareers.com/news/2022/09/citadel-hedge-fund-day-in-the-life | Read |
| S60 | LSEG Workspace factsheet for buy-side analysts | https://www.lseg.com/content/dam/data-analytics/en_us/documents/fact-sheets/final_re1570059_ws_ia_rpm_factsheet_buy_side_analyst_a4_v5_web.pdf | Read (PDF text) |
| S61 | Bloomberg Investment Research Data Trends survey (BigDataWire) | https://hpcwire.com/bigdatawire/2025/01/16/bloomberg-survey-reveals-data-challenges-for-investment-research | **Could not be read (HTTP 403)**, not used |

---

## 2. Per product

### 2.1 Nordnet (web and app, Norway)

**Overview / home page.**
- The logged-in home page cannot be read without an account. Nordnet describes the app's start view as one place
  for your holdings, world exchanges, share prices, order activity and currency rates, plus a news feed on the shares you follow [S10].
  The App Store listing adds progress tracking, top and theme lists, articles and campaigns [S12].
- The public market page `nordnet.no/markedet` returned 404 [S13]. The public "inspiration" hub shows curated lists
  (high yield, monthly dividend, dividend aristocrats, ETF favourites), a table of popular stocks filterable by country with
  daily and 1-year change, turnover and number of Nordnet owners, plus Academy articles and blog posts [S4].
- An earnings-week list shows the Oslo Børs companies reporting this week, with today's change, market value, number of owners and report date [S5].
- The app has an "Analyse" tab for the portfolio: asset mix, annual growth rate, dividends, last month's return and sector split [S11].

**Single-stock page** (web, Equinor read logged out) [S3], top to bottom:
- Header with name, ticker, buy/sell buttons, next report date and dividend info (ex-date, yield).
- Price chart. Free indicators on every stock page: SMA, EMA, Bollinger Bands, MACD, RSI, Stochastic, built on Highcharts with Morningstar data [S2].
- Order book (bid/ask) and recent trades.
- Funds/ETFs that hold the stock; "customers also viewed".
- Corporate events (upcoming and past reports, AGM, dividends), sourced from Quartr.
- News: an AI-written summary plus headlines from several providers, with a note that Nordnet did not write or review them.
- Forum (Nordnet Social).
- Key figures from FactSet and Nordnet: market cap, turnover, EBIT, EPS, DPS, yield, P/E, P/B, PEG, P/S, number of Nordnet owners, short-selling status.
- Company and security details (description, CEO, ISIN, sector, margin and shorting eligibility).
- Analyst data: **shown only to logged-in users**.
- Financials 2022–2025 (multiples, income statement, balance sheet, cash flow), sourced from FactSet.
- The page itself does not label prices as real-time or delayed [S3].
- Analyst feature: price targets and recommendations from FactSet. Announced on 24 Oct 2024 for the app, under an "Analytikere" menu below the chart, covering Nordic, German, UK, US and Canadian listings [S1]. The 2026 blog post confirms the app summarises buy/hold/sell views [S11].
- **"Mine notater"**: private notes per stock or fund explaining why you buy or are considering it, visible only to you [S11].
  This is the closest consumer analogue to a judgement log I found.
- App extras: compare up to nine securities on one chart [S11]; listen to or read Quartr company presentations [S10][S12].

**Alerts and watchlists.**
- Price alerts in the app: above or below a level, set as an exact price or a % move from the current price. Delivered as push notifications [S6].
- Alerts for securities outside the Nordics are delayed 15 minutes but free [S7]. Funds cannot have price alerts (listed as a related FAQ title) [S6].
- Per a search summary of a Swedish FAQ, the web shows all alerts under the account overview, but the app has no single alert page [S8] (search only).
- Watchlists: own lists, plus curated theme and industry lists [S10][S12].

**Behind login / paywall.**
- Analyst targets and recommendations need a login (FactSet data) [S3].
- Real-time Oslo Børs quotes for private customers: Level 1 and Level 2 (order depth) streaming are listed as free. Level 2 is 715 NOK for professional customers [S9].
- Investtech "Investor + Norden" via Nordnet costs 299 NOK/month. Børsdata is a paid third-party add-on, with a one-month trial and 30% discount for Active Trading and Private Banking customers [S2].

### 2.2 Investtech (investtech.com)

**Overview / home page** [S14].
- One free sample analysis per day, a webinar list, a "how it works" section, pricing tiers and a free daily newsletter.
- The front page has no market comment, top list or Hausse index in its public text. Those are inside the paid tiers.

**Single-stock page.**
- Logged out, a full stock report shows an access-denied screen asking for the "Trader" level or a free trial [S15]. I could not read a full report directly.
- From Investtech's own published analyses: every stock gets an automatically drawn trend channel, support/resistance levels and chart formations.
  Each analysis covers trend, support/resistance and insider trading, and ends with an overall view for the medium term (1–6 months) plus a recommendation (for example buy or sell) [S17].
- Investtech says it has researched what happens after its signals. It reports, for Stockholm, that stocks in rising channels tended to beat the market and falling ones to lag, with short- and medium-term channels built on about 5 months and 1.5 years of data [S17]. **This is a vendor claim.**
- **Investtech Score**: a composite on −100 to +100. It combines trend (the model tests about 80,000 trend combinations per stock), support/resistance, formations, volume balance, insider buying/selling, seasonality and risk (liquidity, volatility). It is computed daily for about 20,000 stocks. **The weighting is not disclosed** [S16].
- Market-level gauges: short- and long-term "Hausse" optimism indices and an insider barometer [S17].
- Portfolio "health check": a health score for how robust a portfolio is to normal market moves, computed as if all stocks were equally weighted [S18] (search only).

**Alerts and watchlists.**
- The Investor tier includes price alerts. Institutional adds "alarms" and self-defined universes [S14]. I found no public documentation of how alerts are configured.

**Behind paywall** [S14].
- Everything except the daily free sample and newsletter.
- Investor €19/month: analysis across many exchanges, medium/long-term charts, buy/sell signals, health check, Today's Case, Top 50, price alerts.
- Trader €39/month: adds short-term analyses, morning reports, trend signals, pivot points, candlesticks.
- Professional €79/month: adds overall analysis, stock selection, Hausse indices, compare stocks, seasonality, ranking by signals.
- Institutional: custom price.
- Through Nordnet the Norwegian bundle is 299 NOK/month [S2].

### 2.3 Infront Professional Terminal

Note: Infront's old product and help URLs now redirect to the new infront.co site. The new home page links no Professional Terminal product page [S26],
so the evidence is mostly release notes and news posts.

**Overview / desktops.**
- The terminal is built from user-arranged "desktops" of windows.
- An Infront example (search only, page now redirects) describes a desktop with a watchlist of Norwegian salmon producers, linked to Company Overview, Seasonality Matrix and Full Infront Estimates windows. Full estimates need an Infront Equity Analytics subscription [S25].
- News comes from Infront's Direkt service: real-time Nordic market news written by editors in Stockholm and Oslo, plus analyst-collected consensus as a service [S23].

**Single-instrument view.**
- Company Overview, seasonality and estimates windows as above [S25] (search only).
- Analytics widgets cover fundamentals on more than 45,000 listed companies [S20].
- I found no public description of the Company Overview window's contents, so it is not described further.

**Alerts and watchlists** (8.7.100, 2025) [S19][S21][S22]:
- "Dynamic Terminal Alerts" on price, volume, technical indicators, estimates or ratings.
- Field-to-field conditions, for example last price crossing the 50-day moving average.
- Recurring alerts that re-arm after triggering.
- Alerts on any instrument field, including trading halts and news updates.
- Order-entry alerts.
- Filter-based notifications on market lists and watchlists (for example volume above average), shown in ticker windows.
- All notifications go to an alert log / alert manager.
- Custom columns (for example % versus a benchmark) in watchlists and market lists, with live export to Excel [S19][S20].
- Older (2019) material, search only [S24]: an order book embedded in the watchlist, news filters (instrument, watchlist, source, headline/body text) that can be saved as news alerts, and calendar-event alerts with a countdown timer.

**Behind paywall.**
- The whole terminal is a professional subscription. No public prices were found.
- Full consensus estimates need the Equity Analytics add-on [S25] (search only).
- The terminal ties into Infront's order gateways and FIX routing, and has trading journals with P&L [S20].

### 2.4 Koyfin

**Overview / home page.**
- My Dashboards: user layouts combining watchlists, charts, news feeds and scatter plots [S27].
- Market Dashboards: curated cross-market views, including economic data [S27][S28].

**Single-stock page ("Snapshot" / Security Analysis).**
- Described as a top-down view of essential security information, with an Analyst Estimates section [S28].
- I found no help page listing every Snapshot section. Search summaries mention a Key Data block (yield, average volume, beta, multiples) and FY sales/EPS estimates with y/y change [S33] (search only).
- An Earnings History snapshot has two parts: a results-versus-estimates chart and a surprise history table, for sales, EBITDA, EBIT or EPS [S33] (search only).
- Charting through Historical Graph (G) for any series [S27].
- Market data comes from S&P Capital IQ and news from MT Newswires [S31].

**Alerts and watchlists.**
- Alerts on price, technical signals and valuation levels (for example P/E, EV/EBITDA) [S30].
- Alerts on new press releases, news, transcripts and filings [S30].
- One alert can apply to a whole watchlist or portfolio [S30].
- Delivered by desktop notifications, email or mobile push, and managed in one Alerts hub with search, filter and edit [S30].
- Plan quotas (search only): Free 5, Plus 50, Premium 500 [S34].
- Watchlists: user lists with 500+ selectable metric columns. Koyfin suggests average analyst rating (1–5), FY1 revenue estimate change, industry and **next earnings date** as columns [S32].

**Behind paywall** [S29].
- Free tier: 2 years of financials, 1 year of estimates, 2 watchlists, 2 screens, 2 dashboards, limited news and limited snapshots.
  Koyfin's LLM-info page says the free plan has one watchlist [S31], so the vendor's own pages disagree.
- Plus $39/month: 10 years of financials and estimates, transcripts, filings, premium news, 100K+ company snapshots.
- Premium $79/month: adds portfolio analytics and custom formulas.
- Advisor tiers $209–299/month.
- The pricing page does not say whether quotes are real-time or delayed.

### 2.5 Finansavisen (market section; the brief's "Finansavisen Investor")

`finansavisen.no/investor` returned **HTTP 404** on 22 Oct 2026 [S44]. The market functions now sit under several paths, found in the site header menu [S35]:
`/bors`, `/aksjer`, `/indekser`, `/valuta`, `/raavarer`, `/renter`, `/fond`, `/krypto`, `/screener`, `/kalender`, `/rapporter`, `/blokkhandler`,
`/aksjonaerregister`, `/watchlist`, `/investorchat`, `/forum`, `/bjellesauer`. Price data is supplied by Millistream (named in the page metadata and the shareholder register) [S36][S41].

**Overview page (`/bors`)** [S36]. From the meta description and component names:
- Market overview header and marketplace selector.
- Winners and losers, most traded, "hot stocks".
- Short positions; all-time highs and lows.
- Sectors.
- Dividends and a calendar.
- Latest and upcoming quarterly reports, earnings calls and presentations.
- A market-news feed, a live TV player, and a watchlist/portfolio widget.

The front page adds a stock-analysis article widget (articles tagged "aksjeanalyse"), latest forum posts and investor-relations content (labelled as advertiser content) [S35].

**Single-stock page.** I could not find the URL pattern. `/aksjer/EQNR` and similar returned 404, and `/aksjer` is rendered by JavaScript [S36]. So **the stock page was not read**.
The App Store listing mentions graphs and market data on company profiles [S45].

**Other tools.**
- Screener: Nordic and US stocks by valuation, quality, momentum and dividend, with ready-made screens [S38].
- Financial calendar of reports and presentations [S39][S42].
- Block-trade list for Oslo Børs: time, ticker, type, shares, price, value and % of shares [S40].
- Shareholder register built on Tax Administration year-end data, updated once a year [S41].
- AI chat over Finansavisen news, exchange notices and TDN articles [S43].
- TDN newswire items such as broker upgrades and target changes appear under `/tdn/` URLs (seen in search results). Exchange notices appear under `/borsmeldinger/`.

**Alerts and watchlists.**
- The watchlist needs a free registration. It promises real-time prices and key figures for your holdings, return history, relevant quarterly reports, dividend updates and news, synced to the app [S37].
- The app lists push notifications, live Oslo Børs data and real-time ticker prices [S45].

**Behind paywall.**
- The subscription page is rendered by JavaScript and no prices could be read. The App Store lists in-app purchases at 79 NOK [S45].
- Articles sent me through a login (SSO) redirect when fetched. I cannot confirm from this which articles are paywalled.

### 2.6 Bloomberg Terminal

**Overview: Launchpad (BLP).**
- A customisable workspace of multi-asset monitors, alerting tools, charts and news, laid out to the user's workflow, with Instant Bloomberg chat [S51][S46][S48].
- Market overview functions:
  - WEI: world equity indices [S46][S47]
  - IMAP: global equity performance [S46]
  - MOST: most active stocks, by volume, change or 52-week highs/lows [S46][S47]
  - TOP / N: top news stories [S46][S47]
  - READ: most-read news [S48]

**Single-stock functions:**
- DES: description, the usual starting point [S46][S47][S48].
- GP: price chart [S46][S47][S48].
- CN: company news [S46][S47][S48].
- ANR: analyst recommendations. Tracks changes of opinion and how accurate past calls were [S47].
- EE: earnings estimates, surprises and history [S46][S47].
- ERN: past earnings versus consensus [S46][S47].
- RV: relative valuation against peers [S46][S47][S50].
- FA: financials and estimates [S47][S48].
- DVD: dividends; HP: price history; MGMT: management [S46][S47].
- CACS: corporate-action calendar [S47].
- EVTS: events and earnings calendar [S54] (search only).
- EQS: screener [S48][S49][S50].
- BI: Bloomberg Intelligence research [S47][S48].

**Alerts.**
- ALRT sets alerts on price moves [S46].
- Bloomberg's equity-analyst page stresses customisable alerts, custom news feeds, AI news summaries, and comparing KPI estimates with actuals right after results [S52].
- An earnings-season webinar covers the MREP customisable morning report and company briefs set up on covered names [S53]. The page does not describe MREP's contents.

**Behind paywall.**
- Everything. Bloomberg publishes no list price. Third-party estimates put a seat at roughly $24k–32k per year, with exchange data fees on top [S55] (search only, not verified).

---

## 3. What analysts actually use (workflow)

**Evidence found:**
- **The day starts with news and an overnight scan.**
  - A sell-side research associate (Deutsche Bank) checks news on the day's events and sector developments around 7:30, joins an 8:00 team meeting on news, market and plan, listens to a 9:00 earnings call, then updates the Excel model and drafts a note before compliance [S58].
  - A Citadel equities analyst checks overnight moves and their stocks from 6:30, reads chats and sell-side research, scans company news from 7:30, and joins a 7:45 team meeting with a trader update. They watch reactions after the open but deliberately avoid staring at screens, then spend hours on ideas and models [S59].
- **Most screen time goes to monitoring coverage for thesis-relevant change, not to quotes.**
  - Bloomberg describes the analyst job as coverage monitoring with alerts, news feeds and estimate-versus-actual checks after results [S52], and pushes a morning report (MREP) and company briefs for earnings season [S53].
  - LSEG's buy-side factsheet bundles the monitoring view into one "Watchlist Pulse": upcoming events, predicted earnings surprise, quant model score moves, new broker reports and new filings in one place, with alerts. It describes comparing your own model with consensus as a core step [S60].
- **Effort and accuracy can be measured.** A study of minute-by-minute Bloomberg login data for 336 sell-side analysts at 42 brokers (Sep 2017 – Mar 2021) found:
  - Each extra hour of average workday is associated with about 0.3–0.5 more EPS forecasts (~2%) and 0.54 more target-price forecasts (~5%).
  - One more hour of workday, or being in the high "away days" group, is associated with roughly 2% and 5% better forecast accuracy respectively.
  - Travelling analysts' forecast errors rose more in the COVID lockdown [S56]. The full paper could not be fetched [S57].
  - Relevance: the professional benchmark is forecast accuracy measured against outcomes, which is what the judgement log and calibration report do.
- **Alerts are configured on conditions, not just price.** The pro tools all support condition alerts: Infront field-to-field and recurring alerts with a log [S19][S21], Koyfin valuation and document alerts [S30], Bloomberg ALRT [S46].
  Nordnet, the retail tool, supports only price-level and % alerts [S6].

**Gaps (said plainly):**
- I found no CFA Institute or Norwegian NFF survey that measures which screens or functions analysts use daily.
- Bloomberg does not publish function-usage rankings. The university guides are curated lists, not usage data.
- The day-in-the-life pieces are anecdotes from US/UK firms, not Oslo.

---

## 4. Take / Drop / Why

The goal decides each line: **(a)** show what changed and what needs a decision, **(b)** log and measure judgements,
**(c)** run on free, delayed, mostly daily data, **(d)** no trading.

| Element | Take / Drop | Seen in | Why (tied to the goal) |
|---|---|---|---|
| **"Needs your decision" list** at the top: kill criterion hit, price crosses target/bull/bear value, signal fired, report date near for a case company, case not reviewed for N days | **Take** (core) | Closest analogues: LSEG Watchlist Pulse [S60], Infront alert log [S19], Koyfin Alerts hub [S30] | (a) Pros consolidate thesis-relevant changes into one view. Here every item must end in a logged judgement, which is (b). |
| **Threshold alerts on conditions** (price vs target/bull/bear, price vs moving average, valuation multiple, signal state), field-to-field style, re-arming | **Take** | Infront [S19][S21], Koyfin [S30], Bloomberg ALRT [S46]; Nordnet only price/% [S6] | (a) Conditions tied to the written case are decision triggers. They are evaluated on daily closes, so (c) holds. |
| **Alert and decision log** (what fired, when, what was decided) | **Take** | Infront alert log [S19]; Koyfin Alerts hub [S30] | (b) An alert with no recorded response cannot be measured. Ties each fired alert to a judgement-log entry. |
| **Private per-stock notes / judgement entry** on the stock page | **Take** | Nordnet "Mine notater" [S11] | (b) Nordnet keeps notes as free text. Here they become structured, timestamped judgements with a probability, horizon and later outcome. |
| **Own estimate vs price**: target, bull/bear, reverse-DCF implied value, distance in % | **Take** | Bloomberg ANR/EE [S46][S47]; Nordnet analyst tab [S1][S3]; Koyfin rating column [S32] | (a)+(b) Pros compare price with consensus. Here the price is compared with his own written case, which needs no licensed data (c). |
| **Calibration / accuracy panel** | **Take** | Bloomberg ANR tracks accuracy of past calls [S47]; accuracy as the analyst benchmark [S56] | (b) Directly the measurement goal. |
| **"What changed since yesterday" brief** (biggest moves in the 64, new signals, new events, cases near triggers) | **Take** | Bloomberg MREP morning report [S53]; analysts' morning news scan [S58][S59] | (a) Matches how analysts start the day. Daily data is enough (c). |
| **Sector heatmap / winners-losers within the 64** | **Take** (compact) | Finansavisen /bors winners/losers and sectors [S36]; Bloomberg IMAP/MOST [S46][S47] | (a) Context for reading single-stock moves (market vs stock-specific). Uses daily closes only (c). |
| **Events calendar** (reports, ex-dividend, AGM) for the universe, flagged for case companies | **Take** | Nordnet corporate events [S3]; Finansavisen calendar/reports [S39][S42]; Bloomberg EVTS [S54]; Infront calendar alerts [S24] | (a) Reports are the main scheduled decision points. The data source must be free and checked. Koyfin suggests "next earnings date" as a watchlist column [S32]. |
| **News headlines with links out** (title, source, time, link; no body) for case companies | **Take** | Nordnet headline list [S3]; Bloomberg CN [S46]; Finansavisen market news [S36] | (a) Explains why something moved. Headlines with links avoid republishing licensed full text (c). |
| **Technical signals with measured odds** (hit rate, sample size, horizon) | **Take** | Investtech research-based signals [S16][S17] | (a)+(b) Investtech also claims research-backed signals, but shows a recommendation, not the odds. The framework already measures odds, so show them. |
| **Watchlist table with decision columns** (distance to target, days to report, last judgement date, signal state) | **Take** | Infront custom columns [S19]; Koyfin 500+ columns [S32] | (a) One sortable table replaces a screener for a 64-stock universe. |
| **Single-stock page layout**: short description (DES-like), chart with own levels drawn on it, case summary, kill-criteria checklist, events, headlines, judgement history | **Take** | Bloomberg DES/GP/CN [S46]; Nordnet page order [S3] | (a)+(b) Keeps the pro "describe, chart, news" order, swapping consensus and broker modules for his own case. |
| Peer / relative valuation table (RV-style) within sector | **Later** | Bloomberg RV [S46][S47] | Useful, but needs fundamentals the free data may lack (c). Revisit once the data source is clear. |
| Seasonality view | **Later** | Infront seasonality matrix [S25]; Investtech score input [S16] | Computable from his own prices, but not a decision trigger. Low priority. |
| Insider trades / short positions / block trades as events | **Later** | Finansavisen short positions, block trades [S36][S40]; Investtech insider input [S16][S17] | Possibly useful event signals, but the free source and licence need checking first (c). Investtech's insider-return evidence is a vendor claim. |
| **Level-2 order book, recent-trades tape** | **Drop** | Nordnet stock page [S3]; Infront watchlist order book [S24] | (d) No trading, and decisions are daily. Level 2 is a priced product for professionals [S9]. |
| **Live streaming quotes / ticker windows** | **Drop** | Nordnet [S9][S10]; Infront tickers [S19]; Finansavisen real-time [S37] | (c) Free data is delayed or daily. Real-time adds noise to daily decisions, and the Citadel analyst deliberately avoids screen-watching [S59]. |
| **Buy/sell buttons, order-entry alerts, trading journals** | **Drop** | Nordnet [S3]; Infront [S19][S20] | (d) No trading. Paper accounts already live elsewhere in oslo-quant. |
| **Social feeds, forums, "customers also viewed", number of owners** | **Drop** | Nordnet Social [S3][S11]; Finansavisen forum [S35] | (a)+(b) Not a decision input that can be logged and measured. Popularity is noise for this goal. |
| **AI news summaries / AI chat** | **Drop** | Nordnet AI summary [S3]; Finansavisen investorchat [S43]; Bloomberg AI summaries [S52] | (b) An unverifiable summary between him and the source weakens the log. Link to the primary item instead. |
| **Opaque composite scores** (black-box 0–100 style) | **Drop** | Investtech Score, weighting undisclosed [S16] | (b) A score you cannot decompose cannot be calibrated. Show components with measured odds instead. |
| **Consensus estimates / broker targets as a data feed** | **Drop** (as a feed) | Nordnet/FactSet [S1][S3]; Bloomberg ANR/EE [S46]; Koyfin [S29]; Infront Estimates [S25] | (c) Licensed (see section 5). At most a manually entered "street view" with source link and date. |
| **Full-text news** | **Drop** | Bloomberg, Infront Direkt [S23], Finansavisen | (c) Licensed content. Headlines and links cover the need. |
| Large screener (thousands of filters) | **Drop** | Koyfin 5,900+ filters [S28]; Finansavisen screener [S38]; Bloomberg EQS [S48] | Universe is 64 stocks. A sortable table is enough. |
| Video/TV, podcasts, webinars, chat/messaging | **Drop** | Finansavisen TV [S36]; Bloomberg IB chat [S51][S52] | (a) Not part of a daily decision page. |
| Portfolio "health score" | **Drop** | Investtech health check [S18] | (b) A vendor score under an equal-weight assumption. If wanted, compute his own risk numbers instead. |

---

## Det som bare finnes bak betalingsmur

What these products have that is paid, licensed or professional-only. The free dashboard should not try to replicate these, or must not redistribute them.

- **Real-time and depth data.**
  - Streaming quotes and order depth are exchange-licensed. Nordnet lists Level 1 and Level 2 as free for private customers but charges professionals 715 NOK for Level 2 [S9].
  - Real-time quotes for US, Canadian and German stocks are a paid Nordnet subscription [S7].
  - Bloomberg charges exchange data fees on top of the seat (third-party estimate, search only) [S55].
- **Consensus estimates and analyst targets/ratings.**
  - Nordnet's analyst data is FactSet-licensed and needs a login [S1][S3].
  - Koyfin's estimate history beyond 1 year is paid [S29].
  - Infront's full estimates need the Equity Analytics subscription [S25] (search only), and Infront sells consensus collection as a service [S23].
  - Bloomberg EE/ANR are inside the terminal [S46][S47].
- **Broker research and transcripts.**
  - Sell-side research inside Bloomberg [S52] and LSEG (research from 1,300 brokers and independent providers) [S60].
  - Koyfin transcripts and filings from the Plus plan [S29].
  - Bloomberg Intelligence research [S47][S48].
- **Fundamentals databases.**
  - Koyfin: 10-year financials paid; data from S&P Capital IQ [S29][S31].
  - Nordnet financials from FactSet [S3].
  - Infront fundamentals on 45,000+ companies [S20].
  - LSEG Worldscope and I/B/E/S [S60].
  - Børsdata via Nordnet: 20 years of history, paid [S2].
- **News full text and newswires.**
  - Infront Direkt real-time Nordic news [S23].
  - Koyfin premium news (MT Newswires) from the Plus plan [S29][S31].
  - Bloomberg news [S46][S52].
  - Finansavisen subscription content [S45].
- **Proprietary analytics and signals.**
  - Investtech's signals, recommendations, Score, Hausse indices and health check (Investor €19 to Professional €79/month; 299 NOK/month via Nordnet) [S14][S2].
  - LSEG StarMine scores and predicted surprise [S60].
  - Bloomberg ANR scoring [S47].
- **Professional terminals as a whole.**
  - Bloomberg: no list price; third-party estimates of about $24k–32k per seat per year [S55] (search only).
  - Infront Professional Terminal: no public price found.
