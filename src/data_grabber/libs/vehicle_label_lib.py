import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

VEHICLE_FIELDS = ('vm', 'lr', 'tr')
DEFAULT_MAP_PATH = Path(__file__).with_name('vehicle_label_map.json')
TOKEN_PATTERN = re.compile(r'[^\W_]+', re.UNICODE)


def normalize_label(value):
    text = str(value).casefold()
    text = text.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    text = text.replace('&', ' amp ')
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(re.sub(r'[^0-9a-z]+', ' ', text).split())


def _tokenize(value):
    return TOKEN_PATTERN.findall(str(value))


def humanize_choice_value(value, token_casing=None):
    text = re.sub(r'[_\-\s]+', ' ', str(value)).strip()
    if not text:
        return ''

    words = []
    for word in text.split():
        key = word.casefold()
        casing = (token_casing or {}).get(key)
        if key == 'amp':
            words.append('&')
        elif casing:
            words.append(casing)
        elif word.isupper() and len(word) > 1:
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    return ' '.join(words)


def load_vehicle_label_map(path=None):
    map_path = Path(path) if path is not None else DEFAULT_MAP_PATH
    try:
        with map_path.open('r', encoding='utf-8') as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {field: {} for field in VEHICLE_FIELDS}

    if not isinstance(data, dict):
        return {field: {} for field in VEHICLE_FIELDS}
    return {
        field: dict(data.get(field) or {})
        for field in VEHICLE_FIELDS
    }


class VehicleLabelResolver:
    def __init__(self, mapping=None):
        source = mapping or {}
        self.mapping = {
            field: dict(source.get(field) or {})
            for field in VEHICLE_FIELDS
        }
        self._normalized_labels = {}
        self._token_matches = {}
        self._token_sets = {}
        self._token_casing = {}
        self._global_token_casing = {}
        self._build_indexes()

    def _build_indexes(self):
        global_counts = defaultdict(Counter)
        for field in VEHICLE_FIELDS:
            by_normalized = defaultdict(Counter)
            field_counts = defaultdict(Counter)

            for label in self.mapping[field].values():
                normalized = normalize_label(label)
                if normalized:
                    by_normalized[normalized][label] += 1
                for token in _tokenize(label):
                    key = token.casefold()
                    field_counts[key][token] += 1
                    global_counts[key][token] += 1

            self._normalized_labels[field] = {
                normalized: counts.most_common(1)[0][0]
                for normalized, counts in by_normalized.items()
            }
            by_tokens = defaultdict(Counter)
            for normalized, label in self._normalized_labels[field].items():
                tokens = tuple(sorted(normalized.split()))
                if tokens:
                    by_tokens[tokens][label] += 1
            self._token_matches[field] = {
                tokens: (
                    counts.most_common(1)[0][0]
                    if len(counts) == 1
                    else None
                )
                for tokens, counts in by_tokens.items()
            }
            self._token_sets[field] = sorted(
                (
                    (tuple(normalized.split()), label)
                    for normalized, label in self._normalized_labels[field].items()
                ),
                key=lambda item: (-len(item[0]), item[0]),
            )
            self._token_casing[field] = {
                key: counts.most_common(1)[0][0]
                for key, counts in field_counts.items()
            }

        self._global_token_casing = {
            key: counts.most_common(1)[0][0]
            for key, counts in global_counts.items()
        }

    def _casing_for(self, field):
        casing = dict(self._global_token_casing)
        casing.update(self._token_casing.get(field, {}))
        return casing

    def is_known(self, field, value):
        return str(value).strip() in self.mapping.get(field, {})

    def resolve(self, field, value):
        raw = str(value).strip()
        if not raw:
            return '', 1.0, 'empty'
        if field not in VEHICLE_FIELDS:
            return raw, 1.0, 'passthrough'

        exact = self.mapping[field].get(raw)
        if exact:
            return exact, 1.0, 'exact'

        normalized = normalize_label(raw)
        normalized_match = self._normalized_labels[field].get(normalized)
        if normalized_match:
            return normalized_match, 0.95, 'normalized'

        raw_tokens = tuple(normalized.split())
        if raw_tokens:
            token_match = self._token_matches[field].get(tuple(sorted(raw_tokens)))
            if token_match:
                return token_match, 0.92, 'tokens'

        raw_counts = Counter(raw_tokens)
        extension = None
        extension_length = 0
        extension_ambiguous = False

        for candidate_tokens, label in self._token_sets[field]:
            candidate_counts = Counter(candidate_tokens)
            if not candidate_counts or candidate_counts == raw_counts:
                continue
            if any(count > raw_counts[token] for token, count in candidate_counts.items()):
                continue
            length = sum(candidate_counts.values())
            if length > extension_length:
                extension = (candidate_tokens, label)
                extension_length = length
                extension_ambiguous = False
            elif length == extension_length:
                if extension is None or label != extension[1]:
                    extension_ambiguous = True

        if extension and not extension_ambiguous:
            candidate_tokens, label = extension
            remaining = list(raw_tokens)
            for token in candidate_tokens:
                if token in remaining:
                    remaining.remove(token)
            extra = humanize_choice_value(' '.join(remaining), self._casing_for(field))
            return f'{label} {extra}'.strip(), 0.9, 'extension'

        if ' ' in raw or raw != raw.casefold():
            return raw, 0.9, 'display'

        return humanize_choice_value(raw, self._casing_for(field)), 0.35, 'humanized'
