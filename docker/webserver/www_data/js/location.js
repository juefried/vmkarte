export const GEOLOCATION_OPTIONS = Object.freeze({
	enableHighAccuracy: true,
	timeout: 10000,
	maximumAge: 0,
});

export function describeGeolocationError(error) {
	switch (error && error.code) {
		case 1:
			return 'Standortzugriff wurde verweigert. Bitte die Berechtigung im Browser erlauben.';
		case 2:
			return 'Der Standort ist derzeit nicht verfügbar. Bitte später erneut versuchen.';
		case 3:
			return 'Die Standortabfrage hat zu lange gedauert. Bitte erneut versuchen.';
		default:
			return 'Der Standort konnte nicht ermittelt werden.';
	}
}
