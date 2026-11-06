import { HASHTAG_REGEX } from './hashtags.js';

const SEARCH_FIELDS = ['name', 'vm', 'lr', 'tr'];

// Collect possible search terms from all fields that the search can match.
// Values are deduplicated case-insensitively and ordered by frequency, so
// common vehicles and hashtags appear first.
export function collectSearchSuggestions(members) {
	const suggestions = new Map();

	const add = (value, lowerCase = false) => {
		if (typeof value !== 'string')
			return;

		const trimmed = value.trim();
		if (!trimmed)
			return;

		const display = lowerCase ? trimmed.toLocaleLowerCase('de') : trimmed;
		const key = display.toLocaleLowerCase('de');
		const existing = suggestions.get(key);
		if (existing)
			existing.count++;
		else
			suggestions.set(key, { value: display, count: 1 });
	};

	for (const member of Array.isArray(members) ? members : []) {
		if (!member)
			continue;

		for (const field of SEARCH_FIELDS)
			add(member[field]);

		if (typeof member.other === 'string')
			for (const tag of member.other.match(HASHTAG_REGEX) ?? [])
				add(tag, true);
	}

	return Array.from(suggestions.values())
		.sort((a, b) => b.count - a.count
			|| a.value.localeCompare(b.value, 'de', { sensitivity: 'base' }))
		.map(entry => entry.value);
}

export function filterSearchSuggestions(suggestions, query) {
	const values = (Array.isArray(suggestions) ? suggestions : [])
		.filter(value => typeof value === 'string');
	const normalizedQuery = typeof query === 'string'
		? query.trim().toLocaleLowerCase('de')
		: '';

	if (!normalizedQuery)
		return values.filter(value => value.startsWith('#'));

	return values.filter(value => value.toLocaleLowerCase('de').includes(normalizedQuery));
}
