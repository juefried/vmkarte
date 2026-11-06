import { formatStatusText, formatStatusTimestamp, isStale } from './data.js';

export function createStatusUi({ statusElement, messageElement, offlineElement }) {
	let statusTimer = null;
	let messageTimer = null;
	let retryButton = null;

	function hideStatus() {
		if (statusElement)
			statusElement.hidden = true;
	}

	function setStatus({ generatedAt, runStartedAt, source, updateFailed = false, stale = null, offline = false }) {
		if (!statusElement)
			return;

		clearTimeout(statusTimer);
		statusTimer = null;

		const isOld = stale ?? isStale(generatedAt);
		statusElement.hidden = false;
		statusElement.textContent = formatStatusText({
			generatedAt,
			source,
			updateFailed,
			stale: isOld,
			offline,
		});
		statusElement.classList.toggle('status-server', source === 'server');
		statusElement.classList.toggle('status-local', source !== 'server');
		statusElement.classList.toggle('status-warning', isOld || updateFailed);

		const titleParts = [];
		if (runStartedAt)
			titleParts.push(`Laufbeginn: ${formatStatusTimestamp(runStartedAt)}`);
		if (updateFailed)
			titleParts.push('Serverabgleich fehlgeschlagen');
		if (offline)
			titleParts.push('Gerät ist offline');
		statusElement.title = titleParts.join('\n');

		const hideAfter = (isOld || updateFailed) ? 8000 : 6000;
		statusTimer = setTimeout(hideStatus, hideAfter);
	}

	function clearStatus() {
		clearTimeout(statusTimer);
		statusTimer = null;
		if (!statusElement)
			return;

		statusElement.hidden = true;
		statusElement.textContent = '';
		statusElement.title = '';
		statusElement.classList.remove('status-server', 'status-local', 'status-warning');
	}

	function setOffline(offline) {
		if (offlineElement)
			offlineElement.hidden = !offline;
	}

	function setMessage({ type = 'info', text = '', onRetry = null, actionLabel = 'Erneut versuchen', autoHideMs = null } = {}) {
		if (!messageElement)
			return;

		clearTimeout(messageTimer);
		messageTimer = null;
		messageElement.hidden = false;
		messageElement.textContent = '';
		messageElement.className = `data-message data-message-${type}`;
		messageElement.appendChild(document.createTextNode(text));

		if (onRetry) {
			retryButton = document.createElement('button');
			retryButton.type = 'button';
			retryButton.textContent = actionLabel;
			retryButton.addEventListener('click', onRetry);
			messageElement.appendChild(retryButton);
		}

		const closeButton = document.createElement('button');
		closeButton.type = 'button';
		closeButton.className = 'message-close';
		closeButton.textContent = '×';
		closeButton.title = 'Meldung schließen';
		closeButton.setAttribute('aria-label', 'Meldung schließen');
		closeButton.addEventListener('click', clearMessage);
		messageElement.appendChild(closeButton);

		const hideAfter = autoHideMs ?? (type === 'success' ? 3000 : (type === 'loading' ? 0 : 8000));
		if (hideAfter)
			messageTimer = setTimeout(clearMessage, hideAfter);
	}

	function clearMessage() {
		clearTimeout(messageTimer);
		messageTimer = null;
		if (!messageElement)
			return;

		messageElement.hidden = true;
		messageElement.textContent = '';
		retryButton = null;
	}

	return { setStatus, clearStatus, setOffline, setMessage, clearMessage };
}
