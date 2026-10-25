Strict (Opus): Foundation SOUND. 3 Important, 3 Minor.
S1 [I] render frontier undefined; frozen = rows overlapping any segment <= max(listed_bound, highest local seg file); re-plan starts exactly at replaced row's start_frame; mutation test. (render skips existing seg files; publish stoppage leaves rendered-unpublished files)
S2 [I] interstitial rows hit package re-validation by slug -> "no longer eligible" -> re-plan places same clip -> infinite loop w/ watchdog fed. Fix: interstitials re-validate vs folder; failing clip excluded from interstitial pool for the call; hard cap on re-plans per render_step.
S3 [I] gap rule unenforced; estimate->exact swap may leave silence. Pin start = prev.end + gap for non-run_start rows incl interstitials; assert on write only.
S4 [m] invalid live clock.toml stops planning -> silence after lead. Keep last good clock (or open block) + alert.
S5 [m] all pools empty (exclude_profiles) -> PlanError. Bend exclude_profiles last; PlanError only when nothing eligible.
S6 [m] rollback to phase-1 code can't read new plan rows. Document.
Premises: emcee scan skips no-manifest dirs (confirmed); planned_frames model for single-clip pieces untested; commit-block within WatchdogSec (pinged per analysis).
