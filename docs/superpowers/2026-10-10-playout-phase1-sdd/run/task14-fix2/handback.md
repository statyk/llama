Status: DONE. Commit: 675cb6c test(transmitter): pin that the real publish_batch reports a held horizon (test-only; publish.py untouched, no defect found).
Added test_a_batch_stopping_below_the_high_water_mark_reports_the_horizon_held in test_publish.py: crash after horizon PUT (high_water 109), delete local 105.aac, real publish_batch -> held True, "horizon held" in error, no horizon/uploaded, only the crashed batch's horizon PUT, local last/high_water not advanced.
Mutant (publish.py report.held = True -> pass) in scratch copy, PYTHONPATH sentinel-proven, isolated pycache. Predicted red: that new test only. Result: 1 failed, 24 passed, exactly it.
Gates: 3.14 repo and 3.11 transmitter run before commit (see log).
