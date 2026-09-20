/* Drip Lab — built by Rishabh Bhardwaj.
   Personal, non-commercial use only. See LICENSE. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const state = {
    gender: "women",
    type: "auto",
    photoExists: false,
    allStores: [],
    hasSearched: false,
    maxPrice: "",        // "" = any
    sort: "",            // "", "price-asc", "price-desc"
    lastData: null,      // last search response, re-rendered on price/sort change
    storesDirty: false,  // store chips changed while the Stores panel was open
    savedOnly: false,    // showing the Saved view
};

const STORE_PREFIX = "driplab:";

function storage(action, key, value) {
    try {
        if (action === "get") return sessionStorage.getItem(STORE_PREFIX + key);
        sessionStorage.setItem(STORE_PREFIX + key, value);
    } catch { /* storage blocked: state just won't persist */ }
    return null;
}

// A random private ID for this browser. When the app is hosted, the server
// keeps each visitor's photo and try-ons under it; locally it's ignored.
const SESSION_ID = (() => {
    const fresh = () => crypto.getRandomValues(new Uint8Array(16))
        .reduce((hex, b) => hex + b.toString(16).padStart(2, "0"), "");
    try {
        let sid = localStorage.getItem("driplab:sid");
        if (!/^[0-9a-f]{32}$/.test(sid || "")) {
            sid = fresh();
            localStorage.setItem("driplab:sid", sid);
        }
        return sid;
    } catch {
        return fresh();
    }
})();

function api(url, options = {}) {
    return fetch(url, {
        ...options,
        headers: { ...(options.headers || {}), "X-Session-Id": SESSION_ID },
    });
}

/* ---------------- Saved items (this browser only) ---------------- */

function loadSaved() {
    try {
        return JSON.parse(localStorage.getItem("driplab:saved") || "[]");
    } catch {
        return [];
    }
}

function storeSaved(items) {
    try {
        localStorage.setItem("driplab:saved", JSON.stringify(items.slice(0, 200)));
    } catch { /* ignore */ }
    const count = items.length;
    const badge = $("#saved-count");
    badge.textContent = count;
    badge.hidden = count === 0;
}

function isSaved(product) {
    return loadSaved().some((p) => p.url === product.url);
}

function toggleSaved(product) {
    const items = loadSaved();
    const without = items.filter((p) => p.url !== product.url);
    const nowSaved = without.length === items.length;
    storeSaved(nowSaved ? [product, ...items] : without);
    if (state.savedOnly) showSaved();
    return nowSaved;
}

function showSaved() {
    state.savedOnly = true;
    $("#nav-saved").classList.add("active");
    const items = loadSaved();
    const grid = $("#results-grid");
    grid.innerHTML = "";
    $("#status-bar").innerHTML = items.length
        ? `<strong>${items.length} saved item${items.length === 1 ? "" : "s"}</strong>`
        : "";
    $("#empty-state").hidden = items.length > 0;
    if (!items.length) {
        $("#empty-state").querySelector("h2").textContent = "Nothing saved yet";
        $("#empty-state").querySelector("p").innerHTML =
            "Tap the ♡ on any item to keep it here.";
    }
    items.forEach((p) => grid.appendChild(productCard(p)));
}

function exitSaved() {
    if (!state.savedOnly) return;
    state.savedOnly = false;
    $("#nav-saved").classList.remove("active");
    $("#empty-state").querySelector("h2").textContent = "Drop a search";
}

/* ---------------- Init ---------------- */

async function init() {
    setupPhotoUpload();
    setupModals();
    setupControls();
    storeSaved(loadSaved());

    await Promise.all([loadStores(), refreshPhoto(), loadGallery(),
                       loadPrivacyNote()]);

    const params = currentParams();
    applyParams(params);
    await loadTypes(state.gender);
    markActiveType();
    renderActiveFilters();

    if (params.has("q") || params.has("g")) {
        const key = searchKey(params);
        const cached = storage("get", `results:${key}`);
        if (cached) {
            renderResults(JSON.parse(cached));
            restoreScroll(key);
        } else {
            runSearch();
        }
    }
}

function currentParams() {
    const fromUrl = new URLSearchParams(location.search);
    if ([...fromUrl.keys()].length) return fromUrl;
    return new URLSearchParams(storage("get", "last") || "");
}

function applyParams(params) {
    $("#search-input").value = params.get("q") || "";
    setGender(params.get("g") || "women");
    state.type = params.get("type") || "auto";
    state.maxPrice = params.get("max") || "";
    state.sort = params.get("sort") || "";
    markChoice("#price-chips", "price", state.maxPrice);
    markChoice("#sort-chips", "sort", state.sort);
    updateSortLabel();
    const stores = params.get("stores");
    if (stores) {
        const wanted = new Set(stores.split(","));
        $$("#store-chips .chip").forEach((c) =>
            c.classList.toggle("active", wanted.has(c.dataset.store)));
    }
}

function buildParams() {
    const params = new URLSearchParams();
    params.set("q", $("#search-input").value.trim());
    params.set("g", state.gender);
    if (state.type !== "auto") params.set("type", state.type);
    const stores = selectedStores();
    if (stores.length !== state.allStores.length) params.set("stores", stores.join(","));
    if (state.maxPrice) params.set("max", state.maxPrice);
    if (state.sort) params.set("sort", state.sort);
    return params;
}

// Results are cached per search; price and sort only re-filter them.
function searchKey(params) {
    const p = new URLSearchParams(params);
    p.delete("max");
    p.delete("sort");
    return p.toString();
}

function setupControls() {
    $("#search-form").addEventListener("submit", (e) => {
        e.preventDefault();
        state.type = "auto";   // a typed query decides its own type
        exitSaved();
        runSearch();
    });

    $(".trending").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-q]");
        if (!btn) return;
        $("#search-input").value = btn.dataset.q;
        state.type = "auto";
        exitSaved();
        runSearch();
    });

    $("#gender-toggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-gender]");
        if (!btn || btn.dataset.gender === state.gender) return;
        setGender(btn.dataset.gender);
        await loadTypes(state.gender);
        markActiveType();
        exitSaved();
        runSearch();
    });

    $("#type-chips").addEventListener("click", (e) => {
        const btn = e.target.closest(".chip");
        if (!btn) return;
        state.type = btn.dataset.type;
        markActiveType();
        exitSaved();
        runSearch();
    });

    $("#type-scroll-more").addEventListener("click", () => {
        const scroller = $(".type-scroller");
        const atEnd = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 8;
        scroller.scrollBy({ left: atEnd ? -scroller.clientWidth : scroller.clientWidth * 0.8 });
    });

    $("#store-chips").addEventListener("click", (e) => {
        const btn = e.target.closest(".chip");
        if (!btn) return;
        btn.classList.toggle("active");
        state.storesDirty = true;
        renderActiveFilters();
    });

    $("#price-chips").addEventListener("click", (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        state.maxPrice = chip.dataset.price;
        markChoice("#price-chips", "price", state.maxPrice);
        closeDropdowns();
        refilter();
    });

    $("#sort-chips").addEventListener("click", (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        state.sort = chip.dataset.sort;
        markChoice("#sort-chips", "sort", state.sort);
        updateSortLabel();
        closeDropdowns();
        refilter();
    });

    $("#dd-stores").querySelector(".dd-all").addEventListener("click", () => {
        $$("#store-chips .chip").forEach((c) => c.classList.add("active"));
        state.storesDirty = true;
        renderActiveFilters();
    });
    $("#dd-stores").querySelector(".dd-done").addEventListener("click", closeDropdowns);

    $("#clear-filters").addEventListener("click", () => {
        state.maxPrice = "";
        state.sort = "";
        markChoice("#price-chips", "price", "");
        markChoice("#sort-chips", "sort", "");
        updateSortLabel();
        const chips = $$("#store-chips .chip");
        if (chips.some((c) => !c.classList.contains("active"))) state.storesDirty = true;
        chips.forEach((c) => c.classList.add("active"));
        applyStoreChange();
        refilter();
    });

    $("#active-pills").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-remove]");
        if (!btn) return;
        if (btn.dataset.remove === "price") {
            state.maxPrice = "";
            markChoice("#price-chips", "price", "");
            refilter();
        } else if (btn.dataset.remove === "sort") {
            state.sort = "";
            markChoice("#sort-chips", "sort", "");
            updateSortLabel();
            refilter();
        } else {
            $$("#store-chips .chip").forEach((c) => c.classList.add("active"));
            state.storesDirty = true;
            applyStoreChange();
        }
    });

    // Dropdown open/close
    $$(".dropdown").forEach((dd) => {
        const btn = dd.querySelector(".dd-btn");
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const panel = dd.querySelector(".dd-panel");
            const wasOpen = !panel.hidden;
            closeDropdowns();
            if (!wasOpen) {
                panel.hidden = false;
                btn.setAttribute("aria-expanded", "true");
            }
        });
    });
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".dropdown")) closeDropdowns();
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeDropdowns();
    });

    // Top navigation
    $("#nav-saved").addEventListener("click", () => {
        if (state.savedOnly) {
            exitSaved();
            state.lastData ? renderResults(state.lastData) : ($("#empty-state").hidden = false);
        } else {
            showSaved();
        }
    });
    $("#nav-how").addEventListener("click", () => openModal("#how-modal"));
    $("#nav-photo").addEventListener("click", () => openModal("#photo-modal"));
    $("#photo-trigger").addEventListener("click", () => openModal("#photo-modal"));

    let scrollTimer;
    window.addEventListener("scroll", () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(saveScroll, 150);
    }, { passive: true });
    window.addEventListener("pagehide", saveScroll);
}

function closeDropdowns() {
    $$(".dropdown").forEach((dd) => {
        dd.querySelector(".dd-panel").hidden = true;
        dd.querySelector(".dd-btn").setAttribute("aria-expanded", "false");
    });
    applyStoreChange();
}

function applyStoreChange() {
    if (!state.storesDirty) return;
    state.storesDirty = false;
    renderActiveFilters();
    if (state.hasSearched) {
        exitSaved();
        runSearch();
    }
}

function setGender(gender) {
    state.gender = gender === "men" ? "men" : "women";
    $$("#gender-toggle button").forEach((b) =>
        b.classList.toggle("active", b.dataset.gender === state.gender));
}

function updateSortLabel() {
    const labels = { "": "Recommended", "price-asc": "Price: low to high",
                     "price-desc": "Price: high to low" };
    $("#sort-label").textContent = labels[state.sort] || "Recommended";
}

function renderActiveFilters() {
    const pills = [];
    const stores = selectedStores();
    if (state.allStores.length && stores.length !== state.allStores.length) {
        const names = state.allStores.filter((s) => stores.includes(s.key)).map((s) => s.name);
        pills.push({ key: "stores", label: names.join(", ") || "No stores" });
    }
    if (state.maxPrice) pills.push({ key: "price", label: `Under £${state.maxPrice}` });
    if (state.sort) pills.push({ key: "sort", label: $("#sort-label").textContent });

    $("#active-pills").innerHTML = pills.map((p) =>
        `<span class="active-pill">${escapeHtml(p.label)}<button data-remove="${p.key}" aria-label="Remove filter">✕</button></span>`
    ).join("");
    $("#active-filters").hidden = pills.length === 0;
}

async function loadPrivacyNote() {
    const note = $("#privacy-note");
    try {
        const cfg = await api("/api/config").then((r) => r.json());
        const text = cfg.hosted
            ? `Your photo is private to this browser, used only to create your own try-ons, and deleted automatically after ${cfg.photo_days === 1 ? "24 hours" : `${cfg.photo_days} days`}.`
            : "Your photo never leaves your computer, except when it is sent to the try-on AI.";
        note.textContent = text;
        $("#how-privacy").textContent = text;
    } catch { /* keep the neutral default */ }
}

async function loadStores() {
    const stores = await api("/api/stores").then((r) => r.json());
    state.allStores = stores;
    const names = stores.map((s) => s.name);
    const list = names.length > 1
        ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names.join("");
    $$("[data-store-list]").forEach((el) => { el.textContent = list; });
    $$("[data-store-count]").forEach((el) => { el.textContent = names.length; });
    const wrap = $("#store-chips");
    wrap.innerHTML = "";
    for (const s of stores) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chip active";
        btn.textContent = s.name;
        btn.dataset.store = s.key;
        wrap.appendChild(btn);
    }
}

async function loadTypes(gender) {
    const types = await api(`/api/types?gender=${gender}`).then((r) => r.json());
    const wrap = $("#type-chips");
    wrap.innerHTML = "";
    for (const t of [{ key: "auto", label: "All" }, ...types]) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chip";
        btn.textContent = t.label;
        btn.dataset.type = t.key;
        wrap.appendChild(btn);
    }
    if (!types.some((t) => t.key === state.type)) state.type = "auto";
}

function markActiveType(detected) {
    const active = state.type !== "auto" ? state.type : (detected || "auto");
    $$("#type-chips .chip").forEach((c) =>
        c.classList.toggle("active", c.dataset.type === active));
}

function markChoice(groupSel, attr, value) {
    $$(`${groupSel} .chip`).forEach((c) =>
        c.classList.toggle("active", (c.dataset[attr] || "") === value));
}

function selectedStores() {
    const active = $$("#store-chips .chip.active").map((b) => b.dataset.store);
    return active.length ? active : state.allStores.map((s) => s.key);
}

/* ---------------- Search ---------------- */

let searchSeq = 0;

async function runSearch() {
    const grid = $("#results-grid");
    const status = $("#status-bar");
    const btn = $("#search-btn");
    const seq = ++searchSeq;

    state.hasSearched = true;
    $("#empty-state").hidden = true;
    btn.disabled = true;
    status.textContent = "Searching stores live…";
    grid.innerHTML = skeletonCards(8);

    const params = buildParams();
    try {
        const query = new URLSearchParams({
            q: params.get("q"),
            gender: state.gender,
            type: state.type,
            stores: selectedStores().join(","),
        });
        const data = await api(`/api/search?${query}`).then((r) => r.json());
        if (seq !== searchSeq) return;   // a newer search superseded this one

        // The query may have named a gender ("mens hoodie"): follow it.
        if (data.gender && data.gender !== state.gender) {
            setGender(data.gender);
            await loadTypes(state.gender);
            params.set("g", state.gender);
        }
        rememberSearch(params, data);
        renderResults(data);
    } catch (err) {
        if (seq !== searchSeq) return;
        grid.innerHTML = "";
        status.innerHTML = `<span class="warn">Search failed: ${escapeHtml(String(err))}</span>`;
    } finally {
        if (seq === searchSeq) btn.disabled = false;
    }
}

function rememberSearch(params, data) {
    const key = searchKey(params);
    history.replaceState(null, "", `?${params}`);
    storage("set", "last", params.toString());
    storage("set", `results:${key}`, JSON.stringify(data));
    storage("set", `scroll:${key}`, "0");
}

function saveScroll() {
    if (!state.hasSearched) return;
    storage("set", `scroll:${searchKey(location.search)}`, String(Math.round(scrollY)));
}

function restoreScroll(key) {
    const y = Number(storage("get", `scroll:${key}`) || 0);
    if (y > 0) requestAnimationFrame(() => window.scrollTo(0, y));
}

function renderResults(data) {
    const grid = $("#results-grid");
    const status = $("#status-bar");
    state.hasSearched = true;
    state.lastData = data;
    exitSaved();
    grid.innerHTML = "";
    markActiveType(data.type);
    renderActiveFilters();

    const products = applyPriceAndSort(data.products);
    const hidden = data.products.length - products.length;

    let msg = `<strong>${products.length} result${products.length === 1 ? "" : "s"}</strong>`;
    if (data.query) msg += ` for “${escapeHtml(data.query)}”`;
    else msg += ` · ${data.gender === "men" ? "Men's" : "Women's"} ${(data.type_label || "picks").toLowerCase()}`;
    if (hidden > 0) msg += ` <span class="note">(${hidden} over £${state.maxPrice} hidden)</span>`;
    if (data.note) msg = `<span class="note">${escapeHtml(data.note)}</span>`;
    if (data.query && !data.query_matched) {
        msg += ` <span class="warn">— no exact match, showing everything</span>`;
    }
    if (data.errors && data.errors.length) {
        msg += ` <span class="warn">(${data.errors.map(escapeHtml).join("; ")})</span>`;
    }
    status.innerHTML = msg;

    $("#empty-state").hidden = products.length > 0;
    for (const p of products) grid.appendChild(productCard(p));
}

function priceOf(p) {
    const m = String(p.price || "").replace(/,/g, "").match(/£\s*(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
}

function applyPriceAndSort(products) {
    let list = products;
    if (state.maxPrice) {
        const max = Number(state.maxPrice);
        list = list.filter((p) => {
            const price = priceOf(p);
            return price === null || price < max;
        });
    }
    if (state.sort) {
        const dir = state.sort === "price-asc" ? 1 : -1;
        list = [...list].sort((a, b) => {
            const pa = priceOf(a), pb = priceOf(b);
            if (pa === null) return 1;
            if (pb === null) return -1;
            return (pa - pb) * dir;
        });
    }
    return list;
}

// Price/sort changed: re-render the loaded results and update the URL.
function refilter() {
    renderActiveFilters();
    if (state.savedOnly) return showSaved();
    if (!state.lastData) return;
    const params = buildParams();
    history.replaceState(null, "", `?${params}`);
    storage("set", "last", params.toString());
    renderResults(state.lastData);
}

function productCard(p) {
    const card = document.createElement("article");
    card.className = "card";

    const media = document.createElement("a");
    media.className = "card-img";
    media.href = p.url;
    media.target = "_blank";
    media.rel = "noopener";
    media.title = "Open product page";

    if (p.image) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = p.name;
        img.src = `/api/image-proxy?url=${encodeURIComponent(p.image)}`;
        img.onerror = () => {
            img.remove();
            media.insertAdjacentHTML("afterbegin", '<div class="no-img">📷</div>');
        };
        media.appendChild(img);
    } else {
        media.insertAdjacentHTML("afterbegin", '<div class="no-img">📷</div>');
    }

    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = p.store;

    const save = document.createElement("button");
    save.type = "button";
    save.className = "save-btn" + (isSaved(p) ? " saved" : "");
    save.textContent = isSaved(p) ? "♥" : "♡";
    save.title = "Save for later";
    save.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const now = toggleSaved(p);
        save.classList.toggle("saved", now);
        save.textContent = now ? "♥" : "♡";
    });

    const tryBtn = document.createElement("button");
    tryBtn.type = "button";
    tryBtn.className = "card-tryon";
    tryBtn.textContent = "Try it on";
    if (!p.image) {
        tryBtn.disabled = true;
        tryBtn.title = "No product image available";
    } else if (!state.photoExists) {
        tryBtn.disabled = true;
        tryBtn.title = "Add a photo first";
    }
    tryBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!state.photoExists) return openModal("#photo-modal");
        startTryOn(p, tryBtn, card);
    });

    media.append(badge, save, tryBtn);

    const body = document.createElement("div");
    body.className = "card-body";
    const line = document.createElement("div");
    line.className = "card-line";
    const name = document.createElement("div");
    name.className = "card-name";
    name.textContent = p.name;
    const price = document.createElement("div");
    price.className = "card-price";
    price.textContent = p.price || "";
    line.append(name, price);
    body.appendChild(line);
    if (p.colour) {
        const sub = document.createElement("div");
        sub.className = "card-sub";
        sub.textContent = p.colour;
        body.appendChild(sub);
    }

    card.append(media, body);
    return card;
}

function skeletonCards(n) {
    let html = "";
    for (let i = 0; i < n; i++) {
        html += `<div class="card skeleton"><div class="card-img"></div>
        <div class="card-body"><div class="sk-line"></div><div class="sk-line short"></div></div></div>`;
    }
    return html;
}

/* ---------------- Photo ---------------- */

function setupPhotoUpload() {
    const drop = $("#photo-drop");
    const input = $("#photo-input");

    drop.addEventListener("click", () => input.click());
    $("#photo-change").addEventListener("click", (e) => {
        e.stopPropagation();
        input.click();
    });
    input.addEventListener("change", () => {
        if (input.files.length) uploadPhoto(input.files[0]);
    });

    ["dragover", "dragenter"].forEach((ev) =>
        drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("dragover"); }));
    ["dragleave", "drop"].forEach((ev) =>
        drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("dragover"); }));
    drop.addEventListener("drop", (e) => {
        if (e.dataTransfer.files.length) uploadPhoto(e.dataTransfer.files[0]);
    });
}

async function uploadPhoto(file) {
    const status = $("#photo-status");
    status.textContent = "Uploading…";
    status.className = "photo-status";
    const form = new FormData();
    form.append("file", file);
    try {
        const res = await api("/api/photo", { method: "POST", body: form });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        showPhoto((await res.json()).url);
    } catch (err) {
        status.textContent = `Upload failed: ${err.message}`;
    }
}

async function refreshPhoto() {
    try {
        const data = await api("/api/photo").then((r) => r.json());
        if (data.exists) showPhoto(data.url);
    } catch { /* server starting up */ }
}

function showPhoto(url) {
    state.photoExists = true;
    const img = $("#photo-preview");
    img.onload = () => showPhotoAdvice(img);
    img.src = url;
    img.hidden = false;
    $("#photo-placeholder").hidden = true;
    $("#photo-change").hidden = false;
    $("#photo-cta-text").textContent = "Your photo is ready";
    $("#photo-trigger").classList.add("ready");
    $("#nav-avatar").innerHTML = `<img src="${url}" alt="">`;
    $$(".card-tryon").forEach((b) => {
        if (b.title === "Add a photo first") {
            b.disabled = false;
            b.title = "";
        }
    });
}

// Try-on can only dress the body it can see. A landscape shot is almost
// always a webcam/close-up, which makes the AI borrow the model's body.
function showPhotoAdvice(img) {
    const status = $("#photo-status");
    if (img.naturalWidth > img.naturalHeight * 1.05) {
        status.innerHTML = "Photo saved, but it looks like a close-up. For a real " +
            "try-on use a <strong>full-body, portrait</strong> photo — a mirror selfie works great.";
        status.className = "photo-status warn";
    } else {
        status.textContent = "Photo ready — try-on enabled ✓";
        status.className = "photo-status ok";
    }
}

/* ---------------- Try-on ---------------- */

async function startTryOn(product, btn, card) {
    if (btn.classList.contains("working")) return;
    btn.classList.add("working");
    btn.textContent = "Queued…";
    clearCardError(card);

    try {
        const res = await api("/api/tryon", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                // A garment-only shot (no model) gives the AI nobody to copy.
                image_url: product.tryon_image || product.image,
                product_name: product.name,
                product_url: product.url,
                category: product.category || "",
            }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        await pollJob((await res.json()).job_id, product, btn, card);
    } catch (err) {
        showCardError(card, err.message);
        resetTryBtn(btn);
    }
}

async function pollJob(jobId, product, btn, card) {
    const started = Date.now();
    while (true) {
        const job = await api(`/api/tryon/${jobId}`).then((r) => r.json());
        if (job.status === "done") {
            resetTryBtn(btn);
            openResult(product, job.result_url);
            loadGallery();
            return;
        }
        if (job.status === "error") {
            showCardError(card, job.error || "Try-on failed.");
            resetTryBtn(btn);
            return;
        }
        const secs = Math.round((Date.now() - started) / 1000);
        btn.textContent = job.status === "running" ? `Fitting… ${secs}s` : `Queued… ${secs}s`;
        if (secs > 360) {
            showCardError(card, "Timed out after 6 minutes — the try-on service may be busy.");
            resetTryBtn(btn);
            return;
        }
        await sleep(2000);
    }
}

function resetTryBtn(btn) {
    btn.classList.remove("working");
    btn.textContent = "Try it on";
}

function showCardError(card, msg) {
    clearCardError(card);
    const div = document.createElement("div");
    div.className = "card-error";
    div.textContent = msg;
    card.querySelector(".card-body").appendChild(div);
}

function clearCardError(card) {
    card.querySelector(".card-error")?.remove();
}

/* ---------------- Fitting room ---------------- */

async function loadGallery() {
    try {
        const items = await api("/api/tryons").then((r) => r.json());
        const section = $("#gallery-section");
        const strip = $("#gallery-strip");
        if (!items.length) {
            section.hidden = true;
            strip.innerHTML = "";
            return;
        }
        section.hidden = false;
        strip.innerHTML = "";
        for (const it of items) {
            const div = document.createElement("div");
            div.className = "gallery-item";
            div.innerHTML = `<img src="${it.result_url}" alt="${escapeHtml(it.product_name)}" loading="lazy">
                <span>${escapeHtml(it.product_name || "Try-on")}</span>`;
            div.addEventListener("click", () =>
                openResult({ name: it.product_name, image: it.garment_url, url: it.product_url },
                           it.result_url));
            strip.appendChild(div);
        }
    } catch { /* non-fatal */ }
}

async function clearGallery() {
    if (!confirm("Delete all your try-on images?\n\nTrying the same items again will " +
                 "generate (and, with Gemini, charge for) new images.")) return;
    const btn = $("#gallery-clear");
    btn.disabled = true;
    try {
        const res = await api("/api/tryons", { method: "DELETE" });
        if (!res.ok) throw new Error(res.statusText);
        await loadGallery();
    } catch (err) {
        alert(`Couldn't clear the gallery: ${err.message}`);
    } finally {
        btn.disabled = false;
    }
}

/* ---------------- Modals ---------------- */

function setupModals() {
    $("#gallery-clear").addEventListener("click", clearGallery);
    $$(".modal").forEach((modal) => {
        modal.addEventListener("click", (e) => {
            if (e.target === modal || e.target.closest("[data-close]")) modal.hidden = true;
        });
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") $$(".modal").forEach((m) => { m.hidden = true; });
    });
}

function openModal(sel) {
    $(sel).hidden = false;
}

function openResult(product, resultUrl) {
    $("#modal-title").textContent = product.name || "Try-on result";
    $("#modal-garment").src = product.image
        ? `/api/image-proxy?url=${encodeURIComponent(product.image)}` : "";
    $("#modal-result").src = resultUrl;
    $("#modal-download").href = resultUrl;
    const shop = $("#modal-product");
    shop.style.display = product.url ? "" : "none";
    if (product.url) shop.href = product.url;
    openModal("#modal");
}

/* ---------------- Utils ---------------- */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function escapeHtml(s) {
    return String(s ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

init();
