# Latency evidence (speed & reliability targets, brief §10)

One command, reported as **p50 / p95 / worst** per action, not a single
cherry-picked number (§10 / challenge 7h). Reproduce with:

```bash
make bench          # builds a 50,000-card collection and times each action
```

## Latest run (50,000-card collection)

| Action                                   |      p50 |      p95 |    worst |   n |
| :--------------------------------------- | -------: | -------: | -------: | --: |
| Build queue (next card after grading)    |  0.06 ms |  0.06 ms |  7.49 ms | 200 |
| Answer card (grade, backend)             |  0.19 ms |  0.30 ms |  4.06 ms | 200 |
| Mastery query (powers the dashboard)     |  0.17 ms |  0.34 ms |  0.71 ms | 200 |
| Mastery-ordered new cards                | 155.4 ms | 197.2 ms | 326.1 ms | 200 |
| Readiness (give-up rule + memory recall) |  4.41 ms |  5.10 ms |  6.74 ms | 200 |

**Peak process memory (RSS): ~200-350 MB** on the 50,000-card collection
(reported by `make bench`; `resource.getrusage` high-water mark over the whole
run). It varies with concurrent machine load (~198 MB on an idle laptop, ~348 MB
observed while other heavy builds ran alongside), but stays well under the stated
1 GB desktop ceiling either way. Deck generated in ~9-11 s (one-time setup, not
counted in the per-action timings).

**Normal-session sync: 0.04 s** to reconcile a 10+10 two-way session over the
loopback sync server (`make sync-test`; a real network adds its round-trip on
top). This measures the sync protocol + DB overhead, not network latency.

## Against the §10 targets

| Target (§10)              | Threshold               | Measured                                      | Verdict                 |
| :------------------------ | :---------------------- | :-------------------------------------------- | :---------------------- |
| Button press acknowledged | p95 < 50 ms             | answer card **0.30 ms** (backend)             | PASS (UI render on top) |
| Next card after grading   | p95 < 100 ms            | **0.06 ms**                                   | PASS (huge margin)      |
| Dashboard first load      | p95 < 1 s               | mastery **0.34 ms** + readiness **5.10 ms**   | PASS                    |
| Dashboard refresh         | p95 < 500 ms, no freeze | same as above                                 | PASS                    |
| Sync of a normal session  | < 5 s                   | **0.04 s** over loopback (RTT on top)         | PASS (loopback)         |
| Memory on 50k cards       | under a stated limit    | **~200-350 MB** vs stated **1 GB** ceiling    | PASS (~3-5× headroom)   |

Notes:

- The **mastery query** scans only _reviewed_ cards (it drives off an aggregated
  revlog), so it scales with review count, not deck size, so p95 ~0.17 ms on
  50k. The memory-recall band added for the dashboard reuses this same scan (it
  collects per-card retrievability in the loop), so it does not add a pass.
- **Mastery-ordered new cards** still scans all new cards and sorts by a
  precomputed rank; p95 ~197 ms on 50k. It backs the study-map ordering, not the
  per-keystroke path, so it is comfortably under the 1 s dashboard-load budget.
- **Button press acknowledged** is measured as the backend `answerCard` time
  (p95 ~0.30 ms), the work a grade triggers in the engine. The end-to-end UI
  acknowledgement (JS → backend → next-card render) sits on top of this and is a
  desktop/phone-device capture, not a `make bench` number.
- **Memory** is the peak RSS of the desktop process (Rust engine loaded
  in-process + 50k cards): ~200-350 MB depending on concurrent machine load,
  against a stated **1 GB desktop ceiling**. The **mid-range phone** ceiling
  still needs an on-device capture.
- **Sync < 5 s** is measured over the loopback sync server (~0.04 s); it captures
  protocol + DB overhead, so a real connection adds only its round-trip.
- Still needing device capture (not `make bench`): end-to-end button-press ack on
  the **phone**, app **cold start** (< 5 s desktop / < 4 s phone), and the phone
  **memory ceiling**. The crash target is covered separately: `make crash-test`
  (20× mid-review SIGKILL, SQLite `integrity_check` clean every time).

Machine: Apple Silicon dev laptop. Numbers vary by machine; the command is what
makes them reproducible.
