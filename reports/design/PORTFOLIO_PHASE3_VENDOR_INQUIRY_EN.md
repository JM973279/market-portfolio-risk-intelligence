# Vendor licensing inquiry — draft only, not sent

Prepared 2026-11-04. No signup, purchase, quotation request submission, or outbound message has been made.

**Subject:** Written licensing scope and EOD pilot quote for a public portfolio risk analytics website

Hello Licensing Team,

We are evaluating data sources for M/PRI, a small portfolio risk analytics website. Please confirm the applicable license and provide an itemized quote. This is an inquiry draft; we are not placing an order or accepting any subscription.

The pilot would cover approximately 80 US-listed securities, including ordinary shares and nonleveraged ETFs. We need at least 757 valid daily prices per instrument, preferably the full history since 2018, raw prices, split- and dividend-adjusted prices, and dated corporate actions. Each user portfolio contains at most 10 assets. We would retrieve data in an offline end-of-day batch rather than calling your API for each user request.

Our outputs include volatility, covariance/correlation, risk contributions, separate single-factor betas and significance diagnostics, scenario losses, and comparisons between portfolio allocations. The factors are SPY daily adjusted returns, changes in the US ten-year Treasury yield (basis points), and changes in the actual Cboe VIX index (index points). We do not want a VIX futures series or a volatility ETF proxy.

Please answer these permissions separately:

1. May we archive raw observations and corporate actions privately, retain historical vintages for reproducibility, and record SHA256 receipts? What are the retention, cache, backup, and post-termination deletion requirements?
2. May we compute and store the listed portfolio-level and asset-level derived measures, including after a subscription ends? Are there non-reconstructibility or derivative-product restrictions?
3. May an unauthenticated public website display these results? Does the same license permit the website's JSON API to return them to browsers? Please distinguish free-to-view and paid-user scenarios.
4. May we host private immutable runtime files containing daily returns, factor changes, betas, and scenario parameters on a third-party cloud host? Do not assume we will publish these files: please separately quote public GitHub/download redistribution if permitted at all.
5. What attribution, source links, exchange approvals, user counts, geographic limits, reporting, security, and non-display classifications apply?
6. Are SPY and the actual Cboe VIX historical index included? If VIX needs an additional agreement, which party grants the derived-output rights and what are the separate charges?
7. Does your adjusted daily price include ordinary/special cash dividends, stock dividends, splits, reverse splits, spin-offs, mergers, and ETF distributions? Please document exclusions and whether historic observations are revised retroactively.
8. How do you identify missing observations, market holidays, suspended/delisted instruments, renamed securities, share classes, and corrections? Please provide the symbol/identifier mapping and revision policy.
9. What are the exact per-endpoint request/credit weights, rate and daily limits, history window, bulk options, retry rules, and possible overage fees for this 80-security EOD workflow?
10. Please identify the relevant contract clauses and quote monthly/annual minimums, exchange/VIX fees, storage or server-download add-ons, setup fees, taxes, and any permitted small-pilot discount. We are not requesting real-time tick feeds.

We will not enable new securities publicly until both the data and these permissions are validated. A sales page or an API response alone is insufficient for our approval record; please provide written scope or the applicable agreement/addendum.

Thank you,
M/PRI project team

## Vendor-specific additions

- **Twelve Data:** Please distinguish the Venture tier starting at USD 149 from higher credit variants and Enterprise. Confirm whether non-realtime portfolio-derived JSON results qualify as permitted derived display; specify long-term archives and EOD external-distribution add-ons separately.
- **Alpha Vantage:** Please quote the commercial/public-use agreement separately from the USD 49.99 personal premium plan. Confirm Daily Adjusted full-history and actual VIX rights.
- **EODHD:** Please distinguish GBP 399 Internal, its GBP 200 corporate-server download option, GBP 2499 Enterprise, and a custom public-derived-results agreement. Explain indicative/OTC source descriptions versus the official EOD close used for risk analysis.
- **Massive:** Please distinguish personal from Stocks Business and any index license. Confirm the required dividend-adjustment implementation and rights to use action adjustment factors for public portfolio analytics.
- **Cboe or an authorized VIX distributor:** Please quote historical daily VIX input rights for public beta/scenario analytics only, separately from real-time index display, benchmark creation, futures data, or raw-history redistribution.
