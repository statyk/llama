# task2-fix1 report
Status: DONE. Commit f5256ac.
Diff: tar line now `--exclude="./.venv*" --exclude=./.superpowers --exclude=./.git --exclude=./.claude` (double quotes, since the script body is single-quoted; single quotes would have broken out of it and let the host shell glob).
Debian run: ffmpeg 5.1.9-0+deb12u1, Python 3.11.2, 44 passed.
Measured: extra_frames() = 1 on ffmpeg 5.1.9 and on local ffmpeg 8.1.1; ENCODER_PRIMING_SAMPLES = 1024 in both.
