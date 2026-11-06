export const DEV_MODE_KEY = 'vmkarte-dev-mode';

export function parseAppVersion(value) {
	if (!value || typeof value !== 'object')
		return null;

	const version = typeof value.version === 'string' ? value.version.trim() : '';
	if (!version)
		return null;

	const buildDate = typeof value.buildDate === 'string' && value.buildDate.trim()
		? value.buildDate.trim()
		: null;

	return { version, buildDate };
}

export function isNewVersion(currentVersion, remoteVersion) {
	if (typeof currentVersion !== 'string' || typeof remoteVersion !== 'string')
		return false;
	if (!currentVersion || !remoteVersion)
		return false;
	return currentVersion !== remoteVersion;
}

export function resolveDevMode(search, stored) {
	const params = new URLSearchParams(search || '');
	const flag = params.get('dev');

	if (flag === '1')
		return { enabled: true, persist: true, clear: false };
	if (flag === '0')
		return { enabled: false, persist: false, clear: true };

	return {
		enabled: stored === '1',
		persist: false,
		clear: false,
	};
}
