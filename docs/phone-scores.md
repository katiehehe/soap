# The three scores on the phone (Friday, mobile)

The Friday mobile item asks that the phone "shows the three scores with ranges and
follows the give-up rule." Here is the honest status and how to verify it.

## The scoring lives in the shared engine, not the UI

All three signals are computed by the **Rust engine** that ships to both desktop
and phone (`rslib/src/speedrun/`), behind one give-up rule:

- `compute_readiness` returns `oneof { NoScore, ReadinessScore }` — a bare number
  literally cannot be emitted below threshold, on **either** platform.
- `get_mastery_state` (the measured mastery signal) and the FSRS memory signal are
  the same code on both.

The AnkiDroid build is compiled from **our** engine, so these RPCs are present in
the on-device binary. Proof (from `docs/demo-script.md`):

```bash
APK=~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
unzip -p "$APK" lib/arm64-v8a/librsdroid.so | strings | grep -iE "ComputeReadiness|Mastery|speedrun"
# -> anki/rslib/src/speedrun/service.rs, ComputeReadinessRequest, MasteryRequest, ...
```

Because desktop and phone share one collection via sync, once the phone syncs the
demo-persona collection (`make seed-persona`, then sync), `compute_readiness` on
the phone returns the **same** honesty-bundled band the desktop shows — same
engine, same inputs, same number.

## What is built vs. remaining

- **Built:** the give-up rule, the three separate signals, and the honesty bundle
  are enforced in the shared on-device engine; the desktop renders them
  (`ts/routes/readiness-dashboard`). Sync carries the collection both ways
  (`make sync-test`).
- **Remaining (honest):** a **native AnkiDroid screen** that calls these RPCs and
  renders the three numbers + ranges. That is Kotlin/Android UI work on top of the
  already-present engine; it does not change the scoring or the give-up rule. The
  desktop dashboard is the reference layout to mirror.

We do not claim a phone score screen that is not built. The scoring itself is
real, shared, and honest on the phone today; the mobile presentation of it is the
remaining surface.
