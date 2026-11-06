import { parseDataStatus, validateMembers } from './data.js';
import { parseMapState } from './map-state.js';

const DB_NAME = 'vmkarte';
const DB_VERSION = 1;
const STORE_NAME = 'kv';
const KEYS = ['members', 'status', 'etag', 'lastModified'];
const MAP_STATE_KEY = 'mapState';

let databasePromise = null;
let storageUnavailable = false;

function openDatabase() {
	if (storageUnavailable)
		return Promise.resolve(null);
	if (databasePromise)
		return databasePromise;

	databasePromise = new Promise(resolve => {
		let request;
		try {
			request = indexedDB.open(DB_NAME, DB_VERSION);
		}
		catch (error) {
			console.warn('IndexedDB ist nicht verfügbar; Kartendaten werden nicht lokal gespeichert.', error);
			storageUnavailable = true;
			resolve(null);
			return;
		}

		request.onupgradeneeded = () => {
			const database = request.result;
			if (!database.objectStoreNames.contains(STORE_NAME))
				database.createObjectStore(STORE_NAME);
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => {
			console.warn('IndexedDB konnte nicht geöffnet werden.', request.error);
			storageUnavailable = true;
			resolve(null);
		};
	});

	return databasePromise;
}

function readAll(database) {
	return new Promise((resolve, reject) => {
		const transaction = database.transaction(STORE_NAME, 'readonly');
		const store = transaction.objectStore(STORE_NAME);
		const values = {};

		for (const key of KEYS) {
			const request = store.get(key);
			request.onsuccess = () => { values[key] = request.result; };
		}

		transaction.oncomplete = () => resolve(values);
		transaction.onerror = () => reject(transaction.error);
		transaction.onabort = () => reject(transaction.error);
	});
}

function readValue(database, key) {
	return new Promise((resolve, reject) => {
		const transaction = database.transaction(STORE_NAME, 'readonly');
		const request = transaction.objectStore(STORE_NAME).get(key);
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
		transaction.onabort = () => reject(transaction.error);
	});
}

function writeValue(database, key, value) {
	return new Promise((resolve, reject) => {
		const transaction = database.transaction(STORE_NAME, 'readwrite');
		transaction.objectStore(STORE_NAME).put(value, key);
		transaction.oncomplete = () => resolve();
		transaction.onerror = () => reject(transaction.error);
		transaction.onabort = () => reject(transaction.error);
	});
}

export async function readCache() {
	const database = await openDatabase();
	if (!database)
		return null;

	try {
		const values = await readAll(database);
		const validated = validateMembers(values.members);
		if (!validated)
			return null;

		return {
			members: validated.members,
			status: parseDataStatus(values.status),
			etag: typeof values.etag === 'string' ? values.etag : null,
			lastModified: typeof values.lastModified === 'string' ? values.lastModified : null,
		};
	}
	catch (error) {
		console.warn('Lokaler Kartenstand konnte nicht gelesen werden.', error);
		return null;
	}
}

export async function writeCache({ members, status, etag, lastModified }) {
	const database = await openDatabase();
	if (!database)
		return false;

	try {
		await new Promise((resolve, reject) => {
			const transaction = database.transaction(STORE_NAME, 'readwrite');
			const store = transaction.objectStore(STORE_NAME);

			store.put(members, 'members');
			if (status)
				store.put(status, 'status');
			else
				store.delete('status');

			if (etag)
				store.put(etag, 'etag');
			else
				store.delete('etag');

			if (lastModified)
				store.put(lastModified, 'lastModified');
			else
				store.delete('lastModified');

			transaction.oncomplete = () => resolve();
			transaction.onerror = () => reject(transaction.error);
			transaction.onabort = () => reject(transaction.error);
		});
		return true;
	}
	catch (error) {
		console.warn('Lokaler Kartenstand konnte nicht gespeichert werden.', error);
		return false;
	}
}

export async function readMapState() {
	const database = await openDatabase();
	if (!database)
		return null;

	try {
		return parseMapState(await readValue(database, MAP_STATE_KEY));
	}
	catch (error) {
		console.warn('Lokaler Kartenstatus konnte nicht gelesen werden.', error);
		return null;
	}
}

export async function writeMapState(mapState) {
	const normalized = parseMapState(mapState);
	if (!normalized)
		return false;

	const database = await openDatabase();
	if (!database)
		return false;

	try {
		await writeValue(database, MAP_STATE_KEY, normalized);
		return true;
	}
	catch (error) {
		console.warn('Lokaler Kartenstatus konnte nicht gespeichert werden.', error);
		return false;
	}
}

export async function clearCache() {
	const database = await openDatabase();
	if (!database)
		return false;

	try {
		await new Promise((resolve, reject) => {
			const transaction = database.transaction(STORE_NAME, 'readwrite');
			transaction.objectStore(STORE_NAME).clear();
			transaction.oncomplete = () => resolve();
			transaction.onerror = () => reject(transaction.error);
			transaction.onabort = () => reject(transaction.error);
		});
		return true;
	}
	catch (error) {
		console.warn('Lokaler Kartenstand konnte nicht gelöscht werden.', error);
		return false;
	}
}
