# Required: disambiguates test-module basenames shared with llama/herder
# (test_no_llama_imports.py exists in both herder/tests and emcee/tests)
# under pytest's default `prepend` import mode. Do not remove; if a third
# package ever needs the same, switch root pytest.ini to
# `--import-mode=importlib` instead.
