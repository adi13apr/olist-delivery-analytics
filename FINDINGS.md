# Findings

Five observations from the full Olist dataset, for an operations team. Every
number comes from an export in [`data/exports/`](data/exports/), produced by
`scripts/run_all.py`, and links to the query that produced it. Definitions and
thresholds are in the [README](README.md#analysis-phase-2).

**Read with this caveat: right-censoring.** Delivery metrics count only
delivered orders, so an order still in transit when the data was extracted is
missing, and those are the slowest ones. Query
[11_delivery_tail_by_month.sql](sql/analysis/11_delivery_tail_by_month.sql)
shows how far this can go:

- In August 2018, the last trend month, 70 of 6,512 orders (1.07%) were still
  open (not delivered, canceled or unavailable). Censored orders can only be
  among these.
- The open share in August is no higher than earlier (January 2018: 1.62%).
- Every August order had at least 47 days to arrive before the last delivery
  in the data.

So censoring can hide at most 1.07% of a late-2018 month's orders, all in the
slow tail. It can pull down means and the 99th percentile, but can barely move
medians or the 90th percentile. Late-2018 numbers are marked below.

## 1. A late delivery is the clearest sign of an unhappy customer

Source: [04_reviews_late_vs_on_time.sql](sql/analysis/04_reviews_late_vs_on_time.sql)

| | Late | On time |
|---|---|---|
| Eligible orders | 6,534 | 89,936 |
| Reviewed (latest review) | 6,381 | 89,443 |
| Average review score | 2.27 | 4.29 |
| 1-2 star reviews | 3,983 (62.42%) | 8,289 (9.27%) |

153 late and 493 on-time orders have no review. They are counted, not scored.

**So what:** treat every late delivery as an order defect. On-time rate is a
customer-satisfaction metric, not only a logistics one.

## 2. Carrier transit, not seller dispatch, is where late orders lose time

Source: [10_late_root_cause.sql](sql/analysis/10_late_root_cause.sql)

Average days per stage, over the 95,082 eligible orders with timestamps in the
right order. 1,388 orders are excluded, mostly handed to the carrier before
payment approval.

| Stage | Late | On time | Gap |
|---|---|---|---|
| Approval (purchase to approved) | 0.50 | 0.39 | 0.11 |
| Seller dispatch (approved to carrier) | 5.57 | 2.65 | 2.92 |
| Carrier transit (carrier to customer) | 27.88 | 8.00 | 19.87 |
| Total delivery days | 33.95 | 11.05 | 22.90 |

The pattern holds in each of the five states that query
[02](sql/analysis/02_wow_delivery_by_state.sql) flagged for the largest
week-over-week jumps (BA, DF, PE, RJ, SC). There, the transit gap is 14.37 to
23.57 days and the dispatch gap is 1.43 to 3.94 days. These figures include
2018 orders, so see the censoring caveat above.

**So what:** most of the delay on late orders comes after the parcel leaves the
seller, so carrier performance (lanes, SLAs, carrier choice per region) is the
main lever. Seller dispatch is still about twice as slow on late orders, which
makes it the secondary lever.

## 3. Black Friday 2017 multiplied demand and stretched delivery times

Sources: [09_black_friday.sql](sql/analysis/09_black_friday.sql),
[significance.py](scripts/significance.py) (`09b_black_friday_significance.csv`)

Event: 24-27 Nov 2017 (4 days). Baseline: 27 Oct-23 Nov 2017 (28 days).

| Metric | Baseline | Event | Change |
|---|---|---|---|
| Orders per day | 170.25 | 617.25 | +262.56% |
| GMV per day | 24,153.80 | 76,619.29 | +217.21% |
| AOV | 145.19 | 125.04 | -13.88% |
| Median delivery days | 11.41 | 14.84 | +3.43 days |
| Mean delivery days | 13.25 | 17.43 | +4.17 days |
| Late rate | 7.66% | 18.29% | +10.63 points |

Delivery-days test, two-sided Mann-Whitney U, on 2,411 event orders vs 4,570
baseline orders:

- **Effect size:** a random event order took longer than a random baseline
  order with probability 0.6153 (0.5 would mean no difference). The
  rank-biserial correlation is 0.2306.
- **Medians:** 14.84 days vs 11.41 days.
- **p-value:** 1.09E-56, so the difference is very unlikely to be chance alone.

**What this cannot show:** that the promotion caused the slowdown. This is a
before/after comparison with no control group. Holiday-season carrier load,
the run-up days in the baseline, and anything else happening in late November
are mixed into it.

**So what:** during the peak, daily volume ran at more than three times the
baseline and the late rate more than doubled. Book carrier capacity before the
event, and widen promised delivery dates for peak-week orders.

## 4. The delivery promise is broken most often in the Northeast; RJ has the most late orders after SP

Source: [03a_sla_breach_by_customer_state.sql](sql/analysis/03a_sla_breach_by_customer_state.sql)

The five highest late rates are all Northeast states:

| Rank | Customer state | Late orders | Late rate |
|---|---|---|---|
| 1 | AL | 85 of 397 | 21.41% |
| 2 | MA | 125 of 717 | 17.43% |
| 3 | SE | 51 of 335 | 15.22% |
| 4 | PI | 66 of 476 | 13.87% |
| 5 | CE | 176 of 1,279 | 13.76% |
| 8 | RJ | 1,495 of 12,350 | 12.11% |
| 22 | SP | 1,820 of 40,494 | 4.49% |

The highest North state is RR, 6th at 12.20%, but that is 5 of 41 orders, just
above the 30-order threshold.

All 27 states pass the threshold; AM is lowest at 2.76%. These figures include
late-2018 orders, so see the censoring caveat above.

**So what:** for Northeast destinations, starting with AL and MA, the
estimated date is unreliable, so recalibrate promised dates there. RJ is where
lateness affects the most customers outside SP, so it is the first state for a
carrier review.

## 5. On-time rate fell well below normal in Nov 2017 and Feb-Mar 2018

Source: [01_monthly_kpis.sql](sql/analysis/01_monthly_kpis.sql)

On-time rate by purchase month, trend window 2017-01 to 2018-08:

| Month | Eligible orders | On-time rate | Avg delivery days |
|---|---|---|---|
| 2017-11 | 7,288 | 87.60% | 15.16 |
| 2018-02 | 6,555 | 85.87% | 16.95 |
| 2018-03 | 7,003 | 81.04% | 16.30 |
| Other 17 months | | 92.54% to 98.84% | |

The data does not show the cause. November includes Black Friday (finding 3),
but nothing in this dataset explains February and March 2018.

**Late 2018 and censoring:** average delivery days fell to 9.24 in June, 8.96
in July and 7.73 in August 2018 (query 01). Query
[11](sql/analysis/11_delivery_tail_by_month.sql) shows the drop affects the
typical order, not just the tail:

| Measure | Jan 2018 | Aug 2018 |
|---|---|---|
| Median delivery days | 11.83 | 7.01 |
| 90th percentile | 25.46 | 13.07 |
| 99th percentile | 49.48 | 21.33 |

Both the median and the 90th percentile are well inside the 47 days every
August order had to arrive. Censoring can hide at most August's 70 open orders
(1.07%), so it cannot explain the drop in the median and 90th percentile. It
can still pull down the August mean and its 99th percentile, so don't quote
those as final.

**So what:** investigate Feb-Mar 2018 with the carriers before treating it as
noise. Mid-2018 deliveries really were faster for the typical order, so find
out what changed operationally. Confirm the slowest-order tail with a
refreshed extract before reporting it.
