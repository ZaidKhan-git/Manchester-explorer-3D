/**
 * db.js — Manchester Map IndexedDB Layer
 * =======================================
 * Provides a zero-latency local database for all map data.
 * On first load it hydrates from the inline JS data files.
 * Every subsequent page load reads directly from IndexedDB — no API calls.
 *
 * Requires: manchester_buildings.js and manchester_amenities.js loaded first.
 */

const DB = (() => {
    const DB_NAME    = 'ManchesterMapDB';
    const DB_VERSION = 8;                 // bump if schema changes
    const S_BUILDINGS = 'buildings';
    const S_AMENITIES = 'amenities';
    const S_META      = 'meta';

    let _db = null;

    // ── IDB helpers ──────────────────────────────────────────────────────────

    function openIDB() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, DB_VERSION);

            req.onupgradeneeded = (e) => {
                const db = e.target.result;
                // buildings: one record per feature, keyed by building id string
                if (!db.objectStoreNames.contains(S_BUILDINGS))
                    db.createObjectStore(S_BUILDINGS, { keyPath: 'id' });
                // amenities: one record per accommodation id
                if (!db.objectStoreNames.contains(S_AMENITIES))
                    db.createObjectStore(S_AMENITIES, { keyPath: 'id' });
                // meta: key/value store for version tracking
                if (!db.objectStoreNames.contains(S_META))
                    db.createObjectStore(S_META, { keyPath: 'key' });
            };

            req.onsuccess  = (e) => resolve(e.target.result);
            req.onerror    = ()  => reject(req.error);
        });
    }

    function store(name, mode = 'readonly') {
        return _db.transaction([name], mode).objectStore(name);
    }

    function prom(req) {
        return new Promise((res, rej) => {
            req.onsuccess = () => res(req.result);
            req.onerror   = () => rej(req.error);
        });
    }

    // ── Population helpers ───────────────────────────────────────────────────

    async function _populateBuildings() {
        const s = store(S_BUILDINGS, 'readwrite');
        const features = manchesterBuildingsData.features;
        for (const f of features) {
            await prom(s.put({ id: String(f.properties.id), feature: f }));
        }
        console.log(`[DB] Stored ${features.length} buildings`);
    }

    async function _populateAmenities() {
        const s = store(S_AMENITIES, 'readwrite');
        let count = 0;
        for (const [id, data] of Object.entries(manchesterAmenitiesData)) {
            await prom(s.put({ id: String(id), ...data }));
            count++;
        }
        console.log(`[DB] Stored ${count} amenity sets`);
    }

    // ── Public API ───────────────────────────────────────────────────────────

    /**
     * Initialise the database. Must be called before any other DB method.
     * On first call, hydrates from JS data files. Subsequent calls are instant.
     */
    async function init() {
        _db = await openIDB();

        // Check if the current data version is already stored
        const meta = await prom(store(S_META).get('data_version'));

        if (!meta || meta.value !== DB_VERSION) {
            console.log('[DB] Populating IndexedDB from embedded JS data...');
            // Clear any stale data from previous version
            await prom(store(S_BUILDINGS, 'readwrite').clear());
            await prom(store(S_AMENITIES, 'readwrite').clear());

            await _populateBuildings();
            await _populateAmenities();

            await prom(store(S_META, 'readwrite').put({
                key: 'data_version', value: DB_VERSION, ts: Date.now()
            }));
            console.log('[DB] ✅ IndexedDB ready (fresh hydration)');
        } else {
            console.log(`[DB] ✅ Serving from IndexedDB cache (version ${DB_VERSION})`);
        }
    }

    /**
     * Returns all accommodation buildings as a GeoJSON FeatureCollection.
     */
    async function getBuildings() {
        const all = await prom(store(S_BUILDINGS).getAll());
        return {
            type: 'FeatureCollection',
            features: all.map(r => r.feature),
        };
    }

    /**
     * Returns amenity data for a single accommodation.
     * @param {string|number} id - accommodation id
     * @returns {{ name, features, summary } | null}
     */
    async function getAmenities(id) {
        const record = await prom(store(S_AMENITIES).get(String(id)));
        return record || null;
    }

    return { init, getBuildings, getAmenities };
})();
