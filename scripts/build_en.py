#!/usr/bin/env python3
"""
Builds the English -> Korean language pack (packs/en.tsv) for VocaCurve.

Sources (downloaded into .cache/ on first run):
  - Word lists in frequency order (English headwords; Korean, to rank meanings):
      FrequencyWords, OpenSubtitles 2018 (CC BY-SA 4.0)  https://github.com/hermitdave/FrequencyWords
  - Korean meanings: kengdic Korean-English dictionary, reversed (CC BY-SA 3.0 / LGPL-2.0)
      https://github.com/garfieldnate/kengdic
  - Pronunciation (IPA, US): ipa-dict (MIT)
      https://github.com/open-dict-data/ipa-dict
  - Part of speech and English examples: Princeton WordNet 3.0 (WordNet License), via NLTK data
      https://wordnet.princeton.edu/

Usage:  pip install nltk && python3 scripts/build_en.py [--size 20000]
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, '.cache')
SOURCES = {
    'freq': 'https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/en/en_50k.txt',
    'freq_ko': 'https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ko/ko_50k.txt',
    'kengdic': 'https://raw.githubusercontent.com/garfieldnate/kengdic/master/kengdic.tsv',
    'ipa': 'https://raw.githubusercontent.com/open-dict-data/ipa-dict/master/data/en_US.txt',
    'wordnet': 'https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip',
}
POS_KO = {'n': '명사', 'v': '동사', 'a': '형용사', 's': '형용사', 'r': '부사'}
HANGUL = re.compile(r'[가-힣]')
MAX_MEANINGS = 3
LEVEL_BONUS = {'A': 3.0, 'B': 2.0, 'C': 1.0, 'D': 0.5}  # kengdic learner levels: A = most basic


def fetch(name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, os.path.basename(SOURCES[name]))
    if not os.path.exists(path):
        print(f'downloading {name}...', file=sys.stderr)
        urllib.request.urlretrieve(SOURCES[name], path)
    return path


def load_wordnet():
    data_dir = os.path.join(CACHE, 'nltk_data')
    corpora = os.path.join(data_dir, 'corpora')
    if not os.path.exists(os.path.join(corpora, 'wordnet')):
        os.makedirs(corpora, exist_ok=True)
        with zipfile.ZipFile(fetch('wordnet')) as z:
            z.extractall(corpora)
    import nltk
    nltk.data.path.insert(0, data_dir)
    from nltk.corpus import wordnet as wn
    wn.ensure_loaded()
    return wn


def clean_gloss_part(part):
    part = re.sub(r'\([^)]*\)', ' ', part)
    part = re.sub(r'\s+', ' ', part).strip().lower().strip('.!?"\'')
    part = re.sub(r'^(to|a|an|the) ', '', part)
    return part


def clean_korean(surface):
    s = re.sub(r'\s+', ' ', surface).strip()
    s = re.sub(r'^(에|에서|을|를|이|가|의|와|과|로|으로) ', '', s)  # dangling particles ("에 유래하다")
    return s


def korean_frequency():
    """Korean word -> log10(count) in subtitles; used to prefer everyday meanings (물 over 근해)."""
    import math
    freq = {}
    with open(fetch('freq_ko'), encoding='utf-8') as f:
        for line in f:
            word, _, count = line.strip().rpartition(' ')
            if word and count.isdigit():
                freq.setdefault(word, math.log10(int(count)))
    return freq


def reverse_kengdic():
    """English word -> list of (score, korean) from the Korean->English dictionary."""
    index = collections.defaultdict(list)
    ko_freq = korean_frequency()
    with open(fetch('kengdic'), encoding='utf-8') as f:
        next(f)
        for line in f:
            cols = line.rstrip('\n').split('\t')
            if len(cols) < 4 or not cols[3].strip():
                continue
            korean = clean_korean(cols[1])
            if not HANGUL.search(korean) or re.search(r'[A-Za-z0-9]', korean) or len(korean) > 12 or korean.count(' ') > 1:
                continue
            gloss = cols[3]
            parts = [clean_gloss_part(p) for p in re.split(r'[;,/]', gloss)]
            parts = [p for p in parts if p]
            whole = clean_gloss_part(gloss)
            for i, p in enumerate(parts):
                if not re.fullmatch(r"[a-z][a-z' -]*", p):
                    continue
                score = 4.0 if p == whole else 2.5 - min(i, 2) * 0.5  # sole / first gloss = closest meaning
                score += 0.5 if cols[2].strip() else 0             # has hanja: usually a dictionary headword
                score -= 0.15 * max(0, len(korean) - 4)            # prefer short, word-like meanings
                score -= 0.8 * korean.count(' ')
                score += LEVEL_BONUS.get(cols[4].strip(), 0)
                if len(korean) >= 2:  # one-syllable words (정, 시, 적) are too ambiguous to trust their frequency
                    score += 0.7 * ko_freq.get(korean, 0)
                index[p].append((score, korean))
    return index


def best_meanings(cands):
    seen, out = set(), []
    for score, korean in sorted(cands, key=lambda c: -c[0]):
        key = korean.replace(' ', '')
        if key in seen:
            continue
        seen.add(key)
        out.append(korean)
        if len(out) == MAX_MEANINGS:
            break
    return out


def load_ipa():
    ipa = {}
    with open(fetch('ipa'), encoding='utf-8') as f:
        for line in f:
            word, _, prons = line.rstrip('\n').partition('\t')
            if word and prons and word not in ipa:
                ipa[word] = prons.split(',')[0].strip()
    return ipa


def main_pos(wn, word):
    weight = collections.Counter()
    for syn in wn.synsets(word):
        for lemma in syn.lemmas():
            if lemma.name().lower() == word:
                weight[syn.pos()] += lemma.count() + 1
    if not weight:
        return ''
    return POS_KO.get(weight.most_common(1)[0][0], '')


def example(wn, word):
    forms = re.compile(r'\b' + re.escape(word) + r'(s|es|ed|d|ing|er|est|ly)?\b', re.I)
    best = ''
    for syn in wn.synsets(word):
        for ex in syn.examples():
            ex = ex.strip()
            if forms.search(ex) and 15 <= len(ex) <= 100 and (not best or len(ex) < len(best)):
                best = ex
    return best[0].upper() + best[1:] if best else ''


def headwords(wn, size, has_meaning):
    out, seen = [], set()
    with open(fetch('freq'), encoding='utf-8') as f:
        for line in f:
            word = line.split(' ')[0].strip().lower()
            if not re.fullmatch(r'[a-z][a-z-]*[a-z]', word):
                continue
            base = word
            if not any(l.name().lower() == word for s in wn.synsets(word) for l in s.lemmas()):
                base = next((wn.morphy(word, p) for p in ('n', 'v', 'a', 'r') if wn.morphy(word, p)), None)
            if not base or base in seen or not (wn.synsets(base) or base in has_meaning):
                continue
            seen.add(base)
            out.append(base)
            if len(out) == size:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', type=int, default=20000)
    ap.add_argument('--version', default='')
    args = ap.parse_args()

    wn = load_wordnet()
    ko = reverse_kengdic()
    ipa = load_ipa()
    words = headwords(wn, args.size, ko)

    rows, with_meaning = [], 0
    for w in words:
        meanings = best_meanings(ko.get(w, []))
        if meanings:
            with_meaning += 1
        fields = [w, ' | '.join(meanings), ipa.get(w, ''), main_pos(wn, w), example(wn, w)]
        rows.append('\t'.join(f.replace('\t', ' ') for f in fields))

    header = '#vocacurve-langpack\ten\tko\tterm\tmeanings\tipa\tpos\texample'
    body = header + '\n' + '\n'.join(rows) + '\n'
    out = os.path.join(ROOT, 'packs', 'en.tsv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(body)

    data = body.encode('utf-8')
    manifest_path = os.path.join(ROOT, 'manifest.json')
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {'format': 1, 'packs': {}}
    manifest['packs']['en'] = {
        'name': 'English',
        'version': args.version or manifest['packs'].get('en', {}).get('version', '1'),
        'file': 'packs/en.tsv',
        'entries': len(rows),
        'withMeaning': with_meaning,
        'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'sources': ['FrequencyWords (CC BY-SA 4.0)', 'kengdic (CC BY-SA 3.0 / LGPL-2.0)', 'ipa-dict (MIT)', 'Princeton WordNet 3.0 (WordNet License)'],
    }
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'{len(rows)} words, {with_meaning} with Korean meanings ({with_meaning * 100 // max(1, len(rows))}%), {len(data) / 1e6:.2f} MB', file=sys.stderr)


if __name__ == '__main__':
    main()
