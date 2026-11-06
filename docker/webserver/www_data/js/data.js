export const STALE_AFTER_MS = 48 * 60 * 60 * 1000;

export function parseDataStatus(raw) {
	if (!raw || typeof raw !== 'object' || Array.isArray(raw))
		return null;

	const { generatedAt, runStartedAt, memberCount } = raw;
	if (typeof generatedAt !== 'string' || Number.isNaN(Date.parse(generatedAt)))
		return null;
	if (!Number.isInteger(memberCount) || memberCount < 0)
		return null;
	if (runStartedAt != null
		&& (typeof runStartedAt !== 'string' || Number.isNaN(Date.parse(runStartedAt))))
		return null;

	return {
		generatedAt,
		runStartedAt: runStartedAt ?? null,
		memberCount,
	};
}

export function validateMembers(raw) {
	if (!Array.isArray(raw))
		return null;

	const members = [];
	let skipped = 0;

	for (const member of raw) {
		if (!member || typeof member !== 'object'
			|| (typeof member.id !== 'string' && typeof member.id !== 'number')
			|| typeof member.name !== 'string' || member.name.length === 0
			|| member.lat === null || member.lat === ''
			|| member.lon === null || member.lon === '') {
			skipped += 1;
			continue;
		}

		const lat = Number(member.lat);
		const lon = Number(member.lon);
		if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
			skipped += 1;
			continue;
		}

		members.push(member);
	}

	if (members.length === 0)
		return null;

	return { members, skipped };
}

export function isServerNewer(serverStatus, localStatus) {
	if (!serverStatus || !serverStatus.generatedAt)
		return false;
	if (!localStatus || !localStatus.generatedAt)
		return true;

	const serverTime = Date.parse(serverStatus.generatedAt);
	const localTime = Date.parse(localStatus.generatedAt);
	if (Number.isNaN(serverTime) || Number.isNaN(localTime))
		return true;

	return serverTime > localTime;
}

export function formatStatusTimestamp(iso) {
	const date = new Date(iso);
	if (Number.isNaN(date.getTime()))
		return 'unbekannt';

	return new Intl.DateTimeFormat('de-DE', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
	}).format(date);
}

export function isStale(generatedAt, now = Date.now()) {
	if (!generatedAt)
		return false;

	const time = Date.parse(generatedAt);
	if (Number.isNaN(time))
		return false;

	return now - time > STALE_AFTER_MS;
}

export function deriveStatusFromLastModified(lastModified, memberCount) {
	const date = new Date(lastModified);
	if (Number.isNaN(date.getTime()))
		return null;

	return {
		generatedAt: date.toISOString(),
		runStartedAt: null,
		memberCount,
	};
}

export function formatStatusText({ generatedAt, source, updateFailed, stale } = {}) {
	const timestamp = generatedAt ? formatStatusTimestamp(generatedAt) : 'unbekannt';
	const sourceLabel = source === 'server' ? 'Server' : 'lokal';

	let text = `Datenstand: ${timestamp} · ${sourceLabel}`;
	if (updateFailed)
		text += ' (Aktualisierung fehlgeschlagen)';
	if (stale)
		text += ' · älter als 48 h';

	return text;
}
