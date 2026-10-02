# VocaCurve language packs

Offline dictionaries for the [VocaCurve](https://github.com/montaeg0920-lang/wordmemory) flashcard app.
The app downloads **only the pack of the language a learner studies**, stores it in the browser,
and fills in meanings, pronunciation, part of speech and examples without any AI service or API key.

| Pack | Words | With Korean meaning | Size (raw / gzip) |
|---|---|---|---|
| `en` English → Korean | 20,000 | 14,447 (72%) | 1.28 MB / 0.56 MB |

`manifest.json` lists every pack with its version, size and SHA-256.
The app reads it from `@main` and downloads the pack file from the git tag in `ref`.

## Pack format (`packs/<lang>.tsv`)

UTF-8, tab-separated, one word per line. The first line is a header starting with `#vocacurve-langpack`.

| Column | Example |
|---|---|
| term | `derive` |
| meanings (Korean, best first, ` \| ` separated) | `유래하다` |
| ipa | `/dɝˈaɪv/` |
| pos (Korean) | `동사` |
| example (source language) | `Derive pleasure from one's garden` |

## Building

```sh
pip install nltk
python3 scripts/build_en.py --version 2026.10.1
```

Sources are downloaded into `.cache/` on the first run. After rebuilding, commit, create a new tag
(e.g. `v2`) and set `ref` in `manifest.json` to it so apps pick up the update.

## Sources and licenses

The packs are derived from the data below and are distributed under the same terms
(**CC BY-SA**: share alike, attribution required). Code in `scripts/` is MIT.

| Data | Used for | License |
|---|---|---|
| [kengdic](https://github.com/garfieldnate/kengdic) (Joe Speigle et al.) | Korean meanings (Korean→English entries, reversed) | CC BY-SA 3.0 / LGPL-2.0 |
| [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (OpenSubtitles 2018) | Word selection and meaning ranking | CC BY-SA 4.0 |
| [ipa-dict](https://github.com/open-dict-data/ipa-dict) | Pronunciation (IPA, US) | MIT |
| [Princeton WordNet 3.0](https://wordnet.princeton.edu/) | Part of speech, English examples | WordNet License |

Meanings are chosen automatically and can be wrong for some words; the app always lets the learner
review and edit before saving. Corrections are welcome.
