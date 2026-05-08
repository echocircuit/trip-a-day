# Live Run Investigation — 2026-05-07

Diagnostic investigation of three reported issues based on `trip_of_the_day.db` and source code analysis. No code was changed.

---

## Environment snapshot

| Setting | Value |
|---|---|
| Home airport | HSV |
| `daily_batch_size` | 5 |
| `destination_selection_strategy` | `least_recently_queried` |
| `max_live_calls_per_run` | 10 |
| `advance_window_min_days` | 7 |
| `advance_window_max_days` | 365 |
| `trip_length_nights` | 7 |
| `trip_length_flex_nights` | 2 |
| `direct_flights_only` | false |
| `search_radius_miles` | 120 |
| `flight_data_mode` | live |
| Run schedule | Daily via scheduler |

---

## Section 1: Travel Window Investigation

### What windows exist

```
ID  Name               earliest_departure  latest_return  buffer  enabled
2   Spring Break 2027  2027-03-15          2027-03-19     2/2     YES
3   Fall Break 2026    2026-10-05          2026-10-09     2/2     YES
```

Both are enabled and have not been auto-expired (effective ends Oct 11, 2026 and Mar 21, 2027 are in the future).

### How the pipeline decides to use windows

`main.py` (line 636–650) queries all enabled windows and auto-disables any where `effective_end < run_date`. Remaining windows go into `active_windows`; `use_window_mode = bool(active_windows)`. Both windows pass this check today (May 7, 2026).

For each window, `window_data_list` is computed using:
- `min_days_tw = max(0, (eff_start - run_date).days)`
- `max_days_tw = (eff_end - timedelta(days=trip_nights) - run_date).days`
- If `max_days_tw < min_days_tw`, the window is skipped as too narrow for a full trip.

### The departure window is only 2 days wide — but does pass the check

For **Fall Break 2026** as of today:
- `eff_start` = Oct 5 − 2 = **Oct 3, 2026** → `min_days_tw` = 149
- `eff_end` = Oct 9 + 2 = **Oct 11, 2026** → latest departure = Oct 4 → `max_days_tw` = 150
- 150 ≥ 149 → **not skipped; added to `window_data_list`**

For **Spring Break 2027** as of today:
- `eff_start` = Mar 13, 2027 → `min_days_tw` = 310
- Latest departure = Mar 14, 2027 → `max_days_tw` = 311
- 311 ≥ 310 → **not skipped; added to `window_data_list`**

So window mode IS being invoked. The `_probe_dest_window` function is submitted for all 5 batch destinations.

### The window probes only 2 departure dates — and fli returns nothing for them

`_probe_dates(today, min_days=149, max_days=150, n=3)` produces only **[Oct 3, Oct 4]** (Python's banker's rounding collapses `round(0.5)` to 0, creating a duplicate at offset 149 which is then deduped). The same logic gives **[Mar 13, Mar 14]** for Spring Break.

Each destination gets exactly 2 probes per window (4 total across both windows). With 5 destinations × 4 probes, window mode attempts up to 20 live fli calls — double the 10-call budget.

**fli returns no results for these specific dates.** The `price_cache` table has zero live entries for Oct 2026 or Mar 2027 departure dates. All entries for those date ranges are `is_mock=1` from the May 2 mock-mode runs. The same South American destinations (GYE, GRU, MVD, UIO, FLN, GIG, SSA, REC) that successfully return prices in normal mode at Nov 9 (+186 days) return nothing at Oct 3-4 (+149-150 days). This is likely a Google Flights data gap for those specific routes at those specific dates (possibly fli hit a rate limit, the routes don't have published fares that far out for that narrow window, or the very tight date range reduces hit probability).

### Budget consumed by window mode leaves little for normal fallback

`live_calls_made` accumulates across **both** the window pass and the normal fallback pass — it is never reset. The `pass1_stats` reset on fallback resets only the diagnostic counters. Evidence from `run_log`:

| Run | Date | `api_calls_flights` | `pass1_stats.live_calls` | Δ (window-mode cost) |
|---|---|---|---|---|
| 47 | May 3 | 13 | 9 | ~4 consumed by window mode |
| 49 | May 5 | 13 | 6 | ~7 consumed by window mode |
| 51 | May 7 | 18 | 9 | ~9 consumed by window mode |

Window mode alone is consuming roughly half the available budget on most days. With `max_live_calls_per_run=10` and window mode spending 4–10 of those calls before the fallback even starts, normal mode frequently gets 0–4 remaining slots.

### Result: travel window name never appears in emails

`winning_window_name` is set only when window mode produces a valid price **and** `window_fallback_used=False`. Since window mode never finds a price:
1. Fallback fires, sets `window_fallback_used = True`, `use_window_mode = False`
2. Normal mode finds some prices
3. `winning_window_name` = `None`; `travel_window_name` written to `run_log` as empty string
4. Email shows no window context

**Root cause:** The window date ranges (Fall Break Oct 5–9, Spring Break Mar 15–19) produce only a 2-departure-date search window after buffer and trip-length arithmetic. fli returns no flights from HSV for those 2 specific dates for the current batch of South American destinations. Window mode exhausts budget with zero results, triggering fallback.

---

## Section 2: Duplicate Destination Investigation

### What the staleness logic actually does

`selector.py: _least_recently_queried` sorts the eligible pool by `last_queried_at ASC` (NULLs first) and returns the top `batch_size=5`. This is correct in principle.

**Critical gap: `last_queried_at` is only updated when a destination produces a valid price.**

From `main.py` line 854–881:
```python
if cost is not None and best_date is not None:
    dest_obj.last_queried_at = now_utc
    dest_obj.last_known_price_usd = cost.total
    dest_obj.query_count = (dest_obj.query_count or 0) + 1
```

If a destination receives API calls but fli returns no flights (`no_price`), the destination's `last_queried_at` is **never updated**. It stays at its old timestamp, stays at the top of the LRQ queue, and gets selected again the next day.

### What the DB shows

The "most stale" eligible destinations (as of May 7) include many Western European and other international cities:

```
EZE  Buenos Aires     last_queried: 2026-04-24   query_count: 1
SCL  Santiago         last_queried: 2026-04-24   query_count: 1
DUB  Dublin           last_queried: 2026-04-25   query_count: 1
LHR  London           last_queried: 2026-04-26   query_count: 1
CDG  Paris            last_queried: 2026-04-26   query_count: 1
FRA  Frankfurt        last_queried: 2026-04-26   query_count: 1
```

These are at the head of the LRQ queue and ARE being selected in each 5-destination batch. But they consistently return `no_price` from fli (HSV → European routes have complicated connections; fli may not find results or routes are in a price gap). Because their `last_queried_at` never updates, they re-occupy the same 2–3 batch slots every day.

The destinations that DO produce prices — South American cities with Atlanta/Miami connections (GYE, GRU, MVD, UIO, FLN, GIG, SSA, REC) — return results, get their timestamps updated, and rotate back through quickly. With only 2–3 "live" slots in a 5-destination batch (the others locked up by the no-price repeaters), the same South American cities win every few days.

### Compounding factor: window mode budget consumption

With window mode using 4–10 of the 10 live-call budget before normal mode even starts, normal mode sometimes has ≤2 calls left. That means 2–3 of the 5 batch destinations can't even get a live probe attempt. Those return `no_price` for yet another reason, further tightening the effective winner pool.

### Observable pattern confirmed

Across the last 7 runs (May 2–7):
- UIO won twice (May 2, May 5)
- GYE appeared in 3 runs (May 2, May 4 as stale, May 7 as winner)
- GRU appeared in 3 runs (May 2, May 4 as stale, May 7)
- GIG, SSA appeared in consecutive runs (May 3)

**Root cause:** Destinations returning `no_price` are never updated and monopolize LRQ slots indefinitely. The effective "working" pool from HSV is narrow (South American cities with reliable fli results), so those cities cycle back quickly.

---

## Section 3: Price Variance Investigation

### Legitimate variance: probe-date spread

Normal mode (`advance_window_min=7`, `advance_window_max=365`) probes 3 evenly-spaced dates:
- Probe 1: +7 days → **May 14, 2026** (near-term)
- Probe 2: +186 days → **Nov 9, 2026** (mid-term)
- Probe 3: +365 days → **May 7, 2027** (often returns no result)

Near-term international fares from HSV are expensive; mid-term are cheaper. Example from May 7 cache:

```
GYE: May 14 → $12,869/trip    vs    Nov 9 → $3,088/trip   (4.2× difference)
MVD: May 14 →  $5,962/trip    vs    Nov 9 → $4,782/trip   (1.25× difference)
FLN: May 12 → $12,494/trip    vs    Nov 7 → $6,362/trip   (2.0× difference)
```

This is real market variance, not a bug. The cheapest probe wins Pass 1, so the winner is usually the mid-term date. The wide spread of `advance_window_max=365` means near-term expensive fares show up as "also ran" candidates.

### Trip-length flex contributes additional variance

`trip_length_flex_nights=2` generates night variants [5, 6, 7, 8, 9] for Pass 2. A 5-night trip has lower hotel and food costs than a 9-night trip to the same destination. Observed: winners range from 6 to 7 nights across days (e.g., trip 183 May 6 = 6 nights, trip 184 May 7 = 7 nights).

### Genuine bug: mock prices appear in live-mode stale fallback

**May 4 run (run 48) shows stale_cache_used=1, all 5 trip candidates have `stale_cache=True`:**

| Trip | Destination | Flight cost | Departure |
|---|---|---|---|
| 176 | UIO | **$360** | Jun 5 |
| 177 | FLN | **$360** | Jun 5 |
| 178 | REC | **$360** | Jun 5 |
| 179 | GYE | **$360** | Jun 5 |
| 180 | GRU | **$987** | Jun 5 |

All are mock prices. They originate from `price_cache` entries created on **April 24, 2026** during early mock-mode development, with `is_mock=1` and `departure_date=2026-06-05`. They have long since passed their 2-day TTL (expired April 26) but remain future-dated (June 5 > May 4).

`_stale_cache_fallback()` (main.py line 169) queries:
```python
PriceCache.departure_date >= today
```
There is **no `is_mock` filter**. In a live run, mock-priced cache entries are returned and used to build TripCandidates with fake $360 flight costs — off by a factor of 10× from reality ($3,000+ actual). The resulting email shows UIO as a $4,945 winner when actual prices are closer to $8,000.

Additionally: when window mode uses up the budget and normal mode gets 0 live calls, stale_cache_fallback fires. This will pick up any future-dated entry regardless of whether it's from mock or live mode.

**Root cause:** `_stale_cache_fallback` does not filter `PriceCache.is_mock == False` when the current run is in live mode. Mock entries from development runs contaminate live-mode stale fallbacks.

---

## Section 4: Nearby Airport Investigation

### Configuration

`search_radius_miles=120`, `home_airport=HSV` (Huntsville, AL).

`get_nearby_airports()` in `fetcher.py` haversine-scans the `Destination` table (enabled=True, but **no excluded filter**) for airports within 120 miles of HSV.

### BNA and BHM are found and included

Both are in the Destinations table and within range:

| IATA | City | Lat/Lon | Distance to HSV |
|---|---|---|---|
| BHM | Birmingham | 33.5629, -86.7535 | ~73 miles |
| BNA | Nashville | 36.1263, -86.6774 | ~103 miles |

`departure_iatas = ['HSV', 'BHM', 'BNA']` (exact order depends on DB scan order). All three are looped over in the Pass 1 / Pass 2 search.

### BNA and BHM make no effective API calls

The `price_cache` table has **zero entries with `origin_iata` other than 'HSV'**. BHM and BNA are looped over, but by the time their iterations run, `live_calls_made` is equal to or near `max_live_calls=10` (consumed by HSV's window mode + start of HSV normal mode). `live_budget = max(0, 10 - live_calls_made) = 0`, so all 5 destinations for BHM and BNA are skipped with `budget_exhausted`.

### Multi-airport contributes overhead but not results

With 3 departure airports, the pipeline loops through `window_data_list` computation, `eligible_batch` filtering, and thread pool setup 3× per `_search_pass`. This adds latency without adding value. The `destinations_evaluated=5` in `run_log` reflects only the batch size, not 3×5=15, so this overhead is invisible in logs.

### Does multi-airport contribute to any of the above issues?

Indirectly yes. The window mode for HSV runs first in Pass 0, consuming budget. If HSV-window consumed 9 calls, BHM and BNA get 1 or 0 calls for window mode AND normal mode. The transport cost computation (`transport_usd` for BHM/BNA) is correct (haversine × 2 × 0.70 $/mile), but since no flight prices are found, transport_usd is never actually used in a winning TripCandidate from those airports.

---

## Section 5: Root Causes and Recommended Fixes

### Issue 1: Travel windows never match

**Confirmed root cause:** Two compounding problems:
1. **2-day departure window:** Fall Break (Oct 5–9) and Spring Break (Mar 15–19) are each only 5 days wide. After subtracting a 7-night trip from the buffered range, the departure window collapses to exactly 2 dates. fli finds no results for either of those 2 dates on the current batch of South American routes.
2. **Budget competition:** Window mode makes real API calls (4–10 per run) that consume `live_calls_made` before the fallback even starts. Normal mode then runs with a depleted budget.

**Proposed fixes (in priority order):**

A. **Widen the travel windows.** The simplest fix: change `earliest_departure`/`latest_return` to span the intended break period more generously. Example: Fall Break Oct 1–Nov 1 gives a ~25-day departure window, dramatically increasing the probability of finding a flight. The buffer is not a substitute for a wide window.

B. **Separate window-mode budget from normal-mode budget.** Currently `live_calls_made` is shared. Window mode should have its own counter and budget cap (e.g., `window_live_cap = max_live_calls // 2`). If window mode exceeds its cap without finding prices, the normal fallback gets the full remaining budget.

C. **Update `last_queried_at` for no-price attempts too** (see Issue 2 fix — this also reduces the "same batch keeps failing" problem that contributes to window pressure).

### Issue 2: Duplicate destinations

**Confirmed root cause:** `last_queried_at` is only updated when a destination produces a valid price. Destinations that consistently return `no_price` from fli (many European/Asian routes from HSV) permanently occupy the front of the LRQ queue, re-selected every day.

**Proposed fix:**

Update `last_queried_at` for **all destinations that receive at least one live probe attempt**, regardless of whether a price was found. A `no_price` result is still a query — the destination was checked and found empty. Tracking it prevents perpetual re-selection.

One approach: add a separate `last_attempted_at` column (or reuse `last_queried_at`) that is updated whenever a live call is made to that destination, independently of price validity. The LRQ sort key would use `last_attempted_at`.

A simpler interim fix: add a preference `no_price_cooldown_days` (e.g., 3) and in the LRQ sort, rank no-price destinations by `last_queried_at + cooldown`, effectively treating a failed attempt as a 3-day deferral.

### Issue 3: Wildly different prices

**Root cause A (expected):** Different probe dates produce genuinely different prices. Near-term (+7 days) fares are 2–4× more expensive than mid-term (+186 days) fares for international routes from HSV. This is correct behavior — the wide `advance_window_max_days=365` exposes this variance.

**Root cause B (bug):** `_stale_cache_fallback()` does not filter `PriceCache.is_mock == False`. Mock prices ($360 flat rates) from early development runs are still in the `price_cache` table (future-dated, never deleted), and get used in live-mode runs when all live calls fail.

**Proposed fix for B (one-line):**

In `_stale_cache_fallback()` (main.py ~line 194), add `PriceCache.is_mock.is_(False)` to the filter:

```python
cached = (
    session.query(PriceCache)
    .filter(
        PriceCache.origin_iata == dep_iata,
        PriceCache.destination_iata == iata,
        PriceCache.departure_date >= today,
        PriceCache.is_mock.is_(False),   # ← add this
    )
    .order_by(PriceCache.queried_at.desc())
    .first()
)
```

Additionally: the old mock `price_cache` rows (Apr 24 batch, all `is_mock=1`) can be deleted from the DB directly:
```sql
DELETE FROM price_cache WHERE is_mock = 1;
```
This is safe — mock prices are regenerated on demand from `mock_flights.json` when running in mock mode.

### Issue 4: Nearby airports (BNA/BHM)

**Finding:** Working as designed but consuming no effective budget. BNA and BHM are correctly identified and looped over, but `live_calls_made` is exhausted by HSV before their iterations run. No data from BNA or BHM has ever been cached.

**Not a bug**, but two things are worth considering:

A. With `max_live_calls_per_run=10` and 3 departure airports, each airport effectively gets ~3 calls. Raising `max_live_calls_per_run` to 25–30 would allow all 3 airports to actually probe destinations.

B. **`get_nearby_airports` does not filter `excluded=False`** (fetcher.py line 863). If an airport is excluded as a destination, it could still appear as a departure airport. Minor correctness gap — probably not causing issues in practice today but worth fixing.

---

## Priority order for fixes

| Priority | Issue | Fix | Effort |
|---|---|---|---|
| 1 | Issue 3B | Filter `is_mock=False` in `_stale_cache_fallback` | 1 line |
| 1 | Issue 3B | Delete stale mock price_cache rows | 1 SQL command |
| 2 | Issue 2 | Update `last_queried_at` for no-price attempts | ~10 lines in main.py |
| 3 | Issue 1A | Widen travel window date ranges in UI | Config change (no code) |
| 3 | Issue 1B | Separate window-mode live call budget | ~15 lines in main.py |
| 4 | Issue 4A | Raise `max_live_calls_per_run` to 25–30 | Config change (no code) |
| 4 | Issue 4B | Add `excluded=False` filter in `get_nearby_airports` | 1 line |
