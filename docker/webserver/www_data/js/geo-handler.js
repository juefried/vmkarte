const params = new URLSearchParams(window.location.search);
const value = params.get('l') || '';
const matches = /^geo:([0-9.-]+),([0-9.-]+)$/.exec(value);
const message = document.getElementById('message');

if (matches) {
	const lat = matches[1];
	const lon = matches[2];
	window.location.replace(
		'https://brouter.de/brouter-web/#map=7/50/11/standard&profile=vm-forum-velomobil-schnell&lonlats='
		+ encodeURIComponent(lon) + ',' + encodeURIComponent(lat),
	);
}
else if (message) {
	message.textContent = 'Ungültiger geo:-Link.';
}
