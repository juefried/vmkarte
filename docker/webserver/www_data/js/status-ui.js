import { formatStatusText, formatStatusTimestamp, isStale } from './data.js';

export function createStatusUi({ statusElement, messageElement }) {
	let retryButton = null;

	function setStatus({ generatedAt, runStartedAt, source, updateFailed = false, stale = null }) {
		if (!statusElement)
			return;

		const isOld = stale ?? isStale(generatedAt);
		statusElement.hidden = false;
		statusElement.textContent = formatStatusText({
			generatedAt,
			source,
			updateFailed,
			stale: isOld,
		});
		statusElement.classList.toggle('status-server', source === 'server');
		statusElement.classList.toggle('status-local', source !== 'server');
		statusElement.classList.toggle('status-warning', isOld || updateFailed);

		const titleParts = [];
		if (runStartedAt)
			titleParts.push(`Laufbeginn: ${formatStatusTimestamp(runStartedAt)}`);
		if (updateFailed)
			titleParts.push('Serverabgleich fehlgeschlagen');
		statusElement.title = titleParts.join('\n');
	}

	function clearStatus() {
		if (!statusElement)
			return;

		statusElement.hidden = true;
		statusElement.textContent = '';
		statusElement.title = '';
		statusElement.classList.remove('status-server', 'status-local', 'status-warning');
	}

	function setMessage({ type = 'info', text = '', onRetry = null } = {}) {
		if (!messageElement)
			return;

		messageElement.hidden = false;
		messageElement.textContent = '';
		messageElement.className = `data-message data-message-${type}`;
		messageElement.appendChild(document.createTextNode(text));

		if (onRetry) {
			retryButton = document.createElement('button');
			retryButton.type = 'button';
			retryButton.textContent = 'Erneut versuchen';
			retryButton.addEventListener('click', onRetry);
			messageElement.appendChild(retryButton);
		}
	}

	function clearMessage() {
		if (!messageElement)
			return;

		messageElement.hidden = true;
		messageElement.textContent = '';
		retryButton = null;
	}

	return { setStatus, clearStatus, setMessage, clearMessage };
}
