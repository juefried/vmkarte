const container = document.getElementById('legal_links');

function hideLegalLinks() {
	if (!container)
		return;
	container.hidden = true;
	for (const link of container.querySelectorAll('[data-legal]'))
		link.hidden = true;
}

function refreshLegalLinks() {
	if (!container)
		return;
	if (!navigator.onLine) {
		hideLegalLinks();
		return;
	}

	fetch('/legal-status', { cache: 'no-store', credentials: 'same-origin' })
		.then(response => response.ok ? response.json() : null)
		.then(status => {
			if (!status) {
				hideLegalLinks();
				return;
			}

			let visible = false;
			for (const [key, selector] of [
				['privacy', '[data-legal="privacy"]'],
				['imprint', '[data-legal="imprint"]'],
			]) {
				const link = container.querySelector(selector);
				const available = link && Boolean(status[key]);
				if (link)
					link.hidden = !available;
				if (available)
					visible = true;
			}
			container.hidden = !visible;
		})
		.catch(hideLegalLinks);
}

refreshLegalLinks();
window.addEventListener('online', refreshLegalLinks);
window.addEventListener('offline', hideLegalLinks);
