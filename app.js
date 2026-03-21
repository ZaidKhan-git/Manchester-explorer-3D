// =============================================================================
// app.js — Manchester Student Accommodations 3D Map
// =============================================================================
// Architecture:
//   1. Map init (Mapbox, Manchester center)
//   2. DB.init() — hydrates IndexedDB from embedded JS data on first load
//   3. Gray-leak fix — OSM building IDs filtered from the background layer
//   4. Accommodations layer — real/generated polygons, color-coded by category
//   5. Amenities layer — pre-cached polygons from amenities_cache, no live API
//   6. Interaction — click → flyTo (precise lat/lng) + rich side panel

// ── Mapbox Token ─────────────────────────────────────────────────────────────
mapboxgl.accessToken = '**********************************************g';

// ── Constants ─────────────────────────────────────────────────────────────────
const MANCHESTER_CENTER = [-2.2376, 53.4808];   // [lng, lat]
const INITIAL_ZOOM      = 13.8;
const INITIAL_PITCH     = 60;
const INITIAL_BEARING   = -20;

// Color palette — category → extrusion color
const CATEGORY_COLORS = {
    'Student Accommodation': '#3b82f6',   // vivid blue
    'College':               '#2563eb',   // deeper blue
    'University':            '#6366f1',   // indigo
    'Restaurant':            '#f59e0b',   // amber
    'Cafe':                  '#10b981',   // emerald
    'Bar':                   '#f97316',   // orange
    'Nightclub':             '#d946ef',   // fuchsia
    'Sports Centre':         '#ef4444',   // red
    'Gym':                   '#fb7185',   // rose
    'Convenience Store':     '#facc15',   // yellow
    'Supermarket':           '#eab308',   // gold
    'Pharmacy':              '#a3e635',   // lime
    'Library':               '#8b5cf6',   // violet
    'Metro Station':         '#0ea5e9',   // sky
    'Bus Stop':              '#94a3b8',   // slate
    'Park':                  '#6ee7b7',   // mint
    'Church':                '#64748b',   // gray-blue
};

// Mapbox fill-expression from the color palette
function buildColorExpression(fallback = '#94a3b8') {
    const expr = ['match', ['get', 'category']];
    for (const [cat, color] of Object.entries(CATEGORY_COLORS)) {
        expr.push(cat, color);
    }
    expr.push(fallback);
    return expr;
}

// ── Map Init ──────────────────────────────────────────────────────────────────
const map = new mapboxgl.Map({
    container:  'map',
    style:      'mapbox://styles/mapbox/dark-v11',
    center:     MANCHESTER_CENTER,
    zoom:       INITIAL_ZOOM,
    pitch:      INITIAL_PITCH,
    bearing:    INITIAL_BEARING,
    antialias:  true,
});

map.addControl(new mapboxgl.NavigationControl(), 'bottom-right');

// ── State ─────────────────────────────────────────────────────────────────────
let allBuildingsGeoJSON  = null;   // FeatureCollection from DB
let currentBuildingId    = null;   // id of the selected accommodation
let mapLoaded            = false;
let dbReady              = false;

// ── Main load sequence ────────────────────────────────────────────────────────
map.on('load', async () => {
    mapLoaded = true;

    // Find the first symbol layer (map labels) — we insert below it
    const layers = map.getStyle().layers;
    let labelLayerId;
    for (const layer of layers) {
        if (layer.type === 'symbol' && layer.layout && layer.layout['text-field']) {
            labelLayerId = layer.id;
            break;
        }
    }

    // ── 1. Background city buildings ─────────────────────────────────────────
    // We will update the filter later (after data loads) to exclude the OSM
    // buildings we are rendering ourselves → eliminates gray leak for those.
    map.addLayer(
        {
            id:           '3d-buildings-background',
            source:       'composite',
            'source-layer': 'building',
            filter:       ['==', 'extrude', 'true'],
            type:         'fill-extrusion',
            minzoom:      13,
            paint: {
                'fill-extrusion-color': '#252b32',

                'fill-extrusion-height': [
                    'interpolate', ['linear'], ['zoom'],
                    13, 0, 15.15, ['get', 'height']
                ],
                'fill-extrusion-base': [
                    'interpolate', ['linear'], ['zoom'],
                    13, 0, 15.15, ['get', 'min_height']
                ],

                'fill-extrusion-opacity': 1.0,
            }
        },
        labelLayerId
    );

    // ── 2. Accommodation source (empty, will be filled after DB init) ─────────
    map.addSource('accommodations', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
    });

    // Main coloured building layer — starts at 1 m (just enough to prevent gray map artifact leak)
    map.addLayer(
        {
            id:     'accommodations-layer',
            type:   'fill-extrusion',
            source: 'accommodations',
            paint: {
                'fill-extrusion-color':            buildColorExpression(),
                'fill-extrusion-height':           ['get', 'height'],
                'fill-extrusion-base':             1,
                'fill-extrusion-opacity':          1.0,
                'fill-extrusion-vertical-gradient': true,
            },
        },
        labelLayerId
    );

    // ── 3. Amenities source ───────────────────────────────────────────────────
    map.addSource('local-amenities', {
        type:  'geojson',
        data: { type: 'FeatureCollection', features: [] },
    });

    map.addLayer(
        {
            id:     'local-amenities-layer',
            type:   'fill-extrusion',
            source: 'local-amenities',
            paint: {
                'fill-extrusion-color':   buildColorExpression('#64748b'),
                'fill-extrusion-height':  ['get', 'height'],
                'fill-extrusion-base':    ['get', 'base_height'],
                'fill-extrusion-opacity': 0.92,
            },
        },
        labelLayerId
    );

    // ── 4. Load data from DB ───────────────────────────────────────────────────
    try {
        await DB.init();
        allBuildingsGeoJSON = await DB.getBuildings();
        dbReady = true;

        // Push buildings to the map
        map.getSource('accommodations').setData(allBuildingsGeoJSON);

        // ── Gray-leak fix: filter out all buildings we own from background ────
        // Collect numeric OSM way IDs for every accommodation that has a real
        // footprint (osm or snapped).  These IDs match the feature IDs used by
        // the Mapbox composite `building` source layer so we can hide the grey
        // tile under our custom-coloured extrusion.
        const ownedIds = allBuildingsGeoJSON.features
            .filter(f => ['osm', 'snapped', 'generated'].includes(f.properties.geometry_source)
                      && f.properties.osm_id)
            .map(f => parseInt(f.properties.osm_id.replace(/\D+/g, ''), 10))
            .filter(n => !isNaN(n));

        // Purge specific overlapping grey structural parts around Artisan and Bridgewater
        const extraHiddenIds = [
            136507471, 136507472, 136999888, 733085843,  // Artisan overlapping artifacts
            204921664, 647047939, 647047940, 647047941   // Bridgewater overlapping artifacts
        ];
        
        window.allIdsToHideBase = [...new Set([...ownedIds, ...extraHiddenIds])];

        if (window.allIdsToHideBase.length > 0) {
            // Apply legacy-style filter to exclude our IDs from the background layer
            map.setFilter('3d-buildings-background', [
                'all',
                ['==', 'extrude', 'true'],
                ['!in', '$id', ...window.allIdsToHideBase]
            ]);
            console.log(`[App] Hidden ${window.allIdsToHideBase.length} owned buildings from grey background layer`);
        }

    } catch (err) {
        console.error('[App] DB init failed:', err);
    }

    // ── 5. Interaction ────────────────────────────────────────────────────────

    // Cursor
    map.on('mouseenter', 'accommodations-layer',  () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', 'accommodations-layer',  () => map.getCanvas().style.cursor = '');
    map.on('mouseenter', 'local-amenities-layer', () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', 'local-amenities-layer', () => map.getCanvas().style.cursor = '');

    // Amenity click → mini popup
    map.on('click', 'local-amenities-layer', (e) => {
        if (!e.features.length) return;
        const p = e.features[0].properties;
        const dist = p.distance_m ? ` · ${p.distance_m} m away` : '';
        new mapboxgl.Popup({ closeButton: false, closeOnClick: true, offset: 15 })
            .setLngLat(e.lngLat)
            .setHTML(`
                <div style="color:#1f2937;padding:6px 2px;font-family:'Inter',sans-serif;">
                    <strong style="font-size:13px;display:block;margin-bottom:4px;">${p.name}</strong>
                    <span style="font-size:11px;background:#e5e7eb;padding:2px 7px;border-radius:12px;color:#4b5563;">
                        ${p.category}${dist}
                    </span>
                </div>`)
            .addTo(map);
    });

    // Accommodation click
    map.on('click', 'accommodations-layer', async (e) => {
        if (!e.features.length) return;
        const feature = e.features[0];
        const props   = feature.properties;

        // ── Precise flyTo using geocoded coords (not polygon centroid) ─────────
        // props.lat / props.lng are the original geocoded coordinates — always
        // accurate even for generated bounding-box footprints.
        const centerLng = parseFloat(props.lng);
        const centerLat = parseFloat(props.lat);

        map.flyTo({
            center:  [centerLng, centerLat],
            zoom:    16.8,
            pitch:   65,
            bearing: map.getBearing() + 12,
            speed:   1.1,
            curve:   1.2,
            essential: true,
        });

        currentBuildingId = String(props.id);

        // ── Show info panel ───────────────────────────────────────────────────
        populatePanel(props, null);
        document.getElementById('info-panel').classList.add('open');

        // ── Load amenities from local cache (instant) ─────────────────────────
        const amenityData = await DB.getAmenities(currentBuildingId);

        if (amenityData && amenityData.features && amenityData.features.length > 0) {
            map.getSource('local-amenities').setData({
                type:     'FeatureCollection',
                features: amenityData.features,
            });
            populatePanel(props, amenityData.summary);
            
            // Suppress background mapbox structures directly underneath currently loaded amenities
            const activeAmenityIds = amenityData.features
                .map(f => f.properties.osm_id ? parseInt(String(f.properties.osm_id).replace(/\D+/g, ''), 10) : null)
                .filter(n => n && !isNaN(n));
            
            if (activeAmenityIds.length > 0 && window.allIdsToHideBase) {
                const combinedIds = [...new Set([...window.allIdsToHideBase, ...activeAmenityIds])];
                map.setFilter('3d-buildings-background', [
                    'all',
                    ['==', 'extrude', 'true'],
                    ['!in', '$id', ...combinedIds]
                ]);
            }
        } else {
            map.getSource('local-amenities').setData({ type: 'FeatureCollection', features: [] });
            populatePanel(props, {});
            if (window.allIdsToHideBase) {
                map.setFilter('3d-buildings-background', [
                    'all',
                    ['==', 'extrude', 'true'],
                    ['!in', '$id', ...window.allIdsToHideBase]
                ]);
            }
        }
    });

    // Click on empty background → close
    map.on('click', (e) => {
        const a = map.queryRenderedFeatures(e.point, { layers: ['accommodations-layer'] });
        const b = map.queryRenderedFeatures(e.point, { layers: ['local-amenities-layer'] });
        if (!a.length && !b.length) {
            closePanel();
        }
    });

    document.getElementById('close-panel').addEventListener('click', closePanel);
});

// ── Panel helpers ─────────────────────────────────────────────────────────────

function closePanel() {
    document.getElementById('info-panel').classList.remove('open');
    // Clear amenity overlay when panel closes
    if (map.getSource('local-amenities')) {
        map.getSource('local-amenities').setData({ type: 'FeatureCollection', features: [] });
        // Restore background building mesh
        if (window.allIdsToHideBase) {
            map.setFilter('3d-buildings-background', [
                'all',
                ['==', 'extrude', 'true'],
                ['!in', '$id', ...window.allIdsToHideBase]
            ]);
        }
    }
}

function stars(score) {
    if (!score || score <= 0) return '<span class="no-rating">No reviews yet</span>';
    const full  = Math.round(score);
    const empty = 5 - full;
    return '★'.repeat(full) + '☆'.repeat(empty) + ` <span class="rating-num">${score.toFixed(1)}</span>`;
}

function populatePanel(props, amenitySummary) {
    // Header
    el('building-name').textContent = props.name  || 'Student Accommodation';
    el('building-location').textContent =
        (props.category ? props.category + ' • ' : '') + (props.address || props.zipcode || '');

    // ── University block ──────────────────────────────────────────────────────
    const schoolName = props.school_name || '';
    const schoolDist = props.school_distance ? `${parseFloat(props.school_distance).toFixed(2)} km` : '';
    el('university-name').textContent = schoolName || '—';
    el('university-dist').textContent = schoolDist ? `${schoolDist} away` : '';
    el('university-abbr').textContent = props.school_abbr || '';

    // ── Pricing block ─────────────────────────────────────────────────────────
    const rent     = props.rent_amount     ? `£${parseFloat(props.rent_amount).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` : null;
    const unit     = props.lease_unit      ? `/${props.lease_unit.toLowerCase()}` : '';
    const currency = props.rent_currency;
    el('price-display').innerHTML = rent
        ? `<span class="price-amount">${rent}</span><span class="price-unit">${unit}</span>`
        : '<span class="price-na">Price on request</span>';

    // Rating
    el('rating-display').innerHTML = stars(parseFloat(props.review_score) || 0);
    const reviewCount = parseInt(props.review_count) || 0;
    el('review-count').textContent = reviewCount > 0 ? `${reviewCount} review${reviewCount > 1 ? 's' : ''}` : '';

    // ── Property Details block ────────────────────────────────────────────────
    const detailItems = [];
    if (props.room_types)   detailItems.push({ label: 'Room Types', value: props.room_types });
    if (props.bed_num > 0)  detailItems.push({ label: 'Beds',       value: props.bed_num });
    if (props.total_floor > 0) detailItems.push({ label: 'Floors',  value: props.total_floor });
    if (props.building_levels) detailItems.push({ label: 'Levels',  value: props.building_levels });
    if (props.supplier_name)   detailItems.push({ label: 'Operator',value: props.supplier_name });

    const detailUl = el('property-details-list');
    detailUl.innerHTML = '';
    if (detailItems.length > 0) {
        detailItems.forEach(({ label, value }) => {
            const li = document.createElement('li');
            li.innerHTML = `<span class="detail-label">${label}</span><span class="detail-value">${value}</span>`;
            detailUl.appendChild(li);
        });
    } else {
        detailUl.innerHTML = '<li>Details unavailable</li>';
    }

    // ── Nearby Amenities block ────────────────────────────────────────────────
    const amenityUl = el('amenities-list');
    amenityUl.innerHTML = '';

    if (amenitySummary === null) {
        // Loading state
        amenityUl.innerHTML = '<li class="loading">Loading nearby amenities...</li>';
    } else if (!amenitySummary || Object.keys(amenitySummary).length === 0) {
        amenityUl.innerHTML = '<li>No mapped amenity buildings within 1 km</li>';
    } else {
        const sorted = Object.entries(amenitySummary).sort((a, b) => b[1] - a[1]);
        for (const [cat, count] of sorted) {
            const li  = document.createElement('li');
            const dot = document.createElement('span');
            dot.className = 'amenity-dot';
            dot.style.background = CATEGORY_COLORS[cat] || '#94a3b8';
            li.appendChild(dot);
            li.appendChild(document.createTextNode(`${cat}: ${count}`));
            amenityUl.appendChild(li);
        }
    }

    // ── Listing link ──────────────────────────────────────────────────────────
    const linkEl = el('listing-link');
    if (props.house_url) {
        linkEl.href = props.house_url;
        linkEl.style.display = 'inline-flex';
    } else {
        linkEl.style.display = 'none';
    }
}

function el(id) {
    return document.getElementById(id);
}
