'use strict';
/* ── Pakistan Electronics Intelligence — script.js ─────────────────────── */

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  userLat: null,
  userLon: null,
  storeFilter: 'all',    // 'all' | 'physical' | 'online'
  locationConfirmed: false,
  results: null,
  catalogFilter: 'all',
  allProducts: [],
  allStores: [],
  branches: [],
  map: null,
  branchMarkers: new Map(),
  userMarker: null,
  routeLayer: null,
  routeTarget: null,
  mapReady: false,
  locationSuggestions: [],
  selectedSuggestionIndex: -1,
  resultSortPrimary: 'recommended',
  resultSortSecondary: 'none',
  resultMaxDistance: '',
  resultMaxTotal: '',
  resultMinRating: 0,
  resultsControlsBound: false,
  latestQuery: '',
  chatBusy: false,
};

// ── Helpers ────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeUrl(value) {
  if (!value) return '#';
  try {
    const url = new URL(String(value), window.location.origin);
    if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
    return '#';
  } catch (_) {
    return '#';
  }
}

function toNum(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function parseOptionalNumber(value) {
  if (value === null || value === undefined) return Number.NaN;
  const raw = String(value).trim();
  if (!raw) return Number.NaN;
  const n = Number(raw);
  return Number.isFinite(n) ? n : Number.NaN;
}


function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icon = type === 'error' ? '!' : type === 'success' ? '+' : 'i';
  el.innerHTML = `<span>${icon}</span>`;
  el.append(` ${String(msg ?? '')}`);
  $('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function stagger(elements, delayMs = 80) {
  elements.forEach((el, i) => {
    el.style.animationDelay = `${i * delayMs}ms`;
  });
}

function stars(n, total = 5) {
  return Array.from({ length: total }, (_, i) =>
    `<span class="star ${i < n ? 'filled' : ''}">★</span>`
  ).join('');
}

function fmt(n, dec = 0) {
  return Number(n).toLocaleString('en-PK', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function formatDuration(value) {
  const total = Math.round(toNum(value, 0));
  if (!Number.isFinite(total) || total <= 0) return '0m';

  const minute = 1;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;
  const month = 30 * day;
  const year = 365 * day;

  const plural = (num, singular, pluralLabel) => (num === 1 ? singular : pluralLabel);

  if (total >= year) {
    const years = Math.floor(total / year);
    return `${years} ${plural(years, 'year', 'years')}`;
  }
  if (total >= month) {
    const months = Math.floor(total / month);
    return `${months} ${plural(months, 'month', 'months')}`;
  }
  if (total >= week) {
    const weeks = Math.floor(total / week);
    return `${weeks} ${plural(weeks, 'week', 'weeks')}`;
  }
  if (total >= day) {
    const days = Math.floor(total / day);
    return `${days} ${plural(days, 'day', 'days')}`;
  }
  if (total >= hour) {
    const hours = Math.floor(total / hour);
    const mins = total % hour;
    const label = hours === 1 ? 'hr' : 'hrs';
    return mins ? `${hours}${label} ${mins}m` : `${hours}${label}`;
  }
  return `${total}m`;
}

function debounce(fn, delayMs) {
  let timerId = null;
  return (...args) => {
    if (timerId) clearTimeout(timerId);
    timerId = setTimeout(() => fn(...args), delayMs);
  };
}

function saveLastLocation(lat, lon, name) {
  try {
    const payload = {
      lat,
      lon,
      name: String(name || ''),
      savedAt: Date.now(),
    };
    window.localStorage.setItem('pi:lastLocation', JSON.stringify(payload));
  } catch (_) {
    // ignore storage errors
  }
}

function restoreLastLocation() {
  try {
    const raw = window.localStorage.getItem('pi:lastLocation');
    if (!raw) return false;
    const payload = JSON.parse(raw);
    const lat = toNum(payload?.lat, Number.NaN);
    const lon = toNum(payload?.lon, Number.NaN);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return false;
    setUserCoordinates(lat, lon, true);
    if (payload?.name) {
      $('inp-location-name').value = payload.name;
    }
    return true;
  } catch (_) {
    return false;
  }
}

function setUserCoordinates(lat, lon, confirmed = false) {
  state.userLat = lat;
  state.userLon = lon;
  $('inp-lat').value = fmt(lat, 6);
  $('inp-lon').value = fmt(lon, 6);
  state.locationConfirmed = state.locationConfirmed || confirmed;
  updateUserMarker();
  saveLastLocation(lat, lon, $('inp-location-name')?.value || '');
}

function getUserLocation() {
  let lat = toNum(state.userLat, NaN);
  let lon = toNum(state.userLon, NaN);
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    lat = toNum($('inp-lat').value, NaN);
    lon = toNum($('inp-lon').value, NaN);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      setUserCoordinates(lat, lon, true);
    }
  }
  if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
  return { lat, lon };
}

function openMapView() {
  const mapBtn = [...$$('.nav-btn')].find(btn => btn.dataset.view === 'map');
  if (mapBtn) mapBtn.click();
}

function setRouteSummary(message) {
  const el = $('route-summary');
  if (!el) return;
  el.innerHTML = message;
}

function clearActiveRoute() {
  if (state.routeLayer) {
    state.routeLayer.remove();
    state.routeLayer = null;
  }
  state.routeTarget = null;
  const navBtn = $('btn-start-route-nav');
  if (navBtn) navBtn.disabled = true;
  setRouteSummary('Choose a store, then click <strong>Show Route</strong>.');
}

function ensureResultsControlsMarkup() {
  if ($('res-sort-primary')) return;
  const header = document.querySelector('#results-list .results-header');
  if (!header) return;

  const wrap = document.createElement('div');
  wrap.id = 'results-controls';
  wrap.className = 'results-controls';
  wrap.innerHTML = `
    <label class="results-control">
      <span>Primary Sort</span>
      <select id="res-sort-primary" class="inp">
        <option value="recommended">Recommended</option>
        <option value="total_asc">Total: Low to High</option>
        <option value="price_asc">Price: Low to High</option>
        <option value="distance_asc">Nearest First</option>
        <option value="duration_asc">Fastest Drive First</option>
        <option value="rating_desc">Highest Rated First</option>
      </select>
    </label>
    <label class="results-control">
      <span>Secondary Sort</span>
      <select id="res-sort-secondary" class="inp">
        <option value="none">None</option>
        <option value="total_asc">Total: Low to High</option>
        <option value="price_asc">Price: Low to High</option>
        <option value="distance_asc">Nearest First</option>
        <option value="duration_asc">Fastest Drive First</option>
        <option value="rating_desc">Highest Rated First</option>
      </select>
    </label>
    <label class="results-control">
      <span>Max Distance (km)</span>
      <input id="res-max-distance" type="number" min="0" step="0.1" placeholder="Any" class="inp">
    </label>
    <label class="results-control">
      <span>Max Total (PKR)</span>
      <input id="res-max-total" type="number" min="0" step="1" placeholder="Any" class="inp">
    </label>
    <label class="results-control">
      <span>Min Rating</span>
      <select id="res-min-rating" class="inp">
        <option value="0">Any</option>
        <option value="3">3.0+</option>
        <option value="4">4.0+</option>
        <option value="4.5">4.5+</option>
      </select>
    </label>
    <button id="res-reset-filters" type="button" class="btn btn-outline btn-sm">Reset Filters</button>
  `;
  header.appendChild(wrap);
}

// ── Navigation ────────────────────────────────────────────────────────────
$$('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const view = btn.dataset.view;
    $$('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    $$('.view').forEach(v => v.classList.remove('active'));
    const target = $(`view-${view}`);
    target.classList.add('active');

    if (view === 'catalog') loadCatalog();
    if (view === 'stores') loadStoresView();
    if (view === 'ai-insights') fetchAiInsightsPanel(false);
    if (view === 'map') {
      ensureMapReady();
      if (state.map) {
        setTimeout(() => state.map.invalidateSize(), 50);
      }
    }
  });
});

// ── Geolocation + Location Search ────────────────────────────────────────────
async function reverseLookupLocation(lat, lon) {
  try {
    const response = await fetch(`/api/location/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
    const payload = await response.json();
    if (response.ok && payload.display_name) {
      $('inp-location-name').value = payload.display_name;
    }
  } catch (_) {
    // Silent fallback: coordinates are already set.
  }
}

function hideLocationSuggestions() {
  const box = $('location-suggestions');
  box.classList.add('hidden');
  box.innerHTML = '';
  state.selectedSuggestionIndex = -1;
}

function applyLocationSuggestion(item) {
  if (!item) return;
  const lat = toNum(item.lat, NaN);
  const lon = toNum(item.lon, NaN);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return;

  setUserCoordinates(lat, lon, true);
  $('inp-location-name').value = item.display_name || '';
  hideLocationSuggestions();
  ensureMapReady();

  if (state.map) {
    state.map.setView([lat, lon], 14, { animate: true });
  }
}

function renderLocationSuggestions(items) {
  const box = $('location-suggestions');
  if (!items.length) {
    box.innerHTML = '<div class="location-suggestion"><span class="location-suggestion-meta">No matches found.</span></div>';
    box.classList.remove('hidden');
    return;
  }

  box.innerHTML = '';
  items.forEach((item, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'location-suggestion';
    btn.innerHTML = `
      <span class="location-suggestion-title">${esc(item.display_name || 'Unnamed place')}</span>
      <span class="location-suggestion-meta">${esc(item.type || 'location')} · ${fmt(item.lat, 5)}, ${fmt(item.lon, 5)}</span>
    `;
    btn.addEventListener('mousedown', e => {
      e.preventDefault();
      applyLocationSuggestion(item);
    });
    if (idx === state.selectedSuggestionIndex) btn.classList.add('active');
    box.appendChild(btn);
  });
  box.classList.remove('hidden');
}

const requestLocationSuggestions = debounce(async () => {
  const query = $('inp-location-name').value.trim();
  if (query.length < 2) {
    hideLocationSuggestions();
    return;
  }

  try {
    const known = getUserLocation();
    let url = `/api/location/suggest?q=${encodeURIComponent(query)}&limit=7`;
    if (known) {
      url += `&lat=${known.lat}&lon=${known.lon}`;
    }
    const response = await fetch(url);
    const payload = await response.json();
    state.locationSuggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
    state.selectedSuggestionIndex = -1;
    renderLocationSuggestions(state.locationSuggestions);
  } catch (err) {
    hideLocationSuggestions();
    toast('Location search failed. Check your internet connection.', 'error');
  }
}, 280);

$('inp-location-name').addEventListener('input', () => {
  requestLocationSuggestions();
});

$('inp-location-name').addEventListener('focus', () => {
  const current = $('inp-location-name').value.trim();
  if (current.length >= 2) requestLocationSuggestions();
});

$('inp-location-name').addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    hideLocationSuggestions();
    return;
  }

  if (!state.locationSuggestions.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    state.selectedSuggestionIndex = (state.selectedSuggestionIndex + 1) % state.locationSuggestions.length;
    renderLocationSuggestions(state.locationSuggestions);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    state.selectedSuggestionIndex = state.selectedSuggestionIndex <= 0
      ? state.locationSuggestions.length - 1
      : state.selectedSuggestionIndex - 1;
    renderLocationSuggestions(state.locationSuggestions);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const picked = state.locationSuggestions[state.selectedSuggestionIndex] || state.locationSuggestions[0];
    applyLocationSuggestion(picked);
  }
});

$('inp-location-name').addEventListener('blur', () => {
  setTimeout(hideLocationSuggestions, 160);
});

async function detectLocationViaIp(confirm = true) {
  const button = $('btn-ip-locate');
  if (button) {
    button.innerHTML = '<div class="spinner"></div> Locating…';
    button.disabled = true;
  }

  try {
    const response = await fetch('/api/location/ip');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'IP location failed');

    const lat = toNum(payload.lat, NaN);
    const lon = toNum(payload.lon, NaN);
    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      throw new Error('IP location is unavailable right now.');
    }
    setUserCoordinates(lat, lon, confirm);
    if (payload.display_name) {
      $('inp-location-name').value = payload.display_name;
    } else {
      await reverseLookupLocation(lat, lon);
    }
    ensureMapReady();
    if (state.map) state.map.setView([lat, lon], 12, { animate: true });
    toast('Location detected via IP.', 'success');
    return true;
  } catch (err) {
    toast(err.message || 'IP location failed.', 'error');
    return false;
  } finally {
    if (button) {
      button.innerHTML = '<span class="btn-icon">◎</span> Detect via IP';
      button.disabled = false;
    }
  }
}

function detectLocationViaGps(confirm = true) {
  if (!navigator.geolocation) {
    toast('Geolocation is not supported by your browser.', 'error');
    if ($('chk-ip-fallback')?.checked) {
      detectLocationViaIp();
    }
    return;
  }

  if (!window.isSecureContext) {
    toast('Location access needs HTTPS (or localhost).', 'error');
    if ($('chk-ip-fallback')?.checked) {
      detectLocationViaIp();
    }
    return;
  }

  const button = $('btn-geolocate');
  if (button) {
    button.innerHTML = '<div class="spinner"></div> Detecting…';
    button.disabled = true;
  }

  navigator.geolocation.getCurrentPosition(
    async pos => {
      const lat = toNum(pos.coords.latitude, NaN);
      const lon = toNum(pos.coords.longitude, NaN);
      if (Number.isNaN(lat) || Number.isNaN(lon)) {
        toast('Detected coordinates are invalid. Try location search.', 'error');
      } else {
        setUserCoordinates(lat, lon, confirm);
        await reverseLookupLocation(lat, lon);
        ensureMapReady();
        if (state.map) state.map.setView([lat, lon], 14, { animate: true });
        toast('Location detected.', 'success');
      }
      if (button) {
        button.innerHTML = '<span class="btn-icon">◎</span> Detect via GPS';
        button.disabled = false;
      }
    },
    async err => {
      let msg = 'Could not detect your location.';
      if (err && err.code === 1) msg = 'Location permission denied. Allow browser location access.';
      if (err && err.code === 2) msg = 'Location unavailable. Move outdoors and retry.';
      if (err && err.code === 3) msg = 'Location request timed out. Retry.';
      toast(msg, 'error');

      if ($('chk-ip-fallback')?.checked) {
        await detectLocationViaIp(confirm);
      }

      if (button) {
        button.innerHTML = '<span class="btn-icon">◎</span> Detect via GPS';
        button.disabled = false;
      }
    },
    {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
    },
  );
}

$('btn-geolocate')?.addEventListener('click', () => {
  detectLocationViaGps(true);
});

$('btn-ip-locate')?.addEventListener('click', () => {
  detectLocationViaIp(true);
});

// ── Store filter chips (optimizer) ────────────────────────────────────────
$$('#store-filter-chips .chip').forEach(chip => {
  chip.addEventListener('click', () => {
    $$('#store-filter-chips .chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.storeFilter = chip.dataset.filter;
    if (state.results && !state.results.error) {
      applyResultsFiltersAndSort();
    }
  });
});

['inp-lat', 'inp-lon'].forEach(id => {
  $(id).addEventListener('change', () => {
    const lat = toNum($('inp-lat').value, NaN);
    const lon = toNum($('inp-lon').value, NaN);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      setUserCoordinates(lat, lon);
    }
  });
});

// ── Optimizer ────────────────────────────────────────────────────────────
async function resolveLocationFromInput() {
  const name = $('inp-location-name')?.value?.trim() || '';
  if (name.length < 2) return null;

  try {
    const response = await fetch(`/api/location/suggest?q=${encodeURIComponent(name)}&limit=1`);
    const payload = await response.json();
    const item = Array.isArray(payload.suggestions) ? payload.suggestions[0] : null;
    const lat = toNum(item?.lat, Number.NaN);
    const lon = toNum(item?.lon, Number.NaN);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      setUserCoordinates(lat, lon, true);
      if (item?.display_name) $('inp-location-name').value = item.display_name;
      return { lat, lon };
    }
  } catch (_) {
    // ignore and fall back to manual coordinates
  }

  return null;
}

function resetChat(message) {
  const body = $('ai-chat-body');
  if (!body) return;
  body.innerHTML = `
    <div class="ai-chat-empty" id="ai-chat-empty">${esc(message || 'Ask a question about the recommended product.')}</div>
  `;
}

function setChatEnabled(enabled, message) {
  const input = $('ai-chat-input');
  const send = $('ai-chat-send');
  if (input) input.disabled = !enabled;
  if (send) send.disabled = !enabled;
  resetChat(message || (enabled ? 'Ask a question about the recommended product.' : 'Run a search to start asking questions.'));
}

async function runOptimizerSearch() {
  const query = $('inp-search')?.value?.trim() || '';
  if (!query) {
    toast('Search a product first (e.g. iPhone 15, 1.5 ton AC).', 'error');
    return;
  }

  let location = getUserLocation();
  if (!location) {
    location = await resolveLocationFromInput();
  }
  if (!location) {
    const rawName = $('inp-location-name')?.value?.trim() || '';
    if (rawName) {
      toast('Select a suggested location to continue.', 'error');
      return;
    }
    location = { lat: 33.6844, lon: 73.0479 };
    setUserCoordinates(location.lat, location.lon);
    $('inp-location-name').value = 'Islamabad, Pakistan';
    toast('Using default location (Islamabad). Set your location for precise results.', 'info');
  }

  if (!state.locationConfirmed) {
    const proceed = window.confirm(
      `Use current location (${fmt(location.lat, 4)}, ${fmt(location.lon, 4)})? Click OK to continue, or Cancel to enter your location.`
    );
    if (!proceed) {
      toast('Please enter your location to continue.', 'info');
      $('inp-location-name')?.focus();
      return;
    }
    state.locationConfirmed = true;
  }

  const budget = $('inp-budget').value ? parseFloat($('inp-budget').value) : null;
  const priority = document.querySelector('[name="priority"]:checked')?.value || 'total_cost';

  state.userLat = location.lat;
  state.userLon = location.lon;
  state.latestQuery = query;

  const btn = $('btn-search') || $('btn-optimize');
  const originalText = btn?.innerHTML;
  if (btn) {
    btn.innerHTML = '<div class="spinner"></div> Searching…';
    btn.disabled = true;
  }

  $('empty-state').classList.add('hidden');
  $('results-list').classList.add('hidden');
  $('ai-panel').classList.add('hidden');
  setChatEnabled(false, 'Searching for the best recommendation…');

  try {
    const data = await post('/api/optimize', {
      user_lat: location.lat,
      user_lon: location.lon,
      category: 'electronics',
      query,
      store_filter: state.storeFilter,
      budget,
      priority,
    });
    data.query = query;
    renderResults(data);
    fetchIntelligence({
      user_lat: location.lat,
      user_lon: location.lon,
      category: 'electronics',
      query,
      store_filter: state.storeFilter,
      budget,
      priority,
    });
    fetchAiInsightsPanel(false, location);
    setChatEnabled(true);
  } catch (err) {
    toast('Error: ' + err.message, 'error');
    $('empty-state').classList.remove('hidden');
    setChatEnabled(false, 'Run a search to start asking questions.');
  } finally {
    if (btn) {
      btn.innerHTML = originalText || 'Search & Optimize';
      btn.disabled = false;
    }
  }
}

$('btn-search')?.addEventListener('click', runOptimizerSearch);
$('btn-optimize')?.addEventListener('click', runOptimizerSearch);

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'Server error');
  return data;
}

function compareBySortMode(a, b, mode) {
  const num = (obj, key, fallback = Infinity) => {
    const value = toNum(obj?.[key], Number.NaN);
    return Number.isNaN(value) ? fallback : value;
  };

  switch (mode) {
    case 'total_asc':
      return num(a, 'grand_total') - num(b, 'grand_total');
    case 'price_asc':
      return num(a, 'product_price') - num(b, 'product_price');
    case 'distance_asc':
      return num(a, 'distance_km') - num(b, 'distance_km');
    case 'duration_asc':
      return num(a, 'duration_min') - num(b, 'duration_min');
    case 'rating_desc':
      return num(b, 'product_rating', 0) - num(a, 'product_rating', 0);
    default:
      return 0;
  }
}

function renderResultCards(options, totalCount) {
  const grid = $('cards-grid');
  grid.innerHTML = '';

  if (!options.length) {
    grid.innerHTML = '<div class="loading-state"><p>No stores match the selected filters.</p></div>';
    $('results-count').textContent = `0 of ${totalCount} stores`;
    return;
  }

  options.forEach((opt, i) => {
    const card = buildResultCard(opt, i);
    grid.appendChild(card);
  });

  const label = options.length === totalCount
    ? `${options.length} store${options.length !== 1 ? 's' : ''}`
    : `${options.length} of ${totalCount} stores`;
  $('results-count').textContent = label;
  stagger(grid.querySelectorAll('.result-card'));
}

function applyResultsFiltersAndSort() {
  if (!state.results || state.results.error) return;

  const baseOptions = Array.isArray(state.results.all_options) ? state.results.all_options : [];
  if (!baseOptions.length) {
    $('cards-grid').innerHTML = '';
    $('results-count').textContent = '0 stores';
    return;
  }
  const maxDistance = parseOptionalNumber(state.resultMaxDistance);
  const maxTotal = parseOptionalNumber(state.resultMaxTotal);
  const minRating = toNum(state.resultMinRating, 0);

  let options = baseOptions.filter(opt => {
    const branchType = String(opt.branch_type || 'physical').toLowerCase();
    if (state.storeFilter && state.storeFilter !== 'all' && branchType !== state.storeFilter) {
      return false;
    }
    if (!Number.isNaN(maxDistance) && maxDistance >= 0 && toNum(opt.distance_km, Infinity) > maxDistance) {
      return false;
    }
    if (!Number.isNaN(maxTotal) && maxTotal >= 0 && toNum(opt.grand_total, Infinity) > maxTotal) {
      return false;
    }
    if (minRating > 0 && toNum(opt.product_rating, 0) < minRating) {
      return false;
    }
    return true;
  });

  const primary = state.resultSortPrimary || 'recommended';
  const secondary = state.resultSortSecondary || 'none';

  options = options
    .map((opt, idx) => ({ opt, idx }))
    .sort((left, right) => {
      const p = compareBySortMode(left.opt, right.opt, primary);
      if (p !== 0) return p;

      let usedSecondary = false;
      if (secondary !== 'none' && secondary !== primary) {
        const s = compareBySortMode(left.opt, right.opt, secondary);
        if (s !== 0) return s;
        usedSecondary = true;
      }

      if (primary !== 'recommended' || usedSecondary) {
        const fallback = compareBySortMode(left.opt, right.opt, 'total_asc');
        if (fallback !== 0) return fallback;
      }

      return left.idx - right.idx;
    })
    .map(item => item.opt);

  renderResultCards(options, baseOptions.length);
}

function syncResultsControls() {
  if ($('res-sort-primary')) $('res-sort-primary').value = state.resultSortPrimary;
  if ($('res-sort-secondary')) $('res-sort-secondary').value = state.resultSortSecondary;
  if ($('res-max-distance')) $('res-max-distance').value = state.resultMaxDistance;
  if ($('res-max-total')) $('res-max-total').value = state.resultMaxTotal;
  if ($('res-min-rating')) $('res-min-rating').value = String(state.resultMinRating);
}

function readResultsControls() {
  state.resultSortPrimary = $('res-sort-primary')?.value || 'recommended';
  state.resultSortSecondary = $('res-sort-secondary')?.value || 'none';
  state.resultMaxDistance = $('res-max-distance')?.value?.trim() || '';
  state.resultMaxTotal = $('res-max-total')?.value?.trim() || '';
  state.resultMinRating = toNum($('res-min-rating')?.value, 0);
}

function resetResultsFilters() {
  state.resultSortPrimary = 'recommended';
  state.resultSortSecondary = 'none';
  state.resultMaxDistance = '';
  state.resultMaxTotal = '';
  state.resultMinRating = 0;
  syncResultsControls();
  applyResultsFiltersAndSort();
}

function buildFallbackProductRow(item) {
  if (!item) return '';
  const name = esc(item.product || item.name || '');
  const price = fmt(toNum(item.price, 0));
  const store = esc(item.source_store || item.store || '');
  const type = esc(item.store_type || item.type || '');
  const link = safeUrl(item.source_url || '');
  const meta = store ? `${store}${type ? ` · ${type}` : ''}` : (type || '');
  const linkHtml = link && link !== '#' ? `<a href="${link}" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">View</a>` : '';
  return `
    <div class="fallback-product">
      <div>
        <div class="fallback-product-name">${name}</div>
        <div class="fallback-product-meta">${meta}</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <div class="fallback-product-price">Rs. ${price}</div>
        ${linkHtml}
      </div>
    </div>
  `;
}

function renderFallbackPanel(data, optionsCount) {
  const panel = $('results-fallback');
  if (!panel) return;

  const suggestions = Array.isArray(data?.suggestions) ? data.suggestions : [];
  const products = Array.isArray(data?.category_products) ? data.category_products : [];
  const noMatch = Boolean(data?.no_match);
  const fallbackUsed = Boolean(data?.fallback);
  const scope = data?.scope ? String(data.scope) : '';
  const categoryLabel = data?.category_label || data?.category || 'electronics';

  if (!noMatch && !fallbackUsed && !suggestions.length && !products.length && !scope) {
    panel.classList.add('hidden');
    panel.innerHTML = '';
    return;
  }

  const title = noMatch
    ? `No exact match for "${esc(data?.query || '')}".`
    : 'Showing recommended alternatives.';
  const description = noMatch
    ? `We couldn’t find the exact product. Here are similar ${esc(categoryLabel)} options and better search ideas.`
    : `Showing similar ${esc(categoryLabel)} options based on your search.`;

  let html = `
    <div class="results-fallback-title">${title}</div>
    <div class="results-fallback-text">${description}</div>
  `;

  if (scope) {
    html += `<div class="results-fallback-text">${esc(scope)}</div>`;
  }

  if (suggestions.length) {
    html += '<div class="results-fallback-chips">';
    html += suggestions.map(s => `<button type="button" class="hint-tag" data-suggest="${esc(s)}">${esc(s)}</button>`).join('');
    html += '</div>';
  }

  if (products.length && optionsCount === 0) {
    html += '<div class="results-fallback-products">';
    html += products.slice(0, 6).map(buildFallbackProductRow).join('');
    html += '</div>';
  }

  panel.innerHTML = html;
  panel.classList.remove('hidden');

  panel.querySelectorAll('[data-suggest]').forEach(btn => {
    btn.addEventListener('click', () => {
      const value = btn.getAttribute('data-suggest') || '';
      if (!value) return;
      $('inp-search').value = value;
      $('btn-search')?.click();
    });
  });
}

function bindResultsControls() {
  ensureResultsControlsMarkup();
  if (state.resultsControlsBound) return;
  state.resultsControlsBound = true;

  ['res-sort-primary', 'res-sort-secondary', 'res-max-distance', 'res-max-total', 'res-min-rating']
    .forEach(id => {
      const el = $(id);
      if (!el) return;
      const evt = el.tagName === 'SELECT' ? 'change' : 'input';
      el.addEventListener(evt, () => {
        readResultsControls();
        applyResultsFiltersAndSort();
      });
    });

  $('res-reset-filters')?.addEventListener('click', () => {
    resetResultsFilters();
  });
}

// ── Render Results ────────────────────────────────────────────────────────
function renderResults(data) {
  if (data.error && !data.no_match) { toast(data.error, 'error'); $('empty-state').classList.remove('hidden'); return; }

  const options = data.all_options || [];
  bindResultsControls();
  syncResultsControls();

  $('results-count').textContent = `${options.length} store${options.length !== 1 ? 's' : ''}`;
  $('results-title').textContent = data.query
    ? `Results — ${data.query}`
    : 'Results — Electronics';

  const adviceBox = $('advice-box');
  adviceBox.innerHTML = (data.advice || []).map(a => `<p>${esc(a)}</p>`).join('');
  if (!data.advice?.length) adviceBox.style.display = 'none';
  else adviceBox.style.display = '';

  $('results-list').classList.remove('hidden');
  $('empty-state').classList.add('hidden');
  state.results = data;
  renderFallbackPanel(data, options.length);
  if (options.length) {
    applyResultsFiltersAndSort();
  } else {
    $('cards-grid').innerHTML = '';
  }
}

function buildResultCard(opt, rank) {
  const el = document.createElement('div');
  el.className = `result-card${rank === 0 ? ' card-best' : ''}`;

  const rankNum = rank + 1;
  const rankClass = rankNum <= 3 ? `rank-${rankNum}` : 'rank-other';
  const storeType = opt.branch_type || 'physical';
  const typeBadge = storeType === 'online'
    ? '<span class="store-type-badge online">🌐 Online</span>'
    : '<span class="store-type-badge physical">🏬 Physical</span>';

  el.innerHTML = `
    <div class="card-rank ${rankClass}">${rankNum}</div>
    ${rank === 0 ? '<div class="best-badge">★ Best Pick</div>' : ''}
    <div class="card-branch-name">${esc(opt.branch_name)} ${typeBadge}</div>
    <div class="card-city">📍 ${esc(opt.city)} · ${esc(opt.address)}</div>

      <div class="card-product">
      <div class="card-product-name">${esc(opt.product)}</div>
      <div class="card-product-price">Rs. ${fmt(toNum(opt.product_price, 0))} <span>item price</span></div>
      <div class="card-stars">${stars(Math.max(0, Math.min(5, Math.round(toNum(opt.product_rating, 0)))))}</div>
    </div>

    <div class="card-metrics">
      <div class="metric">
        <div class="metric-label">Distance</div>
        <div class="metric-value text-accent">${fmt(toNum(opt.distance_km, 0), 1)} km</div>
      </div>
      <div class="metric">
        <div class="metric-label">Drive Time</div>
        <div class="metric-value">${formatDuration(opt.duration_min)}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Fuel Cost</div>
        <div class="metric-value text-amber">Rs. ${fmt(toNum(opt.fuel_cost, 0))}</div>
      </div>
    </div>

    <div class="card-total">
      <div>
      <div class="total-label">Grand Total (item + fuel)</div>
      <div style="font-size:0.72rem;color:var(--muted)">${opt.via === 'osrm' ? 'via OSRM road route' : 'estimated road distance'}</div>
      </div>
      <div class="total-value">Rs. ${fmt(toNum(opt.grand_total, 0))}</div>
    </div>

    <div class="card-actions">
      <button type="button" class="btn btn-outline btn-sm js-show-route">Show Route</button>
      <button type="button" class="btn btn-ghost btn-sm js-start-nav">Focus Route</button>
    </div>
  `;

  el.querySelector('.js-show-route')?.addEventListener('click', e => {
    e.stopPropagation();
    drawRouteToDestination(opt);
  });
  el.querySelector('.js-start-nav')?.addEventListener('click', e => {
    e.stopPropagation();
    startNavigationToDestination(opt);
  });

  el.addEventListener('click', () => openModal(opt));
  return el;
}

// ── Modal ─────────────────────────────────────────────────────────────────
function openModal(opt) {
  $('modal-body').innerHTML = `
    <div class="modal-branch-name">${esc(opt.branch_name)}</div>
    <div class="modal-address">📍 ${esc(opt.address)}</div>
    ${opt.phone ? `<div style="font-size:0.85rem;color:var(--muted);margin-bottom:1rem">📞 ${esc(opt.phone)}</div>` : ''}

    <div class="modal-section-title">Best Product Available</div>
    <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px;">
      <div style="font-size:0.9rem;font-weight:500;margin-bottom:8px">${esc(opt.product)}</div>
      <div style="font-family:var(--font-head);font-size:1.5rem;font-weight:800;color:var(--accent)">Rs. ${fmt(toNum(opt.product_price, 0))}</div>
      <div class="card-stars" style="margin-top:6px">${stars(Math.max(0, Math.min(5, Math.round(toNum(opt.product_rating, 0)))))}</div>
    </div>

    <div class="modal-section-title">Travel & Cost Breakdown</div>
    <div class="modal-cost-grid">
      <div class="modal-cost-item">
        <div class="modal-cost-label">Distance</div>
        <div class="modal-cost-value">${fmt(toNum(opt.distance_km, 0), 1)} km</div>
      </div>
      <div class="modal-cost-item">
        <div class="modal-cost-label">Driving Time</div>
        <div class="modal-cost-value">${formatDuration(opt.duration_min)}</div>
      </div>
      <div class="modal-cost-item">
        <div class="modal-cost-label">⛽ Fuel Cost</div>
        <div class="modal-cost-value" style="color:var(--amber)">Rs. ${fmt(toNum(opt.fuel_cost, 0))}</div>
      </div>
      <div class="modal-cost-item">
        <div class="modal-cost-label">Item Price</div>
        <div class="modal-cost-value">Rs. ${fmt(toNum(opt.product_price, 0))}</div>
      </div>
      <div class="modal-cost-item full total">
        <div class="modal-cost-label">Grand Total (All-In)</div>
        <div class="modal-cost-value">Rs. ${fmt(toNum(opt.grand_total, 0))}</div>
      </div>
    </div>

    <div class="card-actions" style="margin-top:12px;">
      <button type="button" class="btn btn-outline btn-sm" id="modal-show-route">Show Route</button>
      <button type="button" class="btn btn-ghost btn-sm" id="modal-start-nav">Focus Route</button>
    </div>
    <div style="margin-top:10px;font-size:0.75rem;color:var(--muted)">
      Distances calculated ${opt.via === 'osrm' ? 'via OSRM road route' : 'via estimated road distance'}
    </div>
  `;

  $('modal-show-route')?.addEventListener('click', () => drawRouteToDestination(opt));
  $('modal-start-nav')?.addEventListener('click', () => startNavigationToDestination(opt));
  $('modal-backdrop').classList.remove('hidden');
}

$('modal-close').addEventListener('click', () => $('modal-backdrop').classList.add('hidden'));
$('modal-backdrop').addEventListener('click', e => {
  if (e.target === $('modal-backdrop')) $('modal-backdrop').classList.add('hidden');
});

// ── Catalog ───────────────────────────────────────────────────────────────
async function loadCatalog(filter) {
  const currentFilter = filter || state.catalogFilter;
  state.catalogFilter = currentFilter;

  const grid = $('catalog-grid');
  grid.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading products from 30+ stores…</p></div>';

  try {
    let products;
    if (state.allProducts.length > 0) {
      products = state.allProducts;
    } else {
      const r = await fetch('/api/products/electronics?pages=2');
      const data = await r.json();
      products = data.products || [];
      state.allProducts = products;
    }

    // Filter by store type
    if (currentFilter !== 'all') {
      products = products.filter(p => p.store_type === currentFilter);
    }

    renderCatalogProducts(products);
  } catch (err) {
    grid.innerHTML = `<div class="loading-state" style="color:var(--red)">⚠ ${esc(err.message)}</div>`;
  }
}

// Catalog filter chips
$$('.catalog-header .chip[data-filter]').forEach(chip => {
  chip.addEventListener('click', () => {
    $$('.catalog-header .chip[data-filter]').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    loadCatalog(chip.dataset.filter);
  });
});

$('btn-refresh-catalog').addEventListener('click', () => {
  state.allProducts = [];
  loadCatalog();
});

function renderCatalogProducts(prods) {
  const grid = $('catalog-grid');
  grid.innerHTML = '';

  if (!prods || !prods.length) {
    grid.innerHTML = '<div class="loading-state"><span style="font-size:2rem">📭</span><p>No products found.</p></div>';
    return;
  }

  prods.forEach((p, i) => {
    const el = document.createElement('div');
    el.className = 'product-card';
    el.style.animationDelay = `${i * 30}ms`;
    const typeBadge = p.store_type === 'online'
      ? '<span class="store-type-badge online">🌐</span>'
      : '<span class="store-type-badge physical">🏬</span>';
    el.innerHTML = `
      <div class="product-source">${typeBadge} ${esc(p.source_store || 'Unknown')}</div>
      <div class="product-name">${esc(p.product)}</div>
      <div class="product-price">Rs. ${fmt(toNum(p.price, 0))}</div>
      <div class="product-stars">${stars(Math.max(0, Math.min(5, Math.round(toNum(p.rating, 4)))))}</div>
      ${p.description ? `<div class="product-desc">${esc(p.description)}</div>` : ''}
      <div style="margin-top:auto; padding-top:10px;">
        <a href="${safeUrl(p.source_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="font-size:0.7rem; padding:4px 8px; width:100%; border-radius:6px; text-decoration:none; display:inline-block; text-align:center">View on Store</a>
      </div>
    `;
    grid.appendChild(el);
  });
}

// ── Stores View ──────────────────────────────────────────────────────────
async function loadStoresView(filter = 'all') {
  const grid = $('stores-grid');
  grid.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading stores…</p></div>';

  try {
    let stores;
    if (state.allStores.length > 0) {
      stores = state.allStores;
    } else {
      const r = await fetch('/api/stores');
      const data = await r.json();
      stores = data.stores || [];
      state.allStores = stores;
    }

    if (filter !== 'all') {
      stores = stores.filter(s => s.type === filter);
    }

    grid.innerHTML = '';
    stores.forEach((s, i) => {
      const el = document.createElement('div');
      el.className = 'store-card';
      el.style.animationDelay = `${i * 50}ms`;
      const typeBadge = s.type === 'online'
        ? '<span class="store-type-badge online">🌐 Online</span>'
        : '<span class="store-type-badge physical">🏬 Physical</span>';
      const hasUrl = s.url ? `<a href="${safeUrl(s.url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="font-size:0.75rem; padding:4px 10px; text-decoration:none; display:inline-block; border-radius:6px; margin-top:8px">Visit Website ↗</a>` : '<span style="font-size:0.75rem; color:var(--muted)">No website</span>';

      let distanceInfo = '';
      if (s.type === 'physical' && state.userLat && state.userLon) {
        const dist = haversineKm(state.userLat, state.userLon, s.lat, s.lon);
        const roadDist = (dist * 1.3).toFixed(1);
        const fuelCost = Math.round(roadDist * 25); // Rs 25/km
        distanceInfo = `
          <div class="store-distance">
            <span>📏 ~${roadDist} km</span>
            <span>⛽ ~Rs. ${fmt(fuelCost)}</span>
          </div>
        `;
      }

      let storeActions = '';
      if (s.type === 'physical') {
        storeActions = `
          <div class="store-actions">
            <button type="button" class="btn btn-outline btn-sm js-store-route">Show Route</button>
            <button type="button" class="btn btn-ghost btn-sm js-store-nav">Focus Route</button>
          </div>
        `;
      }

      el.innerHTML = `
        <div class="store-header">
          <div class="store-name">${esc(s.name)}</div>
          ${typeBadge}
        </div>
        <div class="store-city">📍 ${esc(s.city)} — ${esc(s.address)}</div>
        ${s.phone ? `<div class="store-phone">📞 ${esc(s.phone)}</div>` : ''}
        ${distanceInfo}
        ${storeActions}
        ${hasUrl}
      `;
      if (s.type === 'physical') {
        const target = {
          name: s.name,
          lat: s.lat,
          lon: s.lon,
        };
        el.querySelector('.js-store-route')?.addEventListener('click', e => {
          e.stopPropagation();
          drawRouteToDestination(target);
        });
        el.querySelector('.js-store-nav')?.addEventListener('click', e => {
          e.stopPropagation();
          startNavigationToDestination(target);
        });
      }
      grid.appendChild(el);
    });
  } catch (err) {
    grid.innerHTML = `<div class="loading-state" style="color:var(--red)">⚠ ${esc(err.message)}</div>`;
  }
}

// Store filter chips
$$('[data-sfilter]').forEach(chip => {
  chip.addEventListener('click', () => {
    $$('[data-sfilter]').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    loadStoresView(chip.dataset.sfilter);
  });
});

// ── Haversine (client-side for store distance display) ───────────────────
function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

async function drawRouteToDestination(target) {
  const user = getUserLocation();
  if (!user) {
    toast('Set your location first (Detect or search by area).', 'error');
    return;
  }

  const destLat = toNum(target?.lat, NaN);
  const destLon = toNum(target?.lon, NaN);
  const destName = String(target?.branch_name || target?.name || 'Destination');
  if (Number.isNaN(destLat) || Number.isNaN(destLon)) {
    toast('Destination coordinates are unavailable.', 'error');
    return;
  }

  $('modal-backdrop')?.classList.add('hidden');

  try {
    const qs = new URLSearchParams({
      start_lat: String(user.lat),
      start_lon: String(user.lon),
      end_lat: String(destLat),
      end_lon: String(destLon),
    });
    const response = await fetch(`/api/location/route?${qs.toString()}`);
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || 'Could not calculate route');
    }

    ensureMapReady();
    openMapView();
    if (!state.map) return;
    setTimeout(() => state.map.invalidateSize(), 60);

    const points = Array.isArray(payload.geometry) ? payload.geometry : [];
    if (points.length < 2) throw new Error('Route path is unavailable');

    if (state.routeLayer) state.routeLayer.remove();
    state.routeLayer = window.L.polyline(points, {
      color: '#00d4ff',
      weight: 5,
      opacity: 0.9,
    }).addTo(state.map);
    state.routeTarget = { lat: destLat, lon: destLon, name: destName };
    const navBtn = $('btn-start-route-nav');
    if (navBtn) navBtn.disabled = false;

    const bounds = state.routeLayer.getBounds();
    if (bounds.isValid()) {
      state.map.fitBounds(bounds, { padding: [40, 40] });
    } else {
      state.map.setView([destLat, destLon], 13);
    }

    const routeVia = payload.via === 'osrm' ? 'OSRM road route' : 'estimated fallback route';
    setRouteSummary(
      `<strong>${esc(destName)}</strong><br>` +
      `${fmt(payload.distance_km, 2)} km · ${formatDuration(payload.duration_min)}<br>` +
      `<span style="color:var(--muted)">${esc(routeVia)}</span>`
    );
    toast('Route displayed on map.', 'success');
  } catch (err) {
    // Final fallback: draw a straight path so user can still navigate quickly.
    ensureMapReady();
    openMapView();
    if (state.map) {
      if (state.routeLayer) state.routeLayer.remove();
      state.routeLayer = window.L.polyline(
        [
          [user.lat, user.lon],
          [destLat, destLon],
        ],
        { color: '#00d4ff', weight: 4, opacity: 0.8, dashArray: '8 8' },
      ).addTo(state.map);
      state.routeTarget = { lat: destLat, lon: destLon, name: destName };
      const navBtn = $('btn-start-route-nav');
      if (navBtn) navBtn.disabled = false;
      state.map.fitBounds(state.routeLayer.getBounds(), { padding: [40, 40] });
      const approxKm = haversineKm(user.lat, user.lon, destLat, destLon) * 1.3;
      const approxMin = (approxKm / 30) * 60;
      setRouteSummary(
        `<strong>${esc(destName)}</strong><br>` +
        `${fmt(approxKm, 2)} km · ${fmt(approxMin, 0)} min<br>` +
        `<span style="color:var(--muted)">Estimated fallback route</span>`
      );
    }
    toast(`Route fallback used: ${err.message}`, 'error');
  }
}

function startNavigationToDestination(target) {
  if (!target) {
    toast('Select a route first.', 'error');
    return;
  }
  drawRouteToDestination(target);
}

// ── Map / Branch Legend ──────────────────────────────────────────────────
function getPhysicalBranches() {
  return state.branches
    .filter(b => b.type === 'physical')
    .map(b => ({
      ...b,
      lat: toNum(b.lat, NaN),
      lon: toNum(b.lon, NaN),
    }))
    .filter(b => !Number.isNaN(b.lat) && !Number.isNaN(b.lon));
}

function ensureMapReady() {
  if (state.mapReady) return;
  const canvas = $('map-canvas');
  if (!canvas) return;
  if (typeof window.L === 'undefined') {
    canvas.innerHTML = '<div class="loading-state"><p>Map library failed to load.</p></div>';
    return;
  }

  state.map = window.L.map(canvas, { zoomControl: true }).setView([30.3753, 69.3451], 6);
  window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(state.map);
  state.mapReady = true;

  renderBranchMarkers();
  updateUserMarker();
}

function renderBranchMarkers() {
  if (!state.map) return;
  for (const marker of state.branchMarkers.values()) {
    marker.remove();
  }
  state.branchMarkers.clear();

  const branches = getPhysicalBranches();
  branches.forEach(branch => {
    const marker = window.L.marker([branch.lat, branch.lon], { title: branch.name }).addTo(state.map);
    const safeUrlValue = safeUrl(branch.url);
    const popupLink = safeUrlValue !== '#'
      ? `<a href="${safeUrlValue}" target="_blank" rel="noopener noreferrer">Visit website</a>`
      : '<span style="color:#8ca298">No website</span>';

    marker.bindPopup(`
      <div style="min-width:210px">
        <strong>${esc(branch.name)}</strong><br>
        <span style="color:#8ca298">${esc(branch.city)} · ${esc(branch.address)}</span><br>
        ${popupLink}
      </div>
    `);
    state.branchMarkers.set(branch.id, marker);
  });
}

function focusBranchOnMap(branch) {
  ensureMapReady();
  if (!state.map) return;
  const marker = state.branchMarkers.get(branch.id);
  if (!marker) return;
  state.map.setView([branch.lat, branch.lon], 13, { animate: true });
  marker.openPopup();
}

function updateUserMarker() {
  if (!state.map || state.userLat === null || state.userLon === null) return;
  const latLng = [state.userLat, state.userLon];

  if (!state.userMarker) {
    state.userMarker = window.L.circleMarker(latLng, {
      radius: 8,
      color: '#00ff95',
      fillColor: '#00ff95',
      fillOpacity: 0.85,
      weight: 2,
    }).addTo(state.map);
    state.userMarker.bindPopup('Your selected location');
  } else {
    state.userMarker.setLatLng(latLng);
  }
}

function buildBranchLegend() {
  const list = $('branch-legend-list');
  if (!list) return;
  list.innerHTML = '';

  const branches = getPhysicalBranches();

  if (!branches.length) {
    list.innerHTML = '<p style="font-size:0.75rem;color:var(--muted)">Loading store locations...</p>';
    return;
  }

  branches.forEach((b, i) => {
    const item = document.createElement('div');
    item.className = 'branch-legend-item';
    item.innerHTML = `
      <div class="legend-dot" style="background:hsl(${(i * 25) % 360},80%,60%)"></div>
      <div>
        <div class="legend-name">${esc(b.name)}</div>
        <div class="legend-cats">${esc(b.city)}</div>
      </div>
    `;
    item.addEventListener('click', () => focusBranchOnMap(b));
    list.appendChild(item);
  });
}

window.initMap = function (realApi = true) {
  ensureMapReady();
};

$('btn-clear-route')?.addEventListener('click', () => {
  clearActiveRoute();
});
$('btn-start-route-nav')?.addEventListener('click', () => {
  if (!state.routeTarget) {
    toast('Select a route first.', 'error');
    return;
  }
  startNavigationToDestination(state.routeTarget);
});

// ── Search ──────────────────────────────────────────────────────────────
// Enter key search
$('inp-search')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') $('btn-search')?.click();
});

// ── Sub-category hints ───────────────────────────────────────────────────
$$('.hint-tag').forEach(tag => {
  tag.addEventListener('click', () => {
    $('inp-search').value = tag.dataset.q;
    $('btn-search').click();
  });
});

// ── Utility ────────────────────────────────────────────────────────────────
function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ── Init ───────────────────────────────────────────────────────────────────
(async function init() {
  // Preload branches for the legend
  try {
    const r = await fetch('/api/branches');
    const d = await r.json();
    state.branches = d.branches || [];
    buildBranchLegend();
    renderBranchMarkers();
  } catch (_) { }

  const restored = restoreLastLocation();
  if (!restored) {
    $('inp-location-name').value = '';
    $('inp-lat').value = '';
    $('inp-lon').value = '';
  }
  setChatEnabled(false, 'Run a search to start asking questions.');
  ensureMapReady();
  fetchAiInsightsPanel(false);

  // try to detect user location automatically (quietly)
  if (!restored && navigator.geolocation && window.isSecureContext) {
    detectLocationViaGps(false);
  }
})();


// ── AI Insights Dashboard Panel ──────────────────────────────────────────────
function renderAiInsightsList(targetId, items, rowBuilder, emptyMessage) {
  const listEl = $(targetId);
  if (!listEl) return;

  if (!Array.isArray(items) || items.length === 0) {
    listEl.innerHTML = `<li class="ai-insights-placeholder">${esc(emptyMessage)}</li>`;
    return;
  }

  listEl.innerHTML = items.slice(0, 6).map(rowBuilder).join('');
}

function renderAiInsightsPanel(data) {
  renderAiInsightsList(
    'insights-trending-list',
    data?.trending_products,
    item => `
      <li>
        <span class="ai-insights-item-name">${esc(item.product || '')}</span>
        <span class="ai-insights-item-meta">${esc(item.trend || 'stable')} · Rs. ${fmt(toNum(item.avg_price, 0))}</span>
      </li>
    `,
    'No trending signals yet.',
  );

  renderAiInsightsList(
    'insights-price-drops-list',
    data?.biggest_price_drops,
    item => `
      <li>
        <span class="ai-insights-item-name">${esc(item.product || '')}</span>
        <span class="ai-insights-item-meta">↓ ${toNum(item.discount_percent, 0)}% · Rs. ${fmt(toNum(item.current_price, 0))}</span>
      </li>
    `,
    'No significant price drops detected.',
  );

  renderAiInsightsList(
    'insights-best-deals-list',
    data?.best_deals_today,
    item => `
      <li>
        <span class="ai-insights-item-name">${esc(item.product || '')}</span>
        <span class="ai-insights-item-meta">${esc(item.store || 'Store')} · Rs. ${fmt(toNum(item.price, 0))}</span>
      </li>
    `,
    'No active AI deals for now.',
  );

  renderAiInsightsList(
    'insights-popular-categories-list',
    data?.popular_categories,
    item => `
      <li>
        <span class="ai-insights-item-name">${esc(item.category || 'Electronics')}</span>
        <span class="ai-insights-item-meta">${fmt(toNum(item.count, 0))} mentions</span>
      </li>
    `,
    'Category activity is still building.',
  );
}

async function fetchAiInsightsPanel(forceRefresh = false, coords = null) {
  const panel = $('ai-insights-dashboard');
  if (!panel) return;

  const refreshBtn = $('btn-refresh-ai-insights');
  if (refreshBtn) {
    refreshBtn.disabled = true;
    if (forceRefresh) refreshBtn.textContent = 'Refreshing…';
  }

  try {
    const latCandidate = coords?.lat ?? state.userLat ?? parseOptionalNumber($('inp-lat')?.value);
    const lonCandidate = coords?.lon ?? state.userLon ?? parseOptionalNumber($('inp-lon')?.value);

    const params = new URLSearchParams();
    if (!Number.isNaN(latCandidate)) params.set('user_lat', String(latCandidate));
    if (!Number.isNaN(lonCandidate)) params.set('user_lon', String(lonCandidate));
    if (forceRefresh) params.set('refresh', '1');

    const url = params.toString() ? `/ai-insights?${params.toString()}` : '/ai-insights';
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Could not load AI insights');

    renderAiInsightsPanel(payload);
  } catch (err) {
    renderAiInsightsList('insights-trending-list', [], () => '', 'AI insights unavailable right now.');
    renderAiInsightsList('insights-price-drops-list', [], () => '', 'AI insights unavailable right now.');
    renderAiInsightsList('insights-best-deals-list', [], () => '', 'AI insights unavailable right now.');
    renderAiInsightsList('insights-popular-categories-list', [], () => '', 'AI insights unavailable right now.');
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = 'Refresh Insights';
    }
  }
}

// ── AI Chat ───────────────────────────────────────────────────────────────
function buildRecommendationContext() {
  const best = state.results?.best_overall;
  if (!best) return '';
  const product = String(best.product || '').trim();
  if (!product) return '';
  const store = String(best.branch_name || '').trim();
  const price = toNum(best.product_price, Number.NaN);
  let line = product;
  if (store) line += ` at ${store}`;
  if (!Number.isNaN(price)) line += ` for Rs. ${fmt(price, 0)}`;
  return line;
}

function appendChatMessage(role, content, allowHtml = false) {
  const body = $('ai-chat-body');
  if (!body) return null;
  const empty = $('ai-chat-empty');
  if (empty) empty.remove();
  const msg = document.createElement('div');
  msg.className = `ai-chat-msg ${role}`;
  if (allowHtml) {
    msg.innerHTML = content;
  } else {
    msg.textContent = content;
  }
  body.appendChild(msg);
  body.scrollTop = body.scrollHeight;
  return msg;
}

function formatChatResponse(data) {
  if (!data) return esc('No response available.');
  if (data.error) return `<div><strong>Error:</strong> ${esc(data.error)}</div>`;
  if (data.message) {
    const text = esc(String(data.message));
    return `<div>${text.replace(/\n{2,}/g, '<br><br>').replace(/\n/g, '<br>')}</div>`;
  }

  const parts = [];
  if (data.summary) {
    parts.push(`<div><strong>Summary:</strong> ${esc(data.summary)}</div>`);
  }
  if (data.recommended_product) {
    parts.push(`<div><strong>Recommended:</strong> ${esc(data.recommended_product)}</div>`);
  }
  if (data.reason) {
    parts.push(`<div><strong>Reasoning:</strong> ${esc(data.reason)}</div>`);
  }
  if (Array.isArray(data.alternatives) && data.alternatives.length) {
    const items = data.alternatives.map(item => `<li>${esc(item)}</li>`).join('');
    parts.push(`<div><strong>Alternatives:</strong><ul>${items}</ul></div>`);
  }
  if (Array.isArray(data.suggestions) && data.suggestions.length) {
    const items = data.suggestions.map(item => `<li>${esc(item)}</li>`).join('');
    parts.push(`<div><strong>Search ideas:</strong><ul>${items}</ul></div>`);
  }
  if (data.scope) {
    parts.push(`<div><strong>Scope:</strong> ${esc(data.scope)}</div>`);
  }
  if (!parts.length) {
    return esc('No recommendation details returned.');
  }
  return parts.join('');
}

async function sendChatMessage(message) {
  if (state.chatBusy) return;
  const input = $('ai-chat-input');
  const sendBtn = $('ai-chat-send');

  state.chatBusy = true;
  if (input) input.disabled = true;
  if (sendBtn) sendBtn.disabled = true;

  appendChatMessage('user', message);
  const pending = appendChatMessage('bot', 'Thinking…');

  try {
    const location = getUserLocation() || { lat: state.userLat, lon: state.userLon };
    const budget = $('inp-budget')?.value ? parseFloat($('inp-budget').value) : null;
    const priority = document.querySelector('[name="priority"]:checked')?.value || 'total_cost';
    const context = buildRecommendationContext();
    const query = context ? `${message}\nContext: Recommended product is ${context}.` : message;

    const payload = {
      query,
      store_filter: state.storeFilter,
      priority,
      pages: 1,
    };
    if (budget !== null && !Number.isNaN(budget)) payload.budget = budget;
    if (location?.lat !== null && location?.lat !== undefined) payload.user_lat = location.lat;
    if (location?.lon !== null && location?.lon !== undefined) payload.user_lon = location.lon;

    const data = await post('/api/ai-chat', payload);
    if (pending) pending.innerHTML = formatChatResponse(data);
  } catch (err) {
    if (pending) pending.innerHTML = `<strong>Chat error:</strong> ${esc(err.message || 'Unable to reach AI chat.')}`;
  } finally {
    state.chatBusy = false;
    if (input) input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    if (input) input.focus();
  }
}

$('ai-chat-form')?.addEventListener('submit', e => {
  e.preventDefault();
  const input = $('ai-chat-input');
  if (!input || input.disabled) return;
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  sendChatMessage(message);
});

$('btn-refresh-ai-insights')?.addEventListener('click', () => {
  fetchAiInsightsPanel(true);
});


// ── AI Intelligence Panel ─────────────────────────────────────────────────────

async function fetchIntelligence(params) {
  const aiPanel = $('ai-panel');
  aiPanel.classList.remove('hidden');
  aiPanel.innerHTML = `
    <div class="ai-panel-header">
      <h3 class="ai-panel-title">\u{1F9E0} AI Decision Intelligence</h3>
      <span class="ai-badge">AI Powered</span>
    </div>
    <div class="ai-loading">
      <div class="spinner"></div>
      Analyzing prices, travel costs, and market trends...
    </div>
  `;

  try {
    const data = await post('/api/intelligence', params);
    renderIntelligence(data);
  } catch (err) {
    aiPanel.innerHTML = `
      <div class="ai-panel-header">
        <h3 class="ai-panel-title">\u{1F9E0} AI Decision Intelligence</h3>
        <span class="ai-badge">AI Powered</span>
      </div>
      <div class="ai-section ai-summary" style="border-color:rgba(244,63,94,0.3);">
        \u26A0\uFE0F Could not generate AI insights: ${esc(err.message)}
      </div>
    `;
  }
}

function renderIntelligence(data) {
  const aiPanel = $('ai-panel');
  if (!data || data.error) {
    aiPanel.classList.add('hidden');
    return;
  }

  // Rebuild panel structure
  aiPanel.innerHTML = `
    <div class="ai-panel-header">
      <h3 class="ai-panel-title">\u{1F9E0} AI Decision Intelligence</h3>
      <span class="ai-badge">AI Powered</span>
    </div>
    <div class="ai-section ai-summary" id="ai-summary"></div>
    <div class="ai-section ai-best-option" id="ai-best-option"></div>
    
    <!-- Quality Score + Price Eval + Demand row -->
    <div class="ai-trio-row">
      <div class="ai-section ai-quality-score" id="ai-quality-score"></div>
      <div class="ai-section ai-price-eval" id="ai-price-eval"></div>
      <div class="ai-section ai-demand-trend" id="ai-demand-trend"></div>
    </div>

    <!-- Buying Advice -->
    <div class="ai-section ai-buying-advice" id="ai-buying-advice"></div>

    <!-- Risk Warnings -->
    <div class="ai-section ai-risk-warnings hidden" id="ai-risk-warnings"></div>

    <!-- Model Comparison -->
    <div class="ai-section ai-model-comparison" id="ai-model-comparison"></div>

    <div class="ai-row">
      <div class="ai-section ai-prediction" id="ai-prediction"></div>
      <div class="ai-section ai-savings" id="ai-savings"></div>
    </div>
    <div class="ai-section ai-cost-breakdown" id="ai-cost-breakdown"></div>
    <div class="ai-section ai-insights" id="ai-insights"></div>
    <details class="ai-section ai-reasoning-details">
      <summary class="ai-reasoning-toggle">\u{1F9E0} AI Reasoning \u2014 How this decision was made</summary>
      <div class="ai-reasoning-content" id="ai-reasoning"></div>
    </details>
    <div class="ai-section ai-tips" id="ai-tips">
      <h4 class="ai-section-title">\u{1F4A1} Smart Tips</h4>
      <div class="ai-tips-list" id="ai-tips-list"></div>
    </div>
  `;
  aiPanel.classList.remove('hidden');

  // Render each section
  renderAiSummary(data.summary);
  renderAiBestOption(data.best_option);
  renderAiQualityScore(data.quality_score);
  renderAiPriceEvaluation(data.price_evaluation);
  renderAiDemandTrend(data.demand_trend);
  renderAiBuyingAdvice(data.buying_advice);
  renderAiRiskWarnings(data.risk_warnings);
  renderAiModelComparison(data.model_comparison);
  renderAiPrediction(data.price_prediction);
  renderAiSavings(data.savings_opportunity);
  renderAiCostBreakdown(data.cost_breakdown);
  renderAiInsights(data.insights);
  renderAiReasoning(data.ai_reasoning);
  renderAiTips(data.smart_tips);
}

// helper used by multiple renderers to handle bold, lists, paragraphs
function formatAiText(raw) {
  if (!raw) return '';
  let html = esc(raw).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const lines = html.split(/\r?\n/);
  let out = '';
  let inList = false;
  lines.forEach(line => {
    if (/^\s*[-\*•]\s+/.test(line)) {
      if (!inList) { out += '<ul>'; inList = true; }
      out += `<li>${line.replace(/^\s*[-\*•]\s+/, '')}</li>`;
    } else {
      if (inList) { out += '</ul>'; inList = false; }
      if (line.trim() === '') {
        out += '<br/>';
      } else {
        out += `<p>${line}</p>`;
      }
    }
  });
  if (inList) out += '</ul>';
  return out;
}

function renderAiSummary(summary) {
  const el = $('ai-summary');
  if (!el || !summary) return;
  el.innerHTML = formatAiText(summary);
}

function renderAiBestOption(opt) {
  const el = $('ai-best-option');
  if (!el || !opt) return;
  const typeClass = opt.store_type === 'online' ? 'online' : 'physical';
  const typeLabel = opt.store_type === 'online' ? '\u{1F310} Online' : '\u{1F3EC} Physical';

  el.innerHTML = `
    <h4 class="ai-section-title">\u{1F3C6} Best Option</h4>
    <div class="ai-best-option-header">
      <span class="ai-best-option-store">${esc(opt.store)}</span>
      <span class="store-type-badge ${typeClass} ai-best-option-type">${typeLabel}</span>
    </div>
    <div class="ai-best-option-meta">
      <span>\u{1F4CD} ${esc(opt.city)} \u2014 ${esc(opt.address)}</span>
      <span>\u{1F4E6} ${esc(opt.product)}</span>
      <span>\u{1F4B0} Item: Rs. ${fmt(toNum(opt.item_price, 0))}</span>
      <span>\u{1F697} Fuel: Rs. ${fmt(toNum(opt.travel_cost, 0))}</span>
      <span>\u{1F4CF} ${toNum(opt.distance_km, 0).toFixed(1)} km \u00B7 ${formatDuration(opt.duration_min)}</span>
    </div>
    <div class="ai-best-option-total">Rs. ${fmt(toNum(opt.total_cost, 0))}</div>
  `;
}

function renderAiPrediction(pred) {
  const el = $('ai-prediction');
  if (!el || !pred) return;

  const dirMap = {
    up: { label: '\u2191 Prices May Rise', cls: 'up' },
    down: { label: '\u2193 Prices May Drop', cls: 'down' },
    stable: { label: '\u2194 Prices Stable', cls: 'stable' },
  };
  const info = dirMap[pred.direction] || dirMap.stable;
  const explanationHtml = esc(pred.explanation || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  el.innerHTML = `
    <h4 class="ai-section-title">\u{1F4C8} Price Prediction</h4>
    <div class="prediction-direction">
      <span class="prediction-badge ${info.cls}">${info.label}</span>
      <span class="prediction-probability">${pred.probability || 0}%</span>
    </div>
    <div class="prediction-explanation">${explanationHtml}</div>
  `;
}

function renderAiSavings(sav) {
  const el = $('ai-savings');
  if (!el || !sav) return;

  const maxSavings = Math.max(toNum(sav.max_savings_on_price, 0), toNum(sav.max_savings_on_total, 0));
  const explanationHtml = esc(sav.explanation || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  el.innerHTML = `
    <h4 class="ai-section-title">\u{1F4B0} Savings Opportunity</h4>
    <div class="savings-amount">Up to Rs. ${fmt(maxSavings)}</div>
    <div class="savings-detail">${explanationHtml}</div>
  `;
}

function renderAiCostBreakdown(cb) {
  const el = $('ai-cost-breakdown');
  if (!el || !cb) return;

  const total = toNum(cb.grand_total, 1);
  const item = toNum(cb.item_price, 0);
  const fuel = toNum(cb.fuel_cost, 0);
  const durationLabel = cb.duration_label || formatDuration(cb.duration_min);

  const itemPct = total > 0 ? Math.round((item / total) * 100) : 100;
  const fuelPct = total > 0 ? Math.round((fuel / total) * 100) : 0;

  el.innerHTML = `
    <h4 class="ai-section-title">\u{1F4CA} Cost Breakdown</h4>
    <div class="cost-bar-container">
      <div class="cost-bar">
        <div class="cost-bar-segment item" style="width:${itemPct}%">${itemPct}%</div>
        ${fuelPct > 0 ? `<div class="cost-bar-segment fuel" style="width:${fuelPct}%">${fuelPct}%</div>` : ''}
      </div>
      <div class="cost-legend">
        <div class="cost-legend-item">
          <div class="cost-legend-dot" style="background:var(--accent)"></div>
          <span>Item Price: Rs. ${fmt(item)} (${itemPct}%)</span>
        </div>
        <div class="cost-legend-item">
          <div class="cost-legend-dot" style="background:#fbbf24"></div>
          <span>Fuel: Rs. ${fmt(fuel)} (${fuelPct}%)</span>
        </div>
        ${durationLabel && durationLabel !== '0m' ? `
        <div class="cost-legend-item">
          <div class="cost-legend-dot" style="background:#7dd3fc"></div>
          <span>Travel time: ${durationLabel}</span>
        </div>` : ''}
      </div>
    </div>
  `;
}

function renderAiInsights(insights) {
  const el = $('ai-insights');
  if (!el || !insights) return;

  const keys = Object.keys(insights);
  if (!keys.length) {
    el.style.display = 'none';
    return;
  }

  el.innerHTML = '<h4 class="ai-section-title" style="grid-column:1/-1">\u{1F50D} Market Insights</h4>' +
    keys.map(key => {
      const item = insights[key];
      return `
        <div class="ai-insight-card">
          <div class="ai-insight-label">${esc(item.label || '')}</div>
          <div class="ai-insight-value">${esc(item.value || '')}</div>
          <div class="ai-insight-detail">${esc(item.detail || '')}</div>
        </div>
      `;
    }).join('');
}

function renderAiReasoning(reasoning) {
  const el = $('ai-reasoning');
  if (!el || !reasoning) return;
  el.innerHTML = formatAiText(reasoning);
}

function renderAiTips(tips) {
  const el = $('ai-tips-list');
  if (!el || !tips || !tips.length) return;

  el.innerHTML = tips.map(tip => {
    const html = esc(tip).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return `<div class="ai-tip-item">${html}</div>`;
  }).join('');
}


// ── New AI Module Renderers ─────────────────────────────────────────────────

function renderAiQualityScore(qs) {
  const el = $('ai-quality-score');
  if (!el || !qs) return;

  const score = toNum(qs.score, 5);
  const circumference = 2 * Math.PI * 35;
  const offset = circumference - (score / 10) * circumference;
  const color = score >= 8 ? 'var(--green)' : score >= 6 ? 'var(--accent)' : score >= 4 ? 'var(--amber)' : '#fb7185';

  el.innerHTML = `
    <h4 class="ai-section-title">${qs.emoji || '\u2B50'} Quality Score</h4>
    <div class="quality-score-ring">
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle class="ring-bg" cx="40" cy="40" r="35"/>
        <circle class="ring-fill" cx="40" cy="40" r="35"
          stroke="${color}"
          stroke-dasharray="${circumference}"
          stroke-dashoffset="${offset}"/>
      </svg>
      <div class="quality-score-number" style="color:${color}">${score}</div>
    </div>
    <div class="quality-score-verdict">${esc(qs.verdict || '')}</div>
    <div class="quality-score-breakdown">${(qs.breakdown || []).map(b => esc(b)).join('<br>')}</div>
  `;
}

function renderAiPriceEvaluation(pe) {
  const el = $('ai-price-eval');
  if (!el || !pe) return;

  const color = pe.color || 'amber';
  const explanationHtml = esc(pe.explanation || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  el.innerHTML = `
    <h4 class="ai-section-title">${pe.emoji || '\u{1F3F7}'} Price Evaluation</h4>
    <div class="price-eval-badge ${color}">${esc(pe.label || 'Unknown')}</div>
    <div class="price-eval-detail">${explanationHtml}</div>
  `;
}

function renderAiDemandTrend(dt) {
  const el = $('ai-demand-trend');
  if (!el || !dt) return;

  el.innerHTML = `
    <h4 class="ai-section-title">${dt.emoji || '\u{1F4CA}'} Demand & Popularity</h4>
    <div class="demand-level">${esc(dt.level || 'Unknown')}</div>
    <div class="demand-signals">${(dt.signals || []).map(s => esc(s)).join('<br>')}</div>
  `;
}

function renderAiBuyingAdvice(ba) {
  const el = $('ai-buying-advice');
  if (!el || !ba) return;

  const color = ba.color || 'amber';
  el.className = `ai-section ai-buying-advice ${color}`;

  const reasonsHtml = (ba.reasons || []).map(r =>
    `<div class="buying-advice-reason">${esc(r)}</div>`
  ).join('');

  let altHtml = '';
  if (ba.alternative) {
    altHtml = `<div class="buying-advice-alt">
      \u{1F4A1} <strong>Alternative:</strong> ${esc(ba.alternative.note || '')}
    </div>`;
  }

  el.innerHTML = `
    <div class="buying-advice-header">
      <span style="font-size:1.5rem">${ba.emoji || '\u{1F914}'}</span>
      <span class="buying-advice-action">${esc(ba.action || '')}</span>
      <span class="buying-advice-confidence">${ba.confidence || 0}% confidence</span>
    </div>
    <div class="buying-advice-headline">${esc(ba.headline || '')}</div>
    <div class="buying-advice-reasons">${reasonsHtml}</div>
    ${altHtml}
  `;
}

function renderAiRiskWarnings(warnings) {
  const el = $('ai-risk-warnings');
  if (!el) return;

  if (!warnings || warnings.length === 0) {
    el.classList.add('hidden');
    return;
  }

  el.classList.remove('hidden');
  el.innerHTML = '<h4 class="ai-section-title">\u26A0\uFE0F Risk Warnings</h4>' +
    warnings.map(w => `
      <div class="risk-warning-item ${w.level || 'medium'}">
        <span class="risk-warning-emoji">${w.emoji || '\u26A0\uFE0F'}</span>
        <div class="risk-warning-text">
          <strong>${esc(w.title || '')}</strong>
          ${esc(w.detail || '')}
        </div>
      </div>
    `).join('');
}

function renderAiModelComparison(models) {
  const el = $('ai-model-comparison');
  if (!el || !models || models.length < 2) {
    if (el) el.style.display = 'none';
    return;
  }
  if (el) el.style.display = '';

  const rows = models.map(m => {
    const recClass = m.recommended ? ' class="recommended"' : '';
    const tag = m.tag ? `<span class="comparison-tag">${esc(m.tag)}</span>` : '';
    return `<tr${recClass}>
      <td>${esc(m.store || '')}${tag}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.product || '')}</td>
      <td class="comparison-price">Rs. ${fmt(toNum(m.item_price, 0))}</td>
      <td>Rs. ${fmt(toNum(m.travel_cost, 0))}</td>
      <td class="comparison-price">Rs. ${fmt(toNum(m.total_cost, 0))}</td>
      <td>${toNum(m.distance_km, 0).toFixed(1)} km</td>
    </tr>`;
  }).join('');

  el.innerHTML = `
    <h4 class="ai-section-title">\u{1F50D} Model Comparison</h4>
    <table class="comparison-table">
      <thead>
        <tr>
          <th>Store</th>
          <th>Product</th>
          <th>Item Price</th>
          <th>Fuel</th>
          <th>Total</th>
          <th>Distance</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}
