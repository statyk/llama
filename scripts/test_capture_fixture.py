"""scripts/capture_fixture.py --from-cache cuts a fixture from ~/.llama/cache offline."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_fixture as cf


def test_from_cache_writes_the_slim_shape(tmp_path):
    root = tmp_path / "root"
    (root / "cache").mkdir(parents=True)
    full = {"metadata": {"title": "t", "description": "d"},
            "files": [{"name": "a.mp3", "format": "VBR MP3", "length": "100", "md5": "m", "title": "A",
                       "size": "1", "crc32": "x"}],
            "reviews": [{"reviewtitle": "r"}], "server": "ia800"}
    (root / "cache" / "md_x.json").write_text(json.dumps(full))
    out = tmp_path / "x.json"
    cf.main(["--from-cache", "x", str(out), "--cache", str(root / "cache")])
    slim = json.loads(out.read_text())
    assert set(slim) == {"metadata", "files", "reviews"}
    assert slim["files"] == [{"name": "a.mp3", "format": "VBR MP3", "length": "100", "md5": "m", "title": "A"}]
