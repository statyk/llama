# Task 1 handback: DONE
Implemented antenna/src/bucket.ts, period.ts, test/support.ts, bucket.test.ts, period.test.ts verbatim from brief; clock.ts now re-exports bucket types; clock.test.ts uses test/support.ts (local MemoryBucket/fakeTime removed, unused BucketLike import dropped).
RED: npx vitest run test/bucket.test.ts test/period.test.ts -> 2 files failed, "Cannot find module '../src/bucket'" / '../src/period'.
GREEN: cd antenna && npm test -> 5 files, 51 tests passed (was 41 in 3 files); npx tsc --noEmit -> clean (exit 0).
Commit: f13191c feat(antenna): storage seam with etags and conditional puts; billing period; shared test support
Concerns: none. Deviation: removed unused 'type BucketLike' from clock.test.ts import (brief said the import line becomes that form).
