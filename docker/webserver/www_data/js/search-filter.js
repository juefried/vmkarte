export const SEARCH_MODE_HASHTAG_INDEX = 7;
export const SEARCH_MODE_EVERYWHERE_INDEX = 8;

const FILTER_FIELDS = ['name', 'vm', 'lr', 'tr', 'other'];
const SEARCH_BIT = 2 ** 5;

export function resolveSearchMode(value, currentIndex) {
	if (typeof value !== 'string' || value.length === 0)
		return currentIndex;
	return value.startsWith('#')
		? SEARCH_MODE_HASHTAG_INDEX
		: SEARCH_MODE_EVERYWHERE_INDEX;
}

function buildUrlMatchers(urlParams) {
	if (!urlParams)
		return [];
	return FILTER_FIELDS
		.filter(name => urlParams.has(name))
		.map(name => ({ name, regex: new RegExp(urlParams.get(name), 'i') }));
}

function matchesUrlFilters(member, urlMatchers) {
	return urlMatchers.every(({ name, regex }) => member[name] && member[name].match(regex));
}

export function filterMembers(members, { urlParams = null, mode = 1, query = '' } = {}) {
	const urlMatchers = buildUrlMatchers(urlParams);
	const searchRegex = (mode & SEARCH_BIT) ? new RegExp(query, 'i') : null;

	return (Array.isArray(members) ? members : []).filter(member =>
		matchesUrlFilters(member, urlMatchers)
		&& FILTER_FIELDS.some((name, index) =>
			(mode & 2 ** index)
			&& member[name]
			&& (searchRegex ? member[name].match(searchRegex) : true)
		)
	);
}
