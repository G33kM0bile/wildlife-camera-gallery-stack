"use strict";

const state = {
  config: null,
  original: null,
  huntingGround: null,
  originalHuntingGround: null,
  csrf: "",
  username: "",
  selected: 0,
  map: null,
  markers: [],
  mapResizeObserver: null,
  dirty: false,
  saving: false,
  huntingDirty: false,
  huntingBusy: false,
};

const elements = {
  loginView: document.getElementById("login-view"),
  appView: document.getElementById("app-view"),
  loginForm: document.getElementById("login-form"),
  loginError: document.getElementById("login-error"),
  oidcLoginLink: document.getElementById("oidc-login-link"),
  loginDivider: document.getElementById("login-divider"),
  cameraList: document.getElementById("camera-list"),
  saveButton: document.getElementById("save-button"),
  resetButton: document.getElementById("reset-button"),
  logoutButton: document.getElementById("logout-button"),
  fitMapButton: document.getElementById("fit-map-button"),
  saveState: document.getElementById("save-state"),
  selectedNumber: document.getElementById("selected-number"),
  selectedTitle: document.getElementById("selected-title"),
  selectedCoordinates: document.getElementById("selected-coordinates"),
  revisionLabel: document.getElementById("revision-label"),
  usernameLabel: document.getElementById("username-label"),
  huntingGroundId: document.getElementById("hunting-ground-id"),
  huntingGroundName: document.getElementById("hunting-ground-name"),
  huntingGroundStatus: document.getElementById("hunting-ground-status"),
  validateHuntingGround: document.getElementById("validate-hunting-ground"),
  saveHuntingGround: document.getElementById("save-hunting-ground"),
  toast: document.getElementById("toast"),
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  let result = {};
  try {
    result = await response.json();
  } catch (_) {
    result = {};
  }
  if (!response.ok) {
    const error = new Error(result.error || `Forespørselen feilet (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return result;
}

function showLogin(message = "") {
  elements.appView.hidden = true;
  elements.loginView.hidden = false;
  elements.loginError.textContent = message;
  elements.loginError.hidden = !message;
  window.setTimeout(() => elements.loginForm.elements.username.focus(), 0);
}

function showApp() {
  elements.loginView.hidden = true;
  elements.appView.hidden = false;
  elements.usernameLabel.textContent = `Innlogget som ${state.username}`;
  renderAll();
  window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
    if (!state.map) initializeMap();
    state.map.invalidateSize({ pan: false });
    renderMarkers();
    fitAllMarkers();
  }));
}

function setDirty(value) {
  state.dirty = value;
  elements.saveButton.disabled = !value || state.saving;
  elements.resetButton.disabled = !value || state.saving;
  elements.saveState.classList.toggle("dirty", value && !state.saving);
  elements.saveState.classList.remove("error");
  elements.saveState.querySelector("span:last-child").textContent = state.saving
    ? "Lagrer …"
    : value
      ? "Ulagrede endringer"
      : "Alt er lagret";
}

function markChanged() {
  setDirty(JSON.stringify(state.config.cameras) !== JSON.stringify(state.original.cameras));
  renderMarkers();
  updateSelectedBar();
}

function inputField(labelText, value, type, onInput, options = {}) {
  const label = document.createElement("label");
  if (options.wide) label.classList.add("wide");
  label.append(document.createTextNode(labelText));
  const input = document.createElement("input");
  input.type = type;
  input.value = value;
  if (options.step) input.step = options.step;
  if (options.min !== undefined) input.min = String(options.min);
  if (options.max !== undefined) input.max = String(options.max);
  if (options.maxLength) input.maxLength = options.maxLength;
  input.addEventListener("input", () => onInput(input.value));
  input.addEventListener("focus", () => {
    if (state.selected !== options.cameraIndex) selectCamera(options.cameraIndex);
  });
  label.append(input);
  return label;
}

function textAreaField(labelText, value, onInput, options = {}) {
  const label = document.createElement("label");
  label.classList.add("wide");
  label.append(document.createTextNode(labelText));
  const input = document.createElement("textarea");
  input.value = value;
  input.rows = options.rows || 2;
  if (options.maxLength) input.maxLength = options.maxLength;
  input.addEventListener("input", () => onInput(input.value));
  input.addEventListener("focus", () => {
    if (state.selected !== options.cameraIndex) selectCamera(options.cameraIndex);
  });
  label.append(input);
  return label;
}

function parseTags(value) {
  return [...new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean))];
}

function renderCameraList() {
  elements.cameraList.replaceChildren();
  state.config.cameras.forEach((camera, index) => {
    const card = document.createElement("article");
    card.className = "camera-card";
    card.classList.toggle("selected", index === state.selected);
    card.classList.toggle("disabled-card", !camera.enabled);

    const summary = document.createElement("button");
    summary.type = "button";
    summary.className = "camera-summary";
    summary.setAttribute("aria-expanded", String(index === state.selected));
    summary.addEventListener("click", () => selectCamera(index));

    const number = document.createElement("span");
    number.className = "camera-number";
    number.textContent = String(camera.number);
    const heading = document.createElement("span");
    heading.className = "camera-heading";
    const strong = document.createElement("strong");
    strong.textContent = camera.title;
    const subheading = document.createElement("span");
    subheading.textContent = `${camera.id} · ${camera.location}`;
    heading.append(strong, subheading);
    const chevron = document.createElement("span");
    chevron.className = "chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "⌄";
    summary.append(number, heading, chevron);

    const fields = document.createElement("div");
    fields.className = "camera-fields";
    fields.append(
      inputField("Bildetittel", camera.title, "text", (value) => {
        camera.title = value;
        strong.textContent = value || `Kamera ${camera.number}`;
        markChanged();
      }, { wide: true, maxLength: 100, cameraIndex: index }),
      inputField("Stedsnavn", camera.location, "text", (value) => {
        camera.location = value;
        subheading.textContent = `${camera.id} · ${value}`;
        markChanged();
      }, { wide: true, maxLength: 80, cameraIndex: index }),
      inputField("Emne", camera.subject || "", "text", (value) => {
        camera.subject = value;
        markChanged();
      }, { wide: true, maxLength: 160, cameraIndex: index }),
      textAreaField("Kommentar", camera.comment || "", (value) => {
        camera.comment = value;
        markChanged();
      }, { maxLength: 500, rows: 2, cameraIndex: index }),
      inputField("Tagger (kommaseparert)", (camera.tags || []).join(", "), "text", (value) => {
        camera.tags = parseTags(value);
        markChanged();
      }, { wide: true, maxLength: 2000, cameraIndex: index }),
      inputField("Breddegrad", camera.latitude, "number", (value) => {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) camera.latitude = parsed;
        markChanged();
      }, { step: "0.000001", min: -90, max: 90, cameraIndex: index }),
      inputField("Lengdegrad", camera.longitude, "number", (value) => {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) camera.longitude = parsed;
        markChanged();
      }, { step: "0.000001", min: -180, max: 180, cameraIndex: index })
    );

    const toggleRow = document.createElement("div");
    toggleRow.className = "toggle-row";
    const toggleLabelText = document.createElement("span");
    toggleLabelText.textContent = "Legg metadata på nye bilder";
    const toggle = document.createElement("label");
    toggle.className = "toggle";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = camera.enabled;
    checkbox.setAttribute("aria-label", `Aktiver kamera ${camera.number}`);
    checkbox.addEventListener("change", () => {
      camera.enabled = checkbox.checked;
      markChanged();
      renderCameraList();
    });
    const track = document.createElement("span");
    track.className = "toggle-track";
    toggle.append(checkbox, track);
    toggleRow.append(toggleLabelText, toggle);
    fields.append(toggleRow);

    card.append(summary, fields);
    elements.cameraList.append(card);
  });
}

function initializeMap() {
  state.map = L.map("map", { zoomControl: true, attributionControl: false });
  L.tileLayer.wms("https://wms.geonorge.no/skwms1/wms.topo", {
    layers: "topo",
    format: "image/png",
    transparent: false,
    version: "1.1.1",
    maxZoom: 19,
    minZoom: 4,
  }).addTo(state.map);
  state.map.on("click", (event) => {
    const camera = state.config.cameras[state.selected];
    camera.latitude = Number(event.latlng.lat.toFixed(7));
    camera.longitude = Number(event.latlng.lng.toFixed(7));
    markChanged();
    renderCameraList();
  });
  if (window.ResizeObserver) {
    state.mapResizeObserver = new ResizeObserver(() => {
      window.requestAnimationFrame(() => state.map?.invalidateSize({ pan: false }));
    });
    state.mapResizeObserver.observe(document.getElementById("map"));
  }
}

function markerIcon(camera, selected) {
  const classes = ["camera-map-marker"];
  if (selected) classes.push("selected");
  if (!camera.enabled) classes.push("disabled");
  return L.divIcon({
    className: "",
    html: `<div class="${classes.join(" ")}"><span>${camera.number}</span></div>`,
    iconSize: [35, 35],
    iconAnchor: [17, 34],
  });
}

function renderMarkers() {
  if (!state.map || !state.config) return;
  state.markers.forEach((marker) => marker.remove());
  state.markers = state.config.cameras.map((camera, index) => {
    const marker = L.marker([camera.latitude, camera.longitude], {
      draggable: true,
      icon: markerIcon(camera, index === state.selected),
      title: camera.title,
    }).addTo(state.map);
    marker.on("click", () => selectCamera(index, false));
    marker.on("dragend", () => {
      const point = marker.getLatLng();
      camera.latitude = Number(point.lat.toFixed(7));
      camera.longitude = Number(point.lng.toFixed(7));
      selectCamera(index, false);
      markChanged();
      renderCameraList();
    });
    return marker;
  });
}

function fitAllMarkers() {
  if (!state.map || !state.config) return;
  const points = state.config.cameras.map((camera) => [camera.latitude, camera.longitude]);
  state.map.fitBounds(points, { padding: [42, 42], maxZoom: 15 });
}

function selectCamera(index, pan = true) {
  state.selected = index;
  renderCameraList();
  renderMarkers();
  updateSelectedBar();
  if (pan && state.map) {
    const camera = state.config.cameras[index];
    state.map.flyTo([camera.latitude, camera.longitude], Math.max(state.map.getZoom(), 15), { duration: 0.45 });
  }
}

function updateSelectedBar() {
  const camera = state.config.cameras[state.selected];
  elements.selectedNumber.textContent = camera.number;
  elements.selectedTitle.textContent = camera.title;
  elements.selectedCoordinates.textContent = `${Number(camera.latitude).toFixed(6)}, ${Number(camera.longitude).toFixed(6)}`;
}

function renderRevision() {
  const updated = new Date(state.config.updated_at);
  const time = Number.isNaN(updated.valueOf())
    ? state.config.updated_at
    : updated.toLocaleString("nb-NO", { dateStyle: "medium", timeStyle: "short" });
  elements.revisionLabel.textContent = `Revisjon ${state.config.revision} · Sist endret ${time}`;
}

function renderAll() {
  renderCameraList();
  renderRevision();
  renderHuntingGround();
  updateSelectedBar();
  setDirty(state.dirty);
}

function huntingGroundChanged() {
  if (!state.huntingGround || !state.originalHuntingGround) return;
  state.huntingGround.jaktfelt_id = elements.huntingGroundId.value;
  state.huntingGround.jaktfelt_name = elements.huntingGroundName.value;
  state.huntingDirty =
    state.huntingGround.jaktfelt_id !== state.originalHuntingGround.jaktfelt_id ||
    state.huntingGround.jaktfelt_name !== state.originalHuntingGround.jaktfelt_name;
  elements.saveHuntingGround.disabled = !state.huntingDirty || state.huntingBusy;
  if (state.huntingDirty) {
    elements.huntingGroundStatus.className = "hunting-ground-status pending";
    elements.huntingGroundStatus.textContent = "Ulagrede endringer. Kontroller feltet før aktivering.";
  } else {
    renderHuntingGroundStatus();
  }
}

function renderHuntingGroundStatus() {
  const ground = state.huntingGround;
  if (!ground) return;
  elements.huntingGroundStatus.className = "hunting-ground-status ok";
  const official = ground.statskog_name ? `Statskog: ${ground.statskog_name}` : "Ikke kontrollert";
  const revision = ground.revision ? ` · Revisjon ${ground.revision}` : "";
  elements.huntingGroundStatus.textContent = `${official}${revision}`;
}

function renderHuntingGround() {
  if (!state.huntingGround) return;
  elements.huntingGroundId.value = state.huntingGround.jaktfelt_id || "";
  elements.huntingGroundName.value = state.huntingGround.jaktfelt_name || "";
  elements.validateHuntingGround.disabled = state.huntingBusy;
  elements.saveHuntingGround.disabled = !state.huntingDirty || state.huntingBusy;
  renderHuntingGroundStatus();
}

function toast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.hidden = false;
  window.clearTimeout(toast.timeout);
  toast.timeout = window.setTimeout(() => { elements.toast.hidden = true; }, 4200);
}

async function loadConfiguration() {
  try {
    const result = await request("/api/config");
    state.config = result.config;
    state.original = clone(result.config);
    state.huntingGround = result.hunting_ground;
    state.originalHuntingGround = clone(result.hunting_ground);
    state.csrf = result.csrf;
    state.username = result.username;
    state.dirty = false;
    state.huntingDirty = false;
    showApp();
  } catch (error) {
    if (error.status === 401) showLogin();
    else showLogin(error.message);
  }
}

async function loadAuthOptions() {
  try {
    const options = await request("/api/auth-options");
    elements.oidcLoginLink.hidden = !options.oidc;
    elements.loginDivider.hidden = !options.oidc;
  } catch (_) {
    elements.oidcLoginLink.hidden = true;
    elements.loginDivider.hidden = true;
  }
  const oidcError = new URLSearchParams(window.location.search).get("oidc_error");
  if (oidcError) {
    elements.loginError.textContent = oidcError;
    elements.loginError.hidden = false;
    window.history.replaceState({}, "", window.location.pathname);
  }
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = elements.loginForm.querySelector("button[type=submit]");
  submit.disabled = true;
  elements.loginError.hidden = true;
  try {
    const body = new URLSearchParams(new FormData(elements.loginForm));
    await request("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
      body,
    });
    elements.loginForm.elements.password.value = "";
    await loadConfiguration();
  } catch (error) {
    elements.loginError.textContent = error.message;
    elements.loginError.hidden = false;
  } finally {
    submit.disabled = false;
  }
});

elements.saveButton.addEventListener("click", async () => {
  if (!state.dirty || state.saving) return;
  state.saving = true;
  setDirty(true);
  try {
    const result = await request("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf },
      body: JSON.stringify({ cameras: state.config.cameras }),
    });
    state.config = result.config;
    state.original = clone(result.config);
    state.dirty = false;
    renderAll();
    renderMarkers();
    toast("Kameraoppsettet er lagret. Nye opplastinger bruker de nye verdiene.");
  } catch (error) {
    elements.saveState.classList.add("error");
    elements.saveState.querySelector("span:last-child").textContent = "Kunne ikke lagre";
    toast(error.message, true);
  } finally {
    state.saving = false;
    setDirty(state.dirty);
  }
});

elements.resetButton.addEventListener("click", () => {
  state.config = clone(state.original);
  state.dirty = false;
  renderAll();
  renderMarkers();
  fitAllMarkers();
  toast("Ulagrede endringer er tilbakestilt.");
});

elements.huntingGroundId.addEventListener("input", huntingGroundChanged);
elements.huntingGroundName.addEventListener("input", huntingGroundChanged);

elements.validateHuntingGround.addEventListener("click", async () => {
  if (state.huntingBusy) return;
  state.huntingBusy = true;
  elements.validateHuntingGround.disabled = true;
  elements.saveHuntingGround.disabled = true;
  elements.huntingGroundStatus.className = "hunting-ground-status pending";
  elements.huntingGroundStatus.textContent = "Kontrollerer mot Statskog …";
  try {
    const result = await request("/api/hunting-ground/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf },
      body: JSON.stringify({ jaktfelt_id: elements.huntingGroundId.value }),
    });
    elements.huntingGroundStatus.className = "hunting-ground-status ok";
    elements.huntingGroundStatus.textContent =
      `Gyldig felt: ${result.result.statskog_name} · ${result.result.art || "ukjent art"}`;
    toast(`Statskog bekreftet ${result.result.statskog_name}.`);
  } catch (error) {
    elements.huntingGroundStatus.className = "hunting-ground-status error";
    elements.huntingGroundStatus.textContent = error.message;
    toast(error.message, true);
  } finally {
    state.huntingBusy = false;
    elements.validateHuntingGround.disabled = false;
    elements.saveHuntingGround.disabled = !state.huntingDirty;
  }
});

elements.saveHuntingGround.addEventListener("click", async () => {
  if (!state.huntingDirty || state.huntingBusy) return;
  state.huntingBusy = true;
  elements.validateHuntingGround.disabled = true;
  elements.saveHuntingGround.disabled = true;
  elements.huntingGroundStatus.className = "hunting-ground-status pending";
  elements.huntingGroundStatus.textContent = "Validerer og aktiverer jaktfeltet …";
  try {
    const result = await request("/api/hunting-ground", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf },
      body: JSON.stringify({
        jaktfelt_id: elements.huntingGroundId.value,
        jaktfelt_name: elements.huntingGroundName.value,
      }),
    });
    state.huntingGround = result.hunting_ground;
    state.originalHuntingGround = clone(result.hunting_ground);
    state.huntingDirty = false;
    renderHuntingGround();
    toast(result.message || "Jaktfeltet er aktivert.");
  } catch (error) {
    elements.huntingGroundStatus.className = "hunting-ground-status error";
    elements.huntingGroundStatus.textContent = error.message;
    toast(error.message, true);
  } finally {
    state.huntingBusy = false;
    elements.validateHuntingGround.disabled = false;
    elements.saveHuntingGround.disabled = !state.huntingDirty;
  }
});

elements.logoutButton.addEventListener("click", async () => {
  if ((state.dirty || state.huntingDirty) && !window.confirm("Du har ulagrede endringer. Vil du logge ut likevel?")) return;
  try {
    await request("/api/logout", { method: "POST", headers: { "X-CSRF-Token": state.csrf } });
  } catch (_) {
    // The local session is cleared in the UI even if the server already expired it.
  }
  state.config = null;
  state.original = null;
  state.huntingGround = null;
  state.originalHuntingGround = null;
  state.csrf = "";
  showLogin();
});

elements.fitMapButton.addEventListener("click", fitAllMarkers);

window.addEventListener("resize", () => {
  if (state.map) state.map.invalidateSize({ pan: false });
});

window.addEventListener("beforeunload", (event) => {
  if (!state.dirty && !state.huntingDirty) return;
  event.preventDefault();
  event.returnValue = "";
});

loadAuthOptions();
loadConfiguration();
