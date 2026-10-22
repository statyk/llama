# Taper set/encore markers: SDD record

Record of the subagent-driven build of "piece 2: the taper's set/encore markers win" (branch held-backlog-taper-markers). Spec: docs/superpowers/specs/2026-10-22-taper-set-markers-design.md. Acceptance write-up: docs/superpowers/2026-10-22-taper-set-markers-evidence/acceptance.md.

The cycle was run by three successive peer orchestrator sessions, orch, orch-r1 and orch-r2, whose parent was llama-db; each dispatched the implementer, reviewer, fix and measurement subagents named below. Contents:

- `orch/`, `orch-r1/`, `orch-r2/`: each orchestrator's `ledger.md`, copied byte for byte. orch-r2's ledger is the copy taken at the final-review fix (t9-rewrite), and `orch-r2/deferred-minors.md` is its list of minor findings deferred out of this run.
- `verdicts/<task>.md`: the `handback.md` report of every subagent task (implementers `*-impl`, reviewers `*-rev`/`*-rr*`, fixes `*-fix*`, the Checkpoint A/B pre-screens `cpa*`, `pre2-*`, `pre3-*`, `acc-explain`, `rescreen2`; the docs task `t9-docs` and the final branch review `final-rev`). Copied unedited. t9-fix1 left no `handback.md`, so it has no verdict file.
- `evidence/orch/`, `evidence/orch-r1/`: the orchestrators' evidence directories, relative paths kept. Size policy (orchestrator ruling R21): only files of 256 KB or less are committed; each larger file has a line in `evidence/LARGE-FILES.txt` (sha256, size, path) and lives on only in the worktree's git-ignored `.superpowers/`. Copied and mutated source trees are not committed at all: see "Dropped from the record" below.
- `acceptance/`: the acceptance run 3 record (a9016b5), copied from ~/.llama-harness/piece2/accept3/: `cmp/` summary, taper_cleared, taper_changes, structure_changed, title_sources; `score/score_summary.txt`; `step3.txt`.
- `mutation.md`, `spec-review/`: the mutation record and the spec reviews (written earlier).

## Dropped from the record

Operator ruling (final review, finding I1, option (a)): the record commit was rewritten so that copied and mutated source trees never reach main's history. 497 files, 8,654,718 bytes (8.7 MB), were dropped from `evidence/`; what remains are the reviewers' own runner and probe scripts, the one-line mutant definitions (`mut.py`, `mut.sh`, `mutants.json`, `gen.py`), logs, measurement outputs, ledgers and verdicts. Every dropped byte survives in the backup ref `backup/taper-markers-record-8ed8d0c` (commit 8ed8d0c, the pre-rewrite record at `docs/superpowers/2026-10-22-taper-set-markers-sdd/evidence/<path>`) and in the worktree's git-ignored `.superpowers/sdd/taper-markers/` (`<orch dir>/evidence/<rest of path>`). Four lines of `evidence/LARGE-FILES.txt` (the `set_breaks.csv` copies) name files inside the dropped `orch/t12-rev/{mut,c_*}/` trees.

| Directory | Files | Bytes | Why dropped |
|---|---:|---:|---|
| `evidence/orch/t12-rev/mut/` | 162 | 3,005,054 | the T12 reviewer's mutation tree: a copy of the repo's `packages/llama` (src, tests, LICENSE, pyproject.toml) with mutated `taper.py` and `stages/gather.py` |
| `evidence/orch/t12-rev/c_025e713/` | 62 | 808,433 | a copy of `packages/llama/src` at commit 025e713 (recoverable from git at that commit) |
| `evidence/orch/t12-rev/c_3d1c1e7/` | 62 | 805,268 | a copy of `packages/llama/src` at commit 3d1c1e7 (recoverable from git at that commit) |
| `evidence/orch/t12-rev/c_67291bd/` | 62 | 801,424 | a copy of `packages/llama/src` at commit 67291bd (recoverable from git at that commit) |
| `evidence/orch/cpa2-tiers/versions/` | 8 | 227,725 | `taper.py` at eight branch commits, each byte-identical to `git show <sha>:packages/llama/src/llama/taper.py` for the sha in its name |
| `evidence/orch-r1/mut/` | 11 | 198,569 | a scratch copy of the repo's top level (CLAUDE.md, LICENSE, README.md, .gitignore, pytest.ini, .github/, packaging/) |
| `evidence/orch-r1/red/` | 11 | 198,569 | a scratch copy of the repo's top level, as above |
| `evidence/orch-r1/red2/` | 11 | 198,569 | a scratch copy of the repo's top level, as above |
| `evidence/orch-r1/t6-rev/m_A/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_B/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_base0/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_C/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_D/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_F/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_G/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_I/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t6-rev/m_J/` | 11 | 198,569 | a T6 reviewer mutant/base scratch copy of the repo's top level, as above (the one-line mutants themselves are in `orch-r1/t6-rev/mut.sh`) |
| `evidence/orch-r1/t4-fix1/M0/` | 1 | 220 | a stray copy of the repo's `pytest.ini` |
| `evidence/orch-r1/cpa3-r*` | 2 | 76,583 | pre-mutation copies of `packages/llama/src/llama/taper.py` (`taper.orig`) |
| `evidence/orch-r1/` | 6 | 547,183 | whole-file copies of repo source: `gather.full.py`/`gather.head.py` (`stages/gather.py`), `test.head.py`/`test_stage_gather.full.py` (`tests/test_stage_gather.py`), and `tests_head.py`/`tests_tail.py` (test text that was added to `tests/test_taper.py`, where it now lives) |
| **total** | **497** | **8,654,718** | |

Per-file list (sha256, size in bytes, path under `evidence/`), by directory:

<details><summary><code>evidence/orch/t12-rev/mut/</code>: 162 files</summary>

```
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch/t12-rev/mut/packages/llama/LICENSE
e70b49bd1cd53a2a53277991a19c8016d45aa831086178673fd2d8a9a30ca8da       599  orch/t12-rev/mut/packages/llama/pyproject.toml
904b602ee93f132eba8b8c8c0137539a411bdd4363bee696d97336f9aae83347       539  orch/t12-rev/mut/packages/llama/src/llama/__init__.py
36966479a214299cd056823afc51f8bc291b1f4409399f37e723caf17446dd1f       138  orch/t12-rev/mut/packages/llama/src/llama/__main__.py
c1a20620f1b85a127ecbc20af030c2fac0ee80f23b468b3d5a806627766c7851      7135  orch/t12-rev/mut/packages/llama/src/llama/artist_index.py
cf6f5b63cf463ece0ca85b7f3ef4f922b11db4cd0566567e10542ee53dbb73c1      1317  orch/t12-rev/mut/packages/llama/src/llama/audio.py
63547dbc6889eeb2e581689e94d12324c4162e4758da2b97551a3199ba94f346     15445  orch/t12-rev/mut/packages/llama/src/llama/catalog.py
01c38fc28089e3ec4a9c5d33cacf985e81c5aa8a6dbae6ef9002d1664c6c98d6    209603  orch/t12-rev/mut/packages/llama/src/llama/cli.py
1b4104b6dde1615cbc3ae8108c2c592b5afcd7d0c9f5b71ccef687ae9e1b2d0a      3104  orch/t12-rev/mut/packages/llama/src/llama/cli_select.py
e4a6e73d53fcae0e2299f9e2f8c0e8a6fba812fc4423800b9b258985a2db4d66     11868  orch/t12-rev/mut/packages/llama/src/llama/config.py
bd92abe317d529db0dd15e66e0f8eb63726bb6e44332d3b7562062e0a6ce831b     16888  orch/t12-rev/mut/packages/llama/src/llama/correspondence.py
64d4041648335e86a829562155cde0481ab28a152da03f563e636a679f713875      1451  orch/t12-rev/mut/packages/llama/src/llama/data/README.md
174ae16ad1c6b425fd8693bb85ad7b39e877a9f1c29e989773efe9d39b604cf9        63  orch/t12-rev/mut/packages/llama/src/llama/data/__init__.py
542b9531c255cdee9b027dd304e40adbb88102d24d4be098c0973732cd98d9dd      2653  orch/t12-rev/mut/packages/llama/src/llama/download_slots.py
bf066f51994ef376882d6cae19a124de337012dca1ed0a86a1f3ff1b1dfbaaa1      1163  orch/t12-rev/mut/packages/llama/src/llama/errors.py
ec68ac9560ddacdaae566698c133569ef3f2dd6cc82296b9267a92cc3f19c019      5192  orch/t12-rev/mut/packages/llama/src/llama/grouping.py
cbfa0383f8c45aef8d43c062364763a17fddc2dfefa3306832bad5300c8808a6     20097  orch/t12-rev/mut/packages/llama/src/llama/ia_client.py
1453941b8ca2f77f7e5993055193217a0d2f1b0f8ae37c43d4f4cad69166a41c     16101  orch/t12-rev/mut/packages/llama/src/llama/jerrybase.py
66fa15048a54a78ad53b9f480d4c034d5ac141751af972c33bdba918f964ce24     14314  orch/t12-rev/mut/packages/llama/src/llama/junk.py
0e8fe3b1a462108d3d3e690abce76760ea658a93e68520b0b95d0df2967dffb4      2628  orch/t12-rev/mut/packages/llama/src/llama/ledger.py
712eb2cdf68b5c154b455302474b0dfbc6b978481d680b19edfc3b09658d2dc3      3957  orch/t12-rev/mut/packages/llama/src/llama/locks.py
eaf13625bd8e68a1909a4ea50fe1ac92fbef3edb73ed79aec418088a171b3539      1361  orch/t12-rev/mut/packages/llama/src/llama/manifest.py
042957174d12b12046b245afc80fe47b47a3e0a5c3e9ea29bd5471f2a188cabb     17827  orch/t12-rev/mut/packages/llama/src/llama/models.py
780837e4dd3a02c90effa2b018002de0a8267d3d1c9534dbb13570ca49df78c4     13290  orch/t12-rev/mut/packages/llama/src/llama/pacing.py
79bb3c04c086313377287a6ccd5e41b267025ac524a04e85e474187d17f131e5      5387  orch/t12-rev/mut/packages/llama/src/llama/pacing_state.py
4ee853edbc5c47f4ef431d7eaf66724e2f4cef0263afc65ced7217de2c092a84      7500  orch/t12-rev/mut/packages/llama/src/llama/pipeline.py
89a415fddb1090ffbfa7f43426d4e87276c1a89136279e13305471cb28b7eda9      7624  orch/t12-rev/mut/packages/llama/src/llama/placeholders.py
ce676c1a7bfc1c4b7b4febc883fc66c4a31d958f7544fd4a3eadc0c52faa0a4a      1928  orch/t12-rev/mut/packages/llama/src/llama/profiles.py
ad6b616496ec5967e27edb823006223fc46b48587a6c381d850f836478d6717d       148  orch/t12-rev/mut/packages/llama/src/llama/prompts/__init__.py
73fa79383436f0075af2255ba1ccd94fc37fd3d598d06607d4bb688d69fdcb8c      1091  orch/t12-rev/mut/packages/llama/src/llama/prompts/align_structure.md
0745db187c77b5234367508e89e1ab4ad5fe3ba60124372aed43051f5a906fde      2009  orch/t12-rev/mut/packages/llama/src/llama/prompts/brief.md
e20d4394b052e157fa2e63dd66acf919392c85c90369c734ef670c33851775f5      1154  orch/t12-rev/mut/packages/llama/src/llama/prompts/deep_research.md
ed1aea4983eef7a3607843a45d49dd050e6ee6ff8c7e350aee92501a9be928f1       801  orch/t12-rev/mut/packages/llama/src/llama/prompts/extract_setlist.md
fd3c66183825f2dcc4c5049ef1194b9bbce44f5b69e40091d04d7092645adce5      1029  orch/t12-rev/mut/packages/llama/src/llama/prompts/find_artists.md
84184a1ffd5d35c2d9697a97cde43291acfb66a07c4c744f984deb48690c7401      2442  orch/t12-rev/mut/packages/llama/src/llama/prompts/interpret.md
82fe78aefc4508f7379cec7b5eb673ee820cda9889cd6b5c051162d1ea3b0059       595  orch/t12-rev/mut/packages/llama/src/llama/prompts/light_research.md
783740367e988fc0afb525e1d3b8bdc1aac5fd7fdfabb1742e3f30cecc50fb97      1238  orch/t12-rev/mut/packages/llama/src/llama/prompts/score_reviews.md
a079ab03053f566e8c6d3d19f1bbafea642b275058ad1aa320a76a9e19fbd89b      1566  orch/t12-rev/mut/packages/llama/src/llama/prompts/vet_research.md
f7a178416a7a3964bea859bb936482c1538a18a317aeecec0ecc725329ac2ee2     12639  orch/t12-rev/mut/packages/llama/src/llama/reapply.py
cb05723d6c9fab2aa74be5ae2289a6fbba5fabf2c3de354ae03c0b993c78c7de     21792  orch/t12-rev/mut/packages/llama/src/llama/replay.py
21d575c2fd7ecdf29c94157078b4ab122c7bafe34b83fc9149468634a03c218a      2056  orch/t12-rev/mut/packages/llama/src/llama/scoring.py
716b96494830440a5923b0be36e1d5d34a5e5c3ed530370ac4d873c7b93e17cd     13213  orch/t12-rev/mut/packages/llama/src/llama/sessions.py
0261db5282875af6cc5a4f6c4d6eddd6924fae917629cc8df79543165fe73473     29081  orch/t12-rev/mut/packages/llama/src/llama/setlist.py
03eaac8343eb7019a4d5afb6afc9e8b21313038992945812feffff3d8d4fbbb1      4942  orch/t12-rev/mut/packages/llama/src/llama/setlistfm.py
a95b093568a0f878a0f535a325a84bf5c7944a1aeb71f156a225c97df7e10284      5660  orch/t12-rev/mut/packages/llama/src/llama/show_unit.py
3dd61ba6d3c4619c4079274f479aaa63d17c466516a6774f0de8e8720d833dfc     26419  orch/t12-rev/mut/packages/llama/src/llama/siblings.py
5e112a5e27870a0a9c78da4a730ed23deb623297bbb73da889be008f603ee932      3337  orch/t12-rev/mut/packages/llama/src/llama/songs.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855         0  orch/t12-rev/mut/packages/llama/src/llama/stages/__init__.py
5e9ec06ac09feb76f921a9719ed7a4292aa9c2994b24088b9ca45dd1217926bf     17944  orch/t12-rev/mut/packages/llama/src/llama/stages/brief.py
985834c838112fac6128af761e59a06d6f8193bfb43b27694d98635f298e6b4b      1636  orch/t12-rev/mut/packages/llama/src/llama/stages/discover.py
a23c31944bd9d886a5d1a8ae52861887fa9b6af4d4a9e8a0434b98cb324803c7     85336  orch/t12-rev/mut/packages/llama/src/llama/stages/gather.py
28710555513c29485cb4d9a671d0247c5c83073424a1847a48e6b448b72a8abd       633  orch/t12-rev/mut/packages/llama/src/llama/stages/interpret.py
9ccfbe8e9f0f392efc688cddda1d187c693408de60773a71ba77cf31c7eedd74      4863  orch/t12-rev/mut/packages/llama/src/llama/stages/package.py
402682e6e36eba67335bab0c83538a475702f13a72d1cf3909921d2f205dd0d2      1053  orch/t12-rev/mut/packages/llama/src/llama/stages/research.py
fef3ae7a34da6b361d14871ce44b1ec180550d564f3b1d677e2f0c4b49670af9      2403  orch/t12-rev/mut/packages/llama/src/llama/stages/search.py
6bb91167be35b5ad3e92384de3801d12c64f25c8585689a5f78035eb67c23f35      4479  orch/t12-rev/mut/packages/llama/src/llama/stages/select_recording.py
ec53ee4224afdfecb5990cd503a37a69d3e0fdf04d69111bf3744c173d5cb5fd     15172  orch/t12-rev/mut/packages/llama/src/llama/stages/vet_research.py
6963d3d085b97130a888337c7773b3cb25063588a67f7c6949a4b252a406bf21      7348  orch/t12-rev/mut/packages/llama/src/llama/stages/winnow.py
cd182f74c49a4ec1b3dfcad7fbb6e02dc60f76d72c9ea5802f695a1fc5eaa19e      4847  orch/t12-rev/mut/packages/llama/src/llama/status.py
ee25e70164d391435ccea40d3c038d80484b34ead43a22718a86647d7e5f3fd2     74781  orch/t12-rev/mut/packages/llama/src/llama/structure.py
2a5a28890abeef165fbdbf7542551865435e980fccd94e0741d350fd1efe87da     33067  orch/t12-rev/mut/packages/llama/src/llama/taper.py
fd90e1882529d0fbe513dd42cbd17e388c92029730bd0c3f9a837a441f5438a4     28964  orch/t12-rev/mut/packages/llama/src/llama/titles.py
202d41232f222a7a6f78c8ffb3756b5fd803a5ef8ede5215a84b26ff45c04db3      3968  orch/t12-rev/mut/packages/llama/src/llama/util.py
8b829d9c0e15069cc167472c5230f92d8be43e50691207f85fb1839860c300cf      4964  orch/t12-rev/mut/packages/llama/src/llama/workspace.py
a6bbcc7a4ce1b1832a2b501e5bd0d7a4131550e5ee03d86d8076351833b6a89d      2702  orch/t12-rev/mut/packages/llama/tests/conftest.py
33d080128887facbde2cd1562019448b0c77cb177f365564584ec2ca082a3a3a      5467  orch/t12-rev/mut/packages/llama/tests/fixture_library.py
6139ca50a89bb4ca6400895a7b17f76fe5abd3ca4e139cd8ec1175d2f90faefe     30784  orch/t12-rev/mut/packages/llama/tests/fixtures/dso2003-01-25.json
6975efaae82fdb739859ea6b3ac1e321090ad6eb860072a2c5a21eedcd517ddf     28110  orch/t12-rev/mut/packages/llama/tests/fixtures/furthur2012-07-15.json
facdf2e6b0ef1f72bb3ede5bbfa68237718abeac4d8fe13f64bc2063121ca65a     42364  orch/t12-rev/mut/packages/llama/tests/fixtures/gd1970-02-14_late_metadata.json
005fb0efb8c7cf881037d07ec854dad71ea1af4b6671fb47741d49f5167539d3     71916  orch/t12-rev/mut/packages/llama/tests/fixtures/gd1970-02-14_spans_metadata.json
c0a67c7b120d21b32dadfdbf24f26443bf0c28718732220721f3b536d22f7278      3269  orch/t12-rev/mut/packages/llama/tests/fixtures/gd73_metadata.json
76ba25281c8b89315488508d41a616b1b4078023045d0d603e30eca4a98efb58     49551  orch/t12-rev/mut/packages/llama/tests/fixtures/gd74_miller_metadata.json
0456ad134aa1bbb147a334a833eb031892c458a5e08e8dc89fef2693f48e7f82     86923  orch/t12-rev/mut/packages/llama/tests/fixtures/gd74_windsor_metadata.json
c7dc15bd37f108469b10f9dec7da35c25cd21efef678f14ffa90f5d5d20e8b3f     27212  orch/t12-rev/mut/packages/llama/tests/fixtures/gd78-11-17_dodd.json
6669d1487d8af2b1843f51710ad82e8d6a30c6d70c5994589e97b639a5fdf66e     27804  orch/t12-rev/mut/packages/llama/tests/fixtures/guster2003-07-10.json
b965c608e6d6d3cf4f37768f0841f320cbd62e2654cea1a24d4d4f66f688816c     29392  orch/t12-rev/mut/packages/llama/tests/fixtures/rre2013-11-30.json
894a6a9555f3b9e0ad33c2a3dd586f954a36cbdcc39f5d4e929018d791c1c369      1618  orch/t12-rev/mut/packages/llama/tests/fixtures/slfm_gd_1974_02_24.json
2b6f29c9571791bfc5e88ca5fdb5e0ff3732532247254739fe2e87e7758fe80f     41829  orch/t12-rev/mut/packages/llama/tests/fixtures/tnd2006-12-13.json
573534d5e583c88c0cf65489785ea6a8b8897e09b5855baf811f476a42c54d60     54004  orch/t12-rev/mut/packages/llama/tests/fixtures/ymsb2005_metadata.json
5a25881fb5ce29c3a7d97085619cfcfc0aa6c1a0e301291b942623aed8950462      3443  orch/t12-rev/mut/packages/llama/tests/helpers.py
b4d0d2489e9e493d26027086107bfe49b06ed0a58ab62b3b9eac3dba64267fd2     10107  orch/t12-rev/mut/packages/llama/tests/test_artist_index.py
8d92ff198086610de3dc0dc2aaae806dc344ab022ac939e30307528397a4d86e      4137  orch/t12-rev/mut/packages/llama/tests/test_artists_cmd.py
f1ab5ec1b400a00f4d1d05f55458f36b2675465008b922b8aa4d8fcdba5d2b95       925  orch/t12-rev/mut/packages/llama/tests/test_atomic_write.py
ad6e0010aee6dbf30738a0811e2477ce4a4c03b308126ea9ba0380aa854a5c49      1131  orch/t12-rev/mut/packages/llama/tests/test_audio.py
2e4cb3e1259873be3bdcd61361f4998684bac8559c396ed746d3ecb00ef198b0      8725  orch/t12-rev/mut/packages/llama/tests/test_catalog.py
83051fe6c0d50d0ce23ad112fbf57e066acb1541341764651be7a64f36602bb6     80427  orch/t12-rev/mut/packages/llama/tests/test_cli.py
2d8d275deaebbe104152b569af7aed11884b9dcdbdfb0192f74e7394a6e206ae     27191  orch/t12-rev/mut/packages/llama/tests/test_cli_commands.py
d31a6b19ccbe236ef7da7f1f7ffb11969cef9b8dff5db99a086f3a93d6d33aa9      1583  orch/t12-rev/mut/packages/llama/tests/test_cli_errors.py
80aaaa394bdc972cb9c965b3d0163ae3e7c755795411131e03be6a3425606148      5399  orch/t12-rev/mut/packages/llama/tests/test_cli_select.py
1651e94ee306e46812ad49fcfe54977fd36b582faaca57a2140c209de3420599      1154  orch/t12-rev/mut/packages/llama/tests/test_concurrency.py
3c2de31f316d699f279e81811caa7934f7c9ef532cea6dd62d7710ebbf83efb0     13285  orch/t12-rev/mut/packages/llama/tests/test_config.py
6922e52e8d1c8220a65178965edb0799d8cc6f0fd2fad0183b1f203b2ba359fa     30720  orch/t12-rev/mut/packages/llama/tests/test_correspondence.py
00492c7e0c96f35c3b0a42191b8fd760df8ffd019dd2711a40302265d555a68b     23053  orch/t12-rev/mut/packages/llama/tests/test_deliver_cmd.py
af770d8f89ef4e416d7351c222d1866e6834f09ba79dce7943945902d8181cd1      1375  orch/t12-rev/mut/packages/llama/tests/test_deliver_gate.py
c4c8c57e67ae971872c6dee1849252628631eee96515340f0b0d285256d4de36      4105  orch/t12-rev/mut/packages/llama/tests/test_download_slots.py
8137bafbf06c2bb8fb1bb81549e3ef7ee48c00ad5f7b26a611fb6fadc5a8ef7c      1509  orch/t12-rev/mut/packages/llama/tests/test_errors.py
b32543a77b84a277b62889cf652b4fa8a455ed88170db43cfa0522efa1b97fc2     43562  orch/t12-rev/mut/packages/llama/tests/test_fix.py
a9fe1957d8220a1eab393fc8d6a0480e81baf8fd446387972c42215550b73b4b      1087  orch/t12-rev/mut/packages/llama/tests/test_fixtures_multi_event.py
98954e5a5f2bd7998dd3f13e6ed6151849e08e257db66573b71c4ca372fec2d5     22421  orch/t12-rev/mut/packages/llama/tests/test_get_cmd.py
a522fa54f27b19b327af0be0fdc6639901a083267d42e9f1303a7c6e705e4e39      6997  orch/t12-rev/mut/packages/llama/tests/test_grouping.py
3594f68e153a7df09b6b459e4efb6d320d3b0efc19ca0a8611c0ee9265f49ec7      8926  orch/t12-rev/mut/packages/llama/tests/test_history_cmd.py
44a2a43aeed0f2b3adbe69ec034d8f7e5cc31046d7b0a916aaff09ba5d0982ef     48958  orch/t12-rev/mut/packages/llama/tests/test_ia_client.py
202e23682318b8d3337e318cd6d4175355c8babe900ec2ddcd597039b34ccd2d     19648  orch/t12-rev/mut/packages/llama/tests/test_jerrybase.py
54a72af66ba365b9bdde5eef99a20288c459e9e8393129e4464f2aeff228d0d3     18875  orch/t12-rev/mut/packages/llama/tests/test_junk.py
e4683c6a0bc66dd67fe409e2c31efbe3ac523074b8407bc38315147564f3fd13      2784  orch/t12-rev/mut/packages/llama/tests/test_ledger.py
2b502e7afc5c1ba2914e77d359c70efd46339eb1f4eca0df13dedad83e39717f      1172  orch/t12-rev/mut/packages/llama/tests/test_ledger_concurrency.py
c12136591b8e5e726f824f74414ad77fe1966c0390c65c4b2977ee6a47812f81      1355  orch/t12-rev/mut/packages/llama/tests/test_library_dedup.py
bb047d65ad14b7f6453b3c90b9ced75e138c1a32ac2ddb29a74b8f39c7bfcb7d      4664  orch/t12-rev/mut/packages/llama/tests/test_live_smoke.py
0e0ac25f672e065558708ee8df175fd3ea443ed0c450749f3b5b97a52f3f773c      1495  orch/t12-rev/mut/packages/llama/tests/test_locks.py
ebd92fc89b2cdf1cc1f8aedf9618a6c8cba6582e455451b97569057aa14dcc96      3884  orch/t12-rev/mut/packages/llama/tests/test_manifest.py
94209a226f2eff9f48cefe3b384856240f679b83dd4f5c207eb57b8dff4ac48e      4287  orch/t12-rev/mut/packages/llama/tests/test_models.py
6f80c00824faa5bf855cdda2391cebfb53d20f3252d6a2c4b803c94f7d053902      3447  orch/t12-rev/mut/packages/llama/tests/test_multi_event_integration.py
bc931babfb57acaa58894a8396c0bdc42bbaa20c416d1ebb77928649507b96f7     72972  orch/t12-rev/mut/packages/llama/tests/test_pace_loop.py
fdcef16cb368c343b83b99dcfd7117a7f1e41ab320753f5ad301595cedbe638e      7885  orch/t12-rev/mut/packages/llama/tests/test_pacing.py
54cb5cf8447281ecfd5f704eadda4d92de352d507ec4b41effad89a46adb9c8e     10460  orch/t12-rev/mut/packages/llama/tests/test_pacing_decide.py
2b19641cdba7cc01e67b58a4f27ade6635e5bf0b9e3d32fa1f81772d0d1363c2      8934  orch/t12-rev/mut/packages/llama/tests/test_pacing_state.py
17c027022df956b897ddd11257fc679cffb9996cd9011b3171b321910ac53857     14459  orch/t12-rev/mut/packages/llama/tests/test_packaging.py
01025f61026e3a33f9bd0cd9087fbca30c28f71105356d0d9253ec29f692ec59     18795  orch/t12-rev/mut/packages/llama/tests/test_pipeline.py
c6d22294227a008d0e933a9ce5cf918c6f4cbbfbf53c06b9655efe4fcbbf4fd3      5083  orch/t12-rev/mut/packages/llama/tests/test_placeholders.py
584582b07af1054cc99b1e2cf443716fcc7e54bdf533f08d3971c176086a7e46      9915  orch/t12-rev/mut/packages/llama/tests/test_profile_selector.py
1ce635ca614a965c9673a3e93669c09cd1b8eb6038c9bfeebc66a9eb7e962b26      3292  orch/t12-rev/mut/packages/llama/tests/test_profiles.py
37c2bbad5396af76e781964f219050a8b53982d3ce501f856270c2a9b438b1f5      1386  orch/t12-rev/mut/packages/llama/tests/test_prompts.py
1250b145050ceb807ea833cc7c67fdeeb7a9601793d2b9acf759ec37786b5ae4     13996  orch/t12-rev/mut/packages/llama/tests/test_purge_audio.py
468e7fbfa6daa868fec990220125453080d0374cd3f23de64d04f02d184fa2f2     53968  orch/t12-rev/mut/packages/llama/tests/test_reapply.py
3ee95e96bbb30c8ac65853f11499c54349aef183a5e478c77e459aef3d7f19bc      2262  orch/t12-rev/mut/packages/llama/tests/test_recording_info.py
7539b787ff1dadf19638c3f24e5bbe9a82d3830c678e324d748fdce14a5fd586     36421  orch/t12-rev/mut/packages/llama/tests/test_redo_cmd.py
8d02905a6fd4f1cbd1fc9a941dad0ebd9e4299fc72dd6cd4c58eca0843215681       976  orch/t12-rev/mut/packages/llama/tests/test_refresh_jerrybase.py
d774d97b8fc6a85cf5085ab79271bcdb2d6ec24ee4ba65effb17a6eda5c25f04     32956  orch/t12-rev/mut/packages/llama/tests/test_replay.py
008d18ae8bcdc821c5a867b9ef3a5a169f299781bb8abd41a84fd2eb629c9704      7632  orch/t12-rev/mut/packages/llama/tests/test_rm_cmd.py
12e8bc0cf2c1210362b3cc9a9a692f72e26a14064fc886d01aebe91ecc6724ae      5636  orch/t12-rev/mut/packages/llama/tests/test_rm_machinery.py
7c1172d534266e6c5b8216b16f893758053b1ce8b20127aaf993f90eb50f1ee2     17960  orch/t12-rev/mut/packages/llama/tests/test_run_lock.py
7bc6fa5ee776dfc9d5b253a41a6814c2dfd117fa46a2d469f26b5fb61737d8e0     28283  orch/t12-rev/mut/packages/llama/tests/test_run_namespace.py
82876a96aa987c28948abf7a7de27f1eb9e363e61aabf118a759379305562873      4967  orch/t12-rev/mut/packages/llama/tests/test_scoring.py
949515554169df48edc822fbbc7dff001488b5e2d76f4927f98f670cbb378107     84659  orch/t12-rev/mut/packages/llama/tests/test_sessions.py
4c9507735fabb9603a176d0a8807f87c56614cdf70cf24364953bce0f192451c     45871  orch/t12-rev/mut/packages/llama/tests/test_setlist.py
45366dde59ab209d58d12d5dc218e066b34b129cd017a1cf5910b8e84b510ee0      6376  orch/t12-rev/mut/packages/llama/tests/test_setlistfm.py
79c1df932ae86bad2611ba0d5e7d8fc0732a439d4bb7bac292263728ba7b7725     23948  orch/t12-rev/mut/packages/llama/tests/test_show_cmd.py
dc0301c74d9a1edb3a2c68e72c275aa9323ca3777b99b91432ae95f499410efe       265  orch/t12-rev/mut/packages/llama/tests/test_show_lock.py
ec92087c59fb38e6977bc38be649f3f53a6f7bb29c0c3788cf0e88f82ed29cca      6872  orch/t12-rev/mut/packages/llama/tests/test_show_unit.py
e731062c9b8f24d85edaa262cdc5a069ebbac058ec7810beb90d491b9bccab46     50880  orch/t12-rev/mut/packages/llama/tests/test_siblings.py
c954454153bf907b5c7c837fa6d2ded84a33e8df6818775253d0946961e4c6e2      1033  orch/t12-rev/mut/packages/llama/tests/test_songs.py
cdf5b3cb28bc9df568a9b761c73263c772ad78f2902111e0e3ec5830d722c578     25199  orch/t12-rev/mut/packages/llama/tests/test_stage_brief.py
93216f090b535b22d3b24b0c62a0b5b08fae9301ccd8a383d2e0141172827ebc      4138  orch/t12-rev/mut/packages/llama/tests/test_stage_discover.py
afeefd510b37e9a28011802429bc831c88036aaf964114bc950535d33d69041b    172926  orch/t12-rev/mut/packages/llama/tests/test_stage_gather.py
8364eece83732498e0a58062d26ca0028fd803d0c2645eb9e9a50e25af62d9c9      1412  orch/t12-rev/mut/packages/llama/tests/test_stage_interpret.py
ab85d0a8d2ccf1771498a7679789575fafd68a2b8374e8b790e20bb57606d7b5      8837  orch/t12-rev/mut/packages/llama/tests/test_stage_package.py
c2edae27045920399b7653fd37410d9119b7709784b14a2985750343b9d5abaf      1922  orch/t12-rev/mut/packages/llama/tests/test_stage_research.py
02d89bad0d361edb2c63ec3c2c6534f56f5b3140697ae0442d6adc4f009fb992      3973  orch/t12-rev/mut/packages/llama/tests/test_stage_search.py
2eff730f8961478e091b7daecaf7a0c923b574085380c2be9ba0c109dd6be560      8529  orch/t12-rev/mut/packages/llama/tests/test_stage_select.py
dbc9246c80bddb9d080601975d822bdab3bcb20287295f86930156926009de83     35909  orch/t12-rev/mut/packages/llama/tests/test_stage_vet.py
f7872ae9cd5108a6e89fcdca6b7c94556f6cbfeb15817d8b4fb4f4c0792c3959     17945  orch/t12-rev/mut/packages/llama/tests/test_stage_winnow.py
613a66c4206cfe78c0774768f1a17103038e1c96bba48c3f7556bbaa60ce242f      6387  orch/t12-rev/mut/packages/llama/tests/test_status.py
2350c729c14bf59fc1dfa0de65e5953bb87def878e2a8adf15a3bfc3b6c19304     12927  orch/t12-rev/mut/packages/llama/tests/test_status_cmd.py
94b71c1f80693b4a8213e1f8544789c92c5031fc113ead27daeca1a45bff26e7    107078  orch/t12-rev/mut/packages/llama/tests/test_structure.py
c0c586afb599ea4a6753f3b1ae6f0ca4e99c48af81f6bf9d46fae6790eb84ee5     22803  orch/t12-rev/mut/packages/llama/tests/test_sweep.py
9d757f68b8a2bc6a8aa8cac706328116ddf28eecac8feaed65837a667c7f4e18    147520  orch/t12-rev/mut/packages/llama/tests/test_taper.py
924ee3a64d0c5b8b87d99b325dda7dd3a7409f88008838a1bea31024d145cd12      3205  orch/t12-rev/mut/packages/llama/tests/test_the_cut.py
12c5a712bd57033d5207b3afff1dd0740b36a6ad8dd3cbb2ade7324c43afa1f9     36497  orch/t12-rev/mut/packages/llama/tests/test_titles.py
94f70f015fd620e92b48330e883c540aeb82e45cca8a38aa277fe713be250939     34112  orch/t12-rev/mut/packages/llama/tests/test_triage.py
cf1b752e130d72aab82a8c1d84067802acf4ba229a5d9b15c4f5f4f55a145870      7352  orch/t12-rev/mut/packages/llama/tests/test_util.py
37e6668052cd541bb57f54d5e865e23d7075c3c139efbfba12d9bb0f6b0acbb5       646  orch/t12-rev/mut/packages/llama/tests/test_version.py
335a13244015a6eaab8aa3fa8a0abac2bec56f93cc6090480a98405e0d1210cc      5828  orch/t12-rev/mut/packages/llama/tests/test_workspace.py
```

</details>

<details><summary><code>evidence/orch/t12-rev/c_025e713/</code>: 62 files</summary>

```
904b602ee93f132eba8b8c8c0137539a411bdd4363bee696d97336f9aae83347       539  orch/t12-rev/c_025e713/packages/llama/src/llama/__init__.py
36966479a214299cd056823afc51f8bc291b1f4409399f37e723caf17446dd1f       138  orch/t12-rev/c_025e713/packages/llama/src/llama/__main__.py
c1a20620f1b85a127ecbc20af030c2fac0ee80f23b468b3d5a806627766c7851      7135  orch/t12-rev/c_025e713/packages/llama/src/llama/artist_index.py
cf6f5b63cf463ece0ca85b7f3ef4f922b11db4cd0566567e10542ee53dbb73c1      1317  orch/t12-rev/c_025e713/packages/llama/src/llama/audio.py
63547dbc6889eeb2e581689e94d12324c4162e4758da2b97551a3199ba94f346     15445  orch/t12-rev/c_025e713/packages/llama/src/llama/catalog.py
01c38fc28089e3ec4a9c5d33cacf985e81c5aa8a6dbae6ef9002d1664c6c98d6    209603  orch/t12-rev/c_025e713/packages/llama/src/llama/cli.py
1b4104b6dde1615cbc3ae8108c2c592b5afcd7d0c9f5b71ccef687ae9e1b2d0a      3104  orch/t12-rev/c_025e713/packages/llama/src/llama/cli_select.py
e4a6e73d53fcae0e2299f9e2f8c0e8a6fba812fc4423800b9b258985a2db4d66     11868  orch/t12-rev/c_025e713/packages/llama/src/llama/config.py
bd92abe317d529db0dd15e66e0f8eb63726bb6e44332d3b7562062e0a6ce831b     16888  orch/t12-rev/c_025e713/packages/llama/src/llama/correspondence.py
64d4041648335e86a829562155cde0481ab28a152da03f563e636a679f713875      1451  orch/t12-rev/c_025e713/packages/llama/src/llama/data/README.md
174ae16ad1c6b425fd8693bb85ad7b39e877a9f1c29e989773efe9d39b604cf9        63  orch/t12-rev/c_025e713/packages/llama/src/llama/data/__init__.py
542b9531c255cdee9b027dd304e40adbb88102d24d4be098c0973732cd98d9dd      2653  orch/t12-rev/c_025e713/packages/llama/src/llama/download_slots.py
bf066f51994ef376882d6cae19a124de337012dca1ed0a86a1f3ff1b1dfbaaa1      1163  orch/t12-rev/c_025e713/packages/llama/src/llama/errors.py
ec68ac9560ddacdaae566698c133569ef3f2dd6cc82296b9267a92cc3f19c019      5192  orch/t12-rev/c_025e713/packages/llama/src/llama/grouping.py
cbfa0383f8c45aef8d43c062364763a17fddc2dfefa3306832bad5300c8808a6     20097  orch/t12-rev/c_025e713/packages/llama/src/llama/ia_client.py
1453941b8ca2f77f7e5993055193217a0d2f1b0f8ae37c43d4f4cad69166a41c     16101  orch/t12-rev/c_025e713/packages/llama/src/llama/jerrybase.py
66fa15048a54a78ad53b9f480d4c034d5ac141751af972c33bdba918f964ce24     14314  orch/t12-rev/c_025e713/packages/llama/src/llama/junk.py
0e8fe3b1a462108d3d3e690abce76760ea658a93e68520b0b95d0df2967dffb4      2628  orch/t12-rev/c_025e713/packages/llama/src/llama/ledger.py
712eb2cdf68b5c154b455302474b0dfbc6b978481d680b19edfc3b09658d2dc3      3957  orch/t12-rev/c_025e713/packages/llama/src/llama/locks.py
eaf13625bd8e68a1909a4ea50fe1ac92fbef3edb73ed79aec418088a171b3539      1361  orch/t12-rev/c_025e713/packages/llama/src/llama/manifest.py
042957174d12b12046b245afc80fe47b47a3e0a5c3e9ea29bd5471f2a188cabb     17827  orch/t12-rev/c_025e713/packages/llama/src/llama/models.py
780837e4dd3a02c90effa2b018002de0a8267d3d1c9534dbb13570ca49df78c4     13290  orch/t12-rev/c_025e713/packages/llama/src/llama/pacing.py
79bb3c04c086313377287a6ccd5e41b267025ac524a04e85e474187d17f131e5      5387  orch/t12-rev/c_025e713/packages/llama/src/llama/pacing_state.py
4ee853edbc5c47f4ef431d7eaf66724e2f4cef0263afc65ced7217de2c092a84      7500  orch/t12-rev/c_025e713/packages/llama/src/llama/pipeline.py
89a415fddb1090ffbfa7f43426d4e87276c1a89136279e13305471cb28b7eda9      7624  orch/t12-rev/c_025e713/packages/llama/src/llama/placeholders.py
ce676c1a7bfc1c4b7b4febc883fc66c4a31d958f7544fd4a3eadc0c52faa0a4a      1928  orch/t12-rev/c_025e713/packages/llama/src/llama/profiles.py
ad6b616496ec5967e27edb823006223fc46b48587a6c381d850f836478d6717d       148  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/__init__.py
73fa79383436f0075af2255ba1ccd94fc37fd3d598d06607d4bb688d69fdcb8c      1091  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/align_structure.md
0745db187c77b5234367508e89e1ab4ad5fe3ba60124372aed43051f5a906fde      2009  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/brief.md
e20d4394b052e157fa2e63dd66acf919392c85c90369c734ef670c33851775f5      1154  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/deep_research.md
ed1aea4983eef7a3607843a45d49dd050e6ee6ff8c7e350aee92501a9be928f1       801  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/extract_setlist.md
fd3c66183825f2dcc4c5049ef1194b9bbce44f5b69e40091d04d7092645adce5      1029  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/find_artists.md
84184a1ffd5d35c2d9697a97cde43291acfb66a07c4c744f984deb48690c7401      2442  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/interpret.md
82fe78aefc4508f7379cec7b5eb673ee820cda9889cd6b5c051162d1ea3b0059       595  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/light_research.md
783740367e988fc0afb525e1d3b8bdc1aac5fd7fdfabb1742e3f30cecc50fb97      1238  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/score_reviews.md
a079ab03053f566e8c6d3d19f1bbafea642b275058ad1aa320a76a9e19fbd89b      1566  orch/t12-rev/c_025e713/packages/llama/src/llama/prompts/vet_research.md
f7a178416a7a3964bea859bb936482c1538a18a317aeecec0ecc725329ac2ee2     12639  orch/t12-rev/c_025e713/packages/llama/src/llama/reapply.py
cb05723d6c9fab2aa74be5ae2289a6fbba5fabf2c3de354ae03c0b993c78c7de     21792  orch/t12-rev/c_025e713/packages/llama/src/llama/replay.py
21d575c2fd7ecdf29c94157078b4ab122c7bafe34b83fc9149468634a03c218a      2056  orch/t12-rev/c_025e713/packages/llama/src/llama/scoring.py
716b96494830440a5923b0be36e1d5d34a5e5c3ed530370ac4d873c7b93e17cd     13213  orch/t12-rev/c_025e713/packages/llama/src/llama/sessions.py
0261db5282875af6cc5a4f6c4d6eddd6924fae917629cc8df79543165fe73473     29081  orch/t12-rev/c_025e713/packages/llama/src/llama/setlist.py
03eaac8343eb7019a4d5afb6afc9e8b21313038992945812feffff3d8d4fbbb1      4942  orch/t12-rev/c_025e713/packages/llama/src/llama/setlistfm.py
a95b093568a0f878a0f535a325a84bf5c7944a1aeb71f156a225c97df7e10284      5660  orch/t12-rev/c_025e713/packages/llama/src/llama/show_unit.py
3dd61ba6d3c4619c4079274f479aaa63d17c466516a6774f0de8e8720d833dfc     26419  orch/t12-rev/c_025e713/packages/llama/src/llama/siblings.py
5e112a5e27870a0a9c78da4a730ed23deb623297bbb73da889be008f603ee932      3337  orch/t12-rev/c_025e713/packages/llama/src/llama/songs.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855         0  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/__init__.py
5e9ec06ac09feb76f921a9719ed7a4292aa9c2994b24088b9ca45dd1217926bf     17944  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/brief.py
985834c838112fac6128af761e59a06d6f8193bfb43b27694d98635f298e6b4b      1636  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/discover.py
a23c31944bd9d886a5d1a8ae52861887fa9b6af4d4a9e8a0434b98cb324803c7     85336  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/gather.py
28710555513c29485cb4d9a671d0247c5c83073424a1847a48e6b448b72a8abd       633  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/interpret.py
9ccfbe8e9f0f392efc688cddda1d187c693408de60773a71ba77cf31c7eedd74      4863  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/package.py
402682e6e36eba67335bab0c83538a475702f13a72d1cf3909921d2f205dd0d2      1053  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/research.py
fef3ae7a34da6b361d14871ce44b1ec180550d564f3b1d677e2f0c4b49670af9      2403  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/search.py
6bb91167be35b5ad3e92384de3801d12c64f25c8585689a5f78035eb67c23f35      4479  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/select_recording.py
ec53ee4224afdfecb5990cd503a37a69d3e0fdf04d69111bf3744c173d5cb5fd     15172  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/vet_research.py
6963d3d085b97130a888337c7773b3cb25063588a67f7c6949a4b252a406bf21      7348  orch/t12-rev/c_025e713/packages/llama/src/llama/stages/winnow.py
cd182f74c49a4ec1b3dfcad7fbb6e02dc60f76d72c9ea5802f695a1fc5eaa19e      4847  orch/t12-rev/c_025e713/packages/llama/src/llama/status.py
ee25e70164d391435ccea40d3c038d80484b34ead43a22718a86647d7e5f3fd2     74781  orch/t12-rev/c_025e713/packages/llama/src/llama/structure.py
1c2c22c25ad3fcea6c33b53448443532216328aebffca28ce5194579e9ea5911     30257  orch/t12-rev/c_025e713/packages/llama/src/llama/taper.py
fd90e1882529d0fbe513dd42cbd17e388c92029730bd0c3f9a837a441f5438a4     28964  orch/t12-rev/c_025e713/packages/llama/src/llama/titles.py
202d41232f222a7a6f78c8ffb3756b5fd803a5ef8ede5215a84b26ff45c04db3      3968  orch/t12-rev/c_025e713/packages/llama/src/llama/util.py
8b829d9c0e15069cc167472c5230f92d8be43e50691207f85fb1839860c300cf      4964  orch/t12-rev/c_025e713/packages/llama/src/llama/workspace.py
```

</details>

<details><summary><code>evidence/orch/t12-rev/c_3d1c1e7/</code>: 62 files</summary>

```
904b602ee93f132eba8b8c8c0137539a411bdd4363bee696d97336f9aae83347       539  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/__init__.py
36966479a214299cd056823afc51f8bc291b1f4409399f37e723caf17446dd1f       138  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/__main__.py
c1a20620f1b85a127ecbc20af030c2fac0ee80f23b468b3d5a806627766c7851      7135  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/artist_index.py
cf6f5b63cf463ece0ca85b7f3ef4f922b11db4cd0566567e10542ee53dbb73c1      1317  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/audio.py
63547dbc6889eeb2e581689e94d12324c4162e4758da2b97551a3199ba94f346     15445  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/catalog.py
01c38fc28089e3ec4a9c5d33cacf985e81c5aa8a6dbae6ef9002d1664c6c98d6    209603  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/cli.py
1b4104b6dde1615cbc3ae8108c2c592b5afcd7d0c9f5b71ccef687ae9e1b2d0a      3104  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/cli_select.py
e4a6e73d53fcae0e2299f9e2f8c0e8a6fba812fc4423800b9b258985a2db4d66     11868  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/config.py
bd92abe317d529db0dd15e66e0f8eb63726bb6e44332d3b7562062e0a6ce831b     16888  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/correspondence.py
64d4041648335e86a829562155cde0481ab28a152da03f563e636a679f713875      1451  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/data/README.md
174ae16ad1c6b425fd8693bb85ad7b39e877a9f1c29e989773efe9d39b604cf9        63  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/data/__init__.py
542b9531c255cdee9b027dd304e40adbb88102d24d4be098c0973732cd98d9dd      2653  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/download_slots.py
bf066f51994ef376882d6cae19a124de337012dca1ed0a86a1f3ff1b1dfbaaa1      1163  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/errors.py
ec68ac9560ddacdaae566698c133569ef3f2dd6cc82296b9267a92cc3f19c019      5192  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/grouping.py
cbfa0383f8c45aef8d43c062364763a17fddc2dfefa3306832bad5300c8808a6     20097  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/ia_client.py
1453941b8ca2f77f7e5993055193217a0d2f1b0f8ae37c43d4f4cad69166a41c     16101  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/jerrybase.py
66fa15048a54a78ad53b9f480d4c034d5ac141751af972c33bdba918f964ce24     14314  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/junk.py
0e8fe3b1a462108d3d3e690abce76760ea658a93e68520b0b95d0df2967dffb4      2628  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/ledger.py
712eb2cdf68b5c154b455302474b0dfbc6b978481d680b19edfc3b09658d2dc3      3957  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/locks.py
eaf13625bd8e68a1909a4ea50fe1ac92fbef3edb73ed79aec418088a171b3539      1361  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/manifest.py
042957174d12b12046b245afc80fe47b47a3e0a5c3e9ea29bd5471f2a188cabb     17827  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/models.py
780837e4dd3a02c90effa2b018002de0a8267d3d1c9534dbb13570ca49df78c4     13290  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/pacing.py
79bb3c04c086313377287a6ccd5e41b267025ac524a04e85e474187d17f131e5      5387  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/pacing_state.py
4ee853edbc5c47f4ef431d7eaf66724e2f4cef0263afc65ced7217de2c092a84      7500  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/pipeline.py
89a415fddb1090ffbfa7f43426d4e87276c1a89136279e13305471cb28b7eda9      7624  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/placeholders.py
ce676c1a7bfc1c4b7b4febc883fc66c4a31d958f7544fd4a3eadc0c52faa0a4a      1928  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/profiles.py
ad6b616496ec5967e27edb823006223fc46b48587a6c381d850f836478d6717d       148  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/__init__.py
73fa79383436f0075af2255ba1ccd94fc37fd3d598d06607d4bb688d69fdcb8c      1091  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/align_structure.md
0745db187c77b5234367508e89e1ab4ad5fe3ba60124372aed43051f5a906fde      2009  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/brief.md
e20d4394b052e157fa2e63dd66acf919392c85c90369c734ef670c33851775f5      1154  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/deep_research.md
ed1aea4983eef7a3607843a45d49dd050e6ee6ff8c7e350aee92501a9be928f1       801  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/extract_setlist.md
fd3c66183825f2dcc4c5049ef1194b9bbce44f5b69e40091d04d7092645adce5      1029  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/find_artists.md
84184a1ffd5d35c2d9697a97cde43291acfb66a07c4c744f984deb48690c7401      2442  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/interpret.md
82fe78aefc4508f7379cec7b5eb673ee820cda9889cd6b5c051162d1ea3b0059       595  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/light_research.md
783740367e988fc0afb525e1d3b8bdc1aac5fd7fdfabb1742e3f30cecc50fb97      1238  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/score_reviews.md
a079ab03053f566e8c6d3d19f1bbafea642b275058ad1aa320a76a9e19fbd89b      1566  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/prompts/vet_research.md
f7a178416a7a3964bea859bb936482c1538a18a317aeecec0ecc725329ac2ee2     12639  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/reapply.py
cb05723d6c9fab2aa74be5ae2289a6fbba5fabf2c3de354ae03c0b993c78c7de     21792  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/replay.py
21d575c2fd7ecdf29c94157078b4ab122c7bafe34b83fc9149468634a03c218a      2056  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/scoring.py
716b96494830440a5923b0be36e1d5d34a5e5c3ed530370ac4d873c7b93e17cd     13213  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/sessions.py
0261db5282875af6cc5a4f6c4d6eddd6924fae917629cc8df79543165fe73473     29081  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/setlist.py
03eaac8343eb7019a4d5afb6afc9e8b21313038992945812feffff3d8d4fbbb1      4942  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/setlistfm.py
a95b093568a0f878a0f535a325a84bf5c7944a1aeb71f156a225c97df7e10284      5660  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/show_unit.py
3dd61ba6d3c4619c4079274f479aaa63d17c466516a6774f0de8e8720d833dfc     26419  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/siblings.py
5e112a5e27870a0a9c78da4a730ed23deb623297bbb73da889be008f603ee932      3337  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/songs.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855         0  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/__init__.py
5e9ec06ac09feb76f921a9719ed7a4292aa9c2994b24088b9ca45dd1217926bf     17944  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/brief.py
985834c838112fac6128af761e59a06d6f8193bfb43b27694d98635f298e6b4b      1636  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/discover.py
a23c31944bd9d886a5d1a8ae52861887fa9b6af4d4a9e8a0434b98cb324803c7     85336  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/gather.py
28710555513c29485cb4d9a671d0247c5c83073424a1847a48e6b448b72a8abd       633  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/interpret.py
9ccfbe8e9f0f392efc688cddda1d187c693408de60773a71ba77cf31c7eedd74      4863  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/package.py
402682e6e36eba67335bab0c83538a475702f13a72d1cf3909921d2f205dd0d2      1053  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/research.py
fef3ae7a34da6b361d14871ce44b1ec180550d564f3b1d677e2f0c4b49670af9      2403  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/search.py
6bb91167be35b5ad3e92384de3801d12c64f25c8585689a5f78035eb67c23f35      4479  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/select_recording.py
ec53ee4224afdfecb5990cd503a37a69d3e0fdf04d69111bf3744c173d5cb5fd     15172  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/vet_research.py
6963d3d085b97130a888337c7773b3cb25063588a67f7c6949a4b252a406bf21      7348  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/stages/winnow.py
cd182f74c49a4ec1b3dfcad7fbb6e02dc60f76d72c9ea5802f695a1fc5eaa19e      4847  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/status.py
ee25e70164d391435ccea40d3c038d80484b34ead43a22718a86647d7e5f3fd2     74781  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/structure.py
826e58b42b5209504f1431a620d1868b00676bb73d3736fca9a59396788331c0     27092  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/taper.py
fd90e1882529d0fbe513dd42cbd17e388c92029730bd0c3f9a837a441f5438a4     28964  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/titles.py
202d41232f222a7a6f78c8ffb3756b5fd803a5ef8ede5215a84b26ff45c04db3      3968  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/util.py
8b829d9c0e15069cc167472c5230f92d8be43e50691207f85fb1839860c300cf      4964  orch/t12-rev/c_3d1c1e7/packages/llama/src/llama/workspace.py
```

</details>

<details><summary><code>evidence/orch/t12-rev/c_67291bd/</code>: 62 files</summary>

```
904b602ee93f132eba8b8c8c0137539a411bdd4363bee696d97336f9aae83347       539  orch/t12-rev/c_67291bd/packages/llama/src/llama/__init__.py
36966479a214299cd056823afc51f8bc291b1f4409399f37e723caf17446dd1f       138  orch/t12-rev/c_67291bd/packages/llama/src/llama/__main__.py
c1a20620f1b85a127ecbc20af030c2fac0ee80f23b468b3d5a806627766c7851      7135  orch/t12-rev/c_67291bd/packages/llama/src/llama/artist_index.py
cf6f5b63cf463ece0ca85b7f3ef4f922b11db4cd0566567e10542ee53dbb73c1      1317  orch/t12-rev/c_67291bd/packages/llama/src/llama/audio.py
63547dbc6889eeb2e581689e94d12324c4162e4758da2b97551a3199ba94f346     15445  orch/t12-rev/c_67291bd/packages/llama/src/llama/catalog.py
01c38fc28089e3ec4a9c5d33cacf985e81c5aa8a6dbae6ef9002d1664c6c98d6    209603  orch/t12-rev/c_67291bd/packages/llama/src/llama/cli.py
1b4104b6dde1615cbc3ae8108c2c592b5afcd7d0c9f5b71ccef687ae9e1b2d0a      3104  orch/t12-rev/c_67291bd/packages/llama/src/llama/cli_select.py
e4a6e73d53fcae0e2299f9e2f8c0e8a6fba812fc4423800b9b258985a2db4d66     11868  orch/t12-rev/c_67291bd/packages/llama/src/llama/config.py
bd92abe317d529db0dd15e66e0f8eb63726bb6e44332d3b7562062e0a6ce831b     16888  orch/t12-rev/c_67291bd/packages/llama/src/llama/correspondence.py
64d4041648335e86a829562155cde0481ab28a152da03f563e636a679f713875      1451  orch/t12-rev/c_67291bd/packages/llama/src/llama/data/README.md
174ae16ad1c6b425fd8693bb85ad7b39e877a9f1c29e989773efe9d39b604cf9        63  orch/t12-rev/c_67291bd/packages/llama/src/llama/data/__init__.py
542b9531c255cdee9b027dd304e40adbb88102d24d4be098c0973732cd98d9dd      2653  orch/t12-rev/c_67291bd/packages/llama/src/llama/download_slots.py
bf066f51994ef376882d6cae19a124de337012dca1ed0a86a1f3ff1b1dfbaaa1      1163  orch/t12-rev/c_67291bd/packages/llama/src/llama/errors.py
ec68ac9560ddacdaae566698c133569ef3f2dd6cc82296b9267a92cc3f19c019      5192  orch/t12-rev/c_67291bd/packages/llama/src/llama/grouping.py
cbfa0383f8c45aef8d43c062364763a17fddc2dfefa3306832bad5300c8808a6     20097  orch/t12-rev/c_67291bd/packages/llama/src/llama/ia_client.py
1453941b8ca2f77f7e5993055193217a0d2f1b0f8ae37c43d4f4cad69166a41c     16101  orch/t12-rev/c_67291bd/packages/llama/src/llama/jerrybase.py
66fa15048a54a78ad53b9f480d4c034d5ac141751af972c33bdba918f964ce24     14314  orch/t12-rev/c_67291bd/packages/llama/src/llama/junk.py
0e8fe3b1a462108d3d3e690abce76760ea658a93e68520b0b95d0df2967dffb4      2628  orch/t12-rev/c_67291bd/packages/llama/src/llama/ledger.py
712eb2cdf68b5c154b455302474b0dfbc6b978481d680b19edfc3b09658d2dc3      3957  orch/t12-rev/c_67291bd/packages/llama/src/llama/locks.py
eaf13625bd8e68a1909a4ea50fe1ac92fbef3edb73ed79aec418088a171b3539      1361  orch/t12-rev/c_67291bd/packages/llama/src/llama/manifest.py
042957174d12b12046b245afc80fe47b47a3e0a5c3e9ea29bd5471f2a188cabb     17827  orch/t12-rev/c_67291bd/packages/llama/src/llama/models.py
780837e4dd3a02c90effa2b018002de0a8267d3d1c9534dbb13570ca49df78c4     13290  orch/t12-rev/c_67291bd/packages/llama/src/llama/pacing.py
79bb3c04c086313377287a6ccd5e41b267025ac524a04e85e474187d17f131e5      5387  orch/t12-rev/c_67291bd/packages/llama/src/llama/pacing_state.py
4ee853edbc5c47f4ef431d7eaf66724e2f4cef0263afc65ced7217de2c092a84      7500  orch/t12-rev/c_67291bd/packages/llama/src/llama/pipeline.py
89a415fddb1090ffbfa7f43426d4e87276c1a89136279e13305471cb28b7eda9      7624  orch/t12-rev/c_67291bd/packages/llama/src/llama/placeholders.py
ce676c1a7bfc1c4b7b4febc883fc66c4a31d958f7544fd4a3eadc0c52faa0a4a      1928  orch/t12-rev/c_67291bd/packages/llama/src/llama/profiles.py
ad6b616496ec5967e27edb823006223fc46b48587a6c381d850f836478d6717d       148  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/__init__.py
73fa79383436f0075af2255ba1ccd94fc37fd3d598d06607d4bb688d69fdcb8c      1091  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/align_structure.md
0745db187c77b5234367508e89e1ab4ad5fe3ba60124372aed43051f5a906fde      2009  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/brief.md
e20d4394b052e157fa2e63dd66acf919392c85c90369c734ef670c33851775f5      1154  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/deep_research.md
ed1aea4983eef7a3607843a45d49dd050e6ee6ff8c7e350aee92501a9be928f1       801  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/extract_setlist.md
fd3c66183825f2dcc4c5049ef1194b9bbce44f5b69e40091d04d7092645adce5      1029  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/find_artists.md
84184a1ffd5d35c2d9697a97cde43291acfb66a07c4c744f984deb48690c7401      2442  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/interpret.md
82fe78aefc4508f7379cec7b5eb673ee820cda9889cd6b5c051162d1ea3b0059       595  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/light_research.md
783740367e988fc0afb525e1d3b8bdc1aac5fd7fdfabb1742e3f30cecc50fb97      1238  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/score_reviews.md
a079ab03053f566e8c6d3d19f1bbafea642b275058ad1aa320a76a9e19fbd89b      1566  orch/t12-rev/c_67291bd/packages/llama/src/llama/prompts/vet_research.md
f7a178416a7a3964bea859bb936482c1538a18a317aeecec0ecc725329ac2ee2     12639  orch/t12-rev/c_67291bd/packages/llama/src/llama/reapply.py
cb05723d6c9fab2aa74be5ae2289a6fbba5fabf2c3de354ae03c0b993c78c7de     21792  orch/t12-rev/c_67291bd/packages/llama/src/llama/replay.py
21d575c2fd7ecdf29c94157078b4ab122c7bafe34b83fc9149468634a03c218a      2056  orch/t12-rev/c_67291bd/packages/llama/src/llama/scoring.py
716b96494830440a5923b0be36e1d5d34a5e5c3ed530370ac4d873c7b93e17cd     13213  orch/t12-rev/c_67291bd/packages/llama/src/llama/sessions.py
0261db5282875af6cc5a4f6c4d6eddd6924fae917629cc8df79543165fe73473     29081  orch/t12-rev/c_67291bd/packages/llama/src/llama/setlist.py
03eaac8343eb7019a4d5afb6afc9e8b21313038992945812feffff3d8d4fbbb1      4942  orch/t12-rev/c_67291bd/packages/llama/src/llama/setlistfm.py
a95b093568a0f878a0f535a325a84bf5c7944a1aeb71f156a225c97df7e10284      5660  orch/t12-rev/c_67291bd/packages/llama/src/llama/show_unit.py
3dd61ba6d3c4619c4079274f479aaa63d17c466516a6774f0de8e8720d833dfc     26419  orch/t12-rev/c_67291bd/packages/llama/src/llama/siblings.py
5e112a5e27870a0a9c78da4a730ed23deb623297bbb73da889be008f603ee932      3337  orch/t12-rev/c_67291bd/packages/llama/src/llama/songs.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855         0  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/__init__.py
5e9ec06ac09feb76f921a9719ed7a4292aa9c2994b24088b9ca45dd1217926bf     17944  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/brief.py
985834c838112fac6128af761e59a06d6f8193bfb43b27694d98635f298e6b4b      1636  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/discover.py
a23c31944bd9d886a5d1a8ae52861887fa9b6af4d4a9e8a0434b98cb324803c7     85336  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/gather.py
28710555513c29485cb4d9a671d0247c5c83073424a1847a48e6b448b72a8abd       633  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/interpret.py
9ccfbe8e9f0f392efc688cddda1d187c693408de60773a71ba77cf31c7eedd74      4863  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/package.py
402682e6e36eba67335bab0c83538a475702f13a72d1cf3909921d2f205dd0d2      1053  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/research.py
fef3ae7a34da6b361d14871ce44b1ec180550d564f3b1d677e2f0c4b49670af9      2403  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/search.py
6bb91167be35b5ad3e92384de3801d12c64f25c8585689a5f78035eb67c23f35      4479  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/select_recording.py
ec53ee4224afdfecb5990cd503a37a69d3e0fdf04d69111bf3744c173d5cb5fd     15172  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/vet_research.py
6963d3d085b97130a888337c7773b3cb25063588a67f7c6949a4b252a406bf21      7348  orch/t12-rev/c_67291bd/packages/llama/src/llama/stages/winnow.py
cd182f74c49a4ec1b3dfcad7fbb6e02dc60f76d72c9ea5802f695a1fc5eaa19e      4847  orch/t12-rev/c_67291bd/packages/llama/src/llama/status.py
ee25e70164d391435ccea40d3c038d80484b34ead43a22718a86647d7e5f3fd2     74781  orch/t12-rev/c_67291bd/packages/llama/src/llama/structure.py
5033b0e65183a878b4da60c53223cfa402246c8a96aa25eecd390565272056b6     23248  orch/t12-rev/c_67291bd/packages/llama/src/llama/taper.py
fd90e1882529d0fbe513dd42cbd17e388c92029730bd0c3f9a837a441f5438a4     28964  orch/t12-rev/c_67291bd/packages/llama/src/llama/titles.py
202d41232f222a7a6f78c8ffb3756b5fd803a5ef8ede5215a84b26ff45c04db3      3968  orch/t12-rev/c_67291bd/packages/llama/src/llama/util.py
8b829d9c0e15069cc167472c5230f92d8be43e50691207f85fb1839860c300cf      4964  orch/t12-rev/c_67291bd/packages/llama/src/llama/workspace.py
```

</details>

<details><summary><code>evidence/orch/cpa2-tiers/versions/</code>: 8 files</summary>

```
1c2c22c25ad3fcea6c33b53448443532216328aebffca28ce5194579e9ea5911     30257  orch/cpa2-tiers/versions/taper_025e713.py
cc9e2fe799448cefcf6d5bc57a9f22a76acd1682a8924fd0f1a4c3cbac03a112     32439  orch/cpa2-tiers/versions/taper_2abad1e.py
05753919949dfcc4394d9eb4cfe6c59f6059a5b431baafb929caba76434bd7bf     31039  orch/cpa2-tiers/versions/taper_3758240.py
826e58b42b5209504f1431a620d1868b00676bb73d3736fca9a59396788331c0     27092  orch/cpa2-tiers/versions/taper_3d1c1e7.py
5033b0e65183a878b4da60c53223cfa402246c8a96aa25eecd390565272056b6     23248  orch/cpa2-tiers/versions/taper_5010a00.py
3079c936d041fe4e79d3365b200edd0a7d2a57c3cf87d86c4620f778612c7b45     33063  orch/cpa2-tiers/versions/taper_569b88c.py
6898b4f4a22baf81c027b675dd39029455e33f2653efb0a47cd1dc03b105e97d     26269  orch/cpa2-tiers/versions/taper_b503f24.py
bdbecf59cf1a9fe0d4f638c7147570a7726aa722cf1dd8529485f390a029a0c7     24318  orch/cpa2-tiers/versions/taper_b643513.py
```

</details>

<details><summary><code>evidence/orch-r1/mut/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/mut/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/mut/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/mut/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/mut/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/mut/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/mut/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/mut/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/mut/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/mut/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/mut/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/mut/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/red/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/red/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/red/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/red/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/red/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/red/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/red/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/red/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/red/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/red/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/red/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/red/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/red2/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/red2/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/red2/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/red2/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/red2/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/red2/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/red2/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/red2/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/red2/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/red2/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/red2/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/red2/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_A/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_A/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_A/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_A/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_A/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_A/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_A/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_A/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_A/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_A/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_A/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_A/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_B/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_B/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_B/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_B/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_B/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_B/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_B/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_B/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_B/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_B/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_B/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_B/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_base0/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_base0/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_base0/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_base0/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_base0/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_base0/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_base0/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_base0/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_base0/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_base0/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_base0/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_base0/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_C/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_C/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_C/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_C/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_C/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_C/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_C/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_C/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_C/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_C/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_C/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_C/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_D/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_D/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_D/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_D/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_D/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_D/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_D/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_D/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_D/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_D/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_D/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_D/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_F/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_F/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_F/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_F/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_F/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_F/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_F/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_F/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_F/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_F/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_F/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_F/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_G/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_G/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_G/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_G/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_G/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_G/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_G/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_G/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_G/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_G/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_G/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_G/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_I/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_I/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_I/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_I/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_I/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_I/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_I/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_I/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_I/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_I/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_I/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_I/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t6-rev/m_J/</code>: 11 files</summary>

```
e8a7e36d141a17b98f30ec3e516dca40f5ca4f5e342ba42957546a13c78a64a1      9098  orch-r1/t6-rev/m_J/.github/workflows/release.yml
860a4538d898525bb15b97b51c9ab41df1f543295a62ce3e201869c6bf83982f       411  orch-r1/t6-rev/m_J/.gitignore
5a4bfabd3895dd42ecbc0706ff07e750aeb87f60c0488ab632463cb9060b4032     83589  orch-r1/t6-rev/m_J/CLAUDE.md
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986     35149  orch-r1/t6-rev/m_J/LICENSE
5d4631115c522b1d0e3f1eb54d1b73a72428966e6e271c0543277c9d7148fe92     44352  orch-r1/t6-rev/m_J/README.md
ccc72889a820f752679e429d8daf3c8f68b2c19ea5d9e4c742f9cc7c6a339bad     17101  orch-r1/t6-rev/m_J/packaging/build.py
648fbc8745d4f5c3608502dcb3c190173c388efb76df89e10c6633443658bc6d      3960  orch-r1/t6-rev/m_J/packaging/emcee.spec
e13dc0dab6e2285a88b5f36b20170ed28e42431cbf52d386a9bc832a97d5aa25       661  orch-r1/t6-rev/m_J/packaging/llama.entitlements
3a4eabca178e2d879f8c4aabd8998e96cfdb5129b75b6365fdf7cfa4cf6a4b95      3797  orch-r1/t6-rev/m_J/packaging/llama.spec
81d63c421e1c0a892d94f938bcabfe2d3fdd84ffdb9b40dac08d6428dc59cdba       231  orch-r1/t6-rev/m_J/packaging/metadata.json
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t6-rev/m_J/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/t4-fix1/M0/</code>: 1 files</summary>

```
3d3611b6b9cd4e06d0064e2ea8d0c01459929694f786b44507e08db628815d8c       220  orch-r1/t4-fix1/M0/pytest.ini
```

</details>

<details><summary><code>evidence/orch-r1/cpa3-r*</code>: 2 files</summary>

```
f8d319bde735ffdc5e6b8157ede4bd826b6f79391beb3e90d9c994b07bbbb00e     37889  orch-r1/cpa3-rev/taper.orig
ba90a649106252e753a363e8e840cedb8c5b0bc4f3ec5f21d9d4f474c5e51335     38694  orch-r1/cpa3-rr1/taper.orig
```

</details>

<details><summary><code>evidence/orch-r1/</code>: 6 files</summary>

```
469ac31b10712111b1af2ca6ceee915987d944ac036bacec9ba2ca739af2fd5b     89905  orch-r1/gather.full.py
a23c31944bd9d886a5d1a8ae52861887fa9b6af4d4a9e8a0434b98cb324803c7     85336  orch-r1/gather.head.py
afeefd510b37e9a28011802429bc831c88036aaf964114bc950535d33d69041b    172926  orch-r1/test.head.py
a68eb228ecda5626e61417775ff71416d03201e786b63c66936c424a5adda05b    191735  orch-r1/test_stage_gather.full.py
133552c66efd0f834fea7c1ca92777e0f8d1760ea64ce1cd0c955a535f61034e       643  orch-r1/tests_head.py
f4be20068795ecd633496bbd788ec0c5564b506d375e8aee6abbe44c80cb6fab      6638  orch-r1/tests_tail.py
```

</details>
