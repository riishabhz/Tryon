/* Drip Lab — dynamic search + virtual try-on frontend */

const $ = (sel) => document.querySelector(sel);

const state = {
    gender: "women",
    type: "auto",
    photoExists: false,
    allStores: [],
    hasSearched: false,
    maxPrice: "",        // "" = any
    sort: "",            // "", "price-asc", "price-desc"
    lastData: null,      // last search response, re-rendered on price/sort change
    storesDirty: false,  // store chips changed while the Filters panel was open
};

// Search state lives in the URL (?q=&g=&type=&stores=) and the last results
// in sessionStorage, so returning from a shop page restores everything.
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
        return fresh();   // storage blocked: private for this page load only
    }
})();

function api(url, options = {}) {
    return fetch(url, {
        ...options,
        headers: { ...(options.headers || {}), "X-Session-Id": SESSION_ID },
    });
}

/* ---------------- Init ---------------- */

async function init() {
    setupPhotoUpload();
    setupModal();
    setupControls();
    $("#gallery-clear").addEventListener("click", clearGallery);

    await Promise.all([loadStores(), refreshPhoto(), loadGallery()]);

    const params = currentParams();
    applyParams(params);
    await loadTypes(state.gender);
    markActiveType();

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
    // Opened fresh (e.g. address bar): fall back to this tab's last search.
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
    const stores = params.get("stores");
    if (stores) {
        const wanted = new Set(stores.split(","));
        document.querySelectorAll("#store-chips .chip").forEach((c) =>
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
        runSearch();
    });

    $("#gender-toggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-gender]");
        if (!btn || btn.dataset.gender === state.gender) return;
        setGender(btn.dataset.gender);
        await loadTypes(state.gender);
        markActiveType();
        runSearch();
    });

    $("#type-chips").addEventListener("click", (e) => {
        const btn = e.target.closest(".chip");
        if (!btn) return;
        state.type = btn.dataset.type;
        markActiveType();
        runSearch();
    });

    $("#store-chips").addEventListener("click", (e) => {
        const btn = e.target.closest(".chip");
        if (!btn) return;
        btn.classList.toggle("active");
        state.storesDirty = true;
        updateFilterCount();
    });

    setupFilters();

    let scrollTimer;
    window.addEventListener("scroll", () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(saveScroll, 150);
    }, { passive: true });
    window.addEventListener("pagehide", saveScroll);
}

function setGender(gender) {
    state.gender = gender === "men" ? "men" : "women";
    document.querySelectorAll("#gender-toggle button").forEach((b) =>
        b.classList.toggle("active", b.dataset.gender === state.gender));
}

async function loadStores() {
    const stores = await api("/api/stores").then((r) => r.json());
    state.allStores = stores;
    const wrap = $("#store-chips");
    wrap.innerHTML = "";
    for (const s of stores) {
        const btn = document.createElement("button");
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
    for (const t of [{ key: "auto", label: "Auto" }, ...types]) {
        const btn = document.createElement("button");
        btn.className = "chip";
        btn.textContent = t.label;
        btn.dataset.type = t.key;
        wrap.appendChild(btn);
    }
    if (!types.some((t) => t.key === state.type)) state.type = "auto";
}

function markActiveType(detected) {
    const active = state.type !== "auto" ? state.type : (detected || "auto");
    document.querySelectorAll("#type-chips .chip").forEach((c) =>
        c.classList.toggle("active", c.dataset.type === active));
}

function selectedStores() {
    const active = [...document.querySelectorAll("#store-chips .chip.active")]
        .map((b) => b.dataset.store);
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
    status.textContent = "Searching retailers live…";
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
    grid.innerHTML = "";
    markActiveType(data.type);

    const products = applyPriceAndSort(data.products);
    const hidden = data.products.length - products.length;

    const what = data.type_label || "items";
    const who = data.gender === "men" ? "Men's" : "Women's";
    let msg = `${products.length} ${who} ${what.toLowerCase()} from ${data.stores_searched.join(", ")}`;
    if (hidden > 0) msg += ` <span class="note">(${hidden} over £${state.maxPrice} hidden)</span>`;
    if (data.note) msg = `<span class="note">${escapeHtml(data.note)}</span>`;
    if (data.query && !data.query_matched) {
        msg += ` — <span class="warn">no exact match for “${escapeHtml(data.query)}”, showing everything</span>`;
    }
    if (data.errors && data.errors.length) {
        msg += ` <span class="warn">(${data.errors.map(escapeHtml).join("; ")})</span>`;
    }
    status.innerHTML = msg;

    $("#empty-state").hidden = products.length > 0;
    for (const p of products) {
        grid.appendChild(productCard(p));
    }
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

/* ---------------- Filters panel ---------------- */

function setupFilters() {
    const panel = $("#filters-panel");
    const btn = $("#filters-btn");

    btn.addEventListener("click", () => (panel.hidden ? openFilters() : closeFilters()));
    $("#filters-done").addEventListener("click", closeFilters);

    $("#price-chips").addEventListener("click", (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        state.maxPrice = chip.dataset.price;
        markChoice("#price-chips", "price", state.maxPrice);
        refilter();
    });
    $("#sort-chips").addEventListener("click", (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        state.sort = chip.dataset.sort;
        markChoice("#sort-chips", "sort", state.sort);
        refilter();
    });
    $("#filters-reset").addEventListener("click", () => {
        state.maxPrice = "";
        state.sort = "";
        markChoice("#price-chips", "price", "");
        markChoice("#sort-chips", "sort", "");
        const chips = [...document.querySelectorAll("#store-chips .chip")];
        if (chips.some((c) => !c.classList.contains("active"))) state.storesDirty = true;
        chips.forEach((c) => c.classList.add("active"));
        refilter();
    });

    // Click outside or Escape closes the panel.
    document.addEventListener("click", (e) => {
        if (!panel.hidden && !panel.contains(e.target) && !btn.contains(e.target)) closeFilters();
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !panel.hidden) closeFilters();
    });
    updateFilterCount();
}

function openFilters() {
    $("#filters-panel").hidden = false;
    $("#filters-btn").setAttribute("aria-expanded", "true");
}

function closeFilters() {
    $("#filters-panel").hidden = true;
    $("#filters-btn").setAttribute("aria-expanded", "false");
    if (state.storesDirty) {
        state.storesDirty = false;
        if (state.hasSearched) runSearch();
    }
}

function markChoice(groupSel, attr, value) {
    document.querySelectorAll(`${groupSel} .chip`).forEach((c) =>
        c.classList.toggle("active", (c.dataset[attr] || "") === value));
}

// Price/sort changed: re-render the loaded results and update the URL.
function refilter() {
    updateFilterCount();
    if (!state.lastData) return;
    const params = buildParams();
    history.replaceState(null, "", `?${params}`);
    storage("set", "last", params.toString());
    renderResults(state.lastData);
}

function updateFilterCount() {
    const storesOff = [...document.querySelectorAll("#store-chips .chip")]
        .some((c) => !c.classList.contains("active"));
    const n = (storesOff ? 1 : 0) + (state.maxPrice ? 1 : 0) + (state.sort ? 1 : 0);
    const badge = $("#filters-count");
    badge.textContent = n;
    badge.hidden = n === 0;
}

function productCard(p) {
    const card = document.createElement("div");
    card.className = "card";

    const imgWrap = document.createElement("a");
    imgWrap.className = "card-img";
    imgWrap.href = p.url;
    imgWrap.target = "_blank";
    imgWrap.rel = "noopener";
    imgWrap.title = "Open product page";
    if (p.image) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = p.name;
        img.src = `/api/image-proxy?url=${encodeURIComponent(p.image)}`;
        img.onerror = () => {
            img.remove();
            imgWrap.insertAdjacentHTML("beforeend", '<div class="no-img">📷</div>');
        };
        imgWrap.appendChild(img);
    } else {
        imgWrap.insertAdjacentHTML("beforeend", '<div class="no-img">📷</div>');
    }

    const body = document.createElement("div");
    body.className = "card-body";

    const name = document.createElement("div");
    name.className = "card-name";
    name.textContent = p.name;

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.innerHTML = `
        <span class="store-badge store-${p.store_key}">${escapeHtml(p.store)}</span>
        ${p.price ? `<span class="price-badge">${escapeHtml(p.price)}</span>` : ""}
    `;

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const tryBtn = document.createElement("button");
    tryBtn.className = "tryon-btn";
    tryBtn.textContent = "Try it on";
    if (!p.image) {
        tryBtn.disabled = true;
        tryBtn.title = "No product image available";
    } else if (!state.photoExists) {
        tryBtn.disabled = true;
        tryBtn.title = "Add a photo first (left panel)";
    }
    tryBtn.addEventListener("click", () => startTryOn(p, tryBtn, card));

    const viewBtn = document.createElement("a");
    viewBtn.className = "view-btn";
    viewBtn.textContent = "↗";
    viewBtn.title = "Open product page";
    viewBtn.href = p.url;
    viewBtn.target = "_blank";
    viewBtn.rel = "noopener";

    actions.append(tryBtn, viewBtn);
    body.append(name, meta, actions);
    card.append(imgWrap, body);
    return card;
}

function skeletonCards(n) {
    let html = "";
    for (let i = 0; i < n; i++) {
        html += `
        <div class="card skeleton">
            <div class="card-img"></div>
            <div class="card-body">
                <div class="sk-line"></div>
                <div class="sk-line short"></div>
            </div>
        </div>`;
    }
    return html;
}

/* ---------------- Photo upload ---------------- */

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
        drop.addEventListener(ev, (e) => {
            e.preventDefault();
            drop.classList.add("dragover");
        })
    );
    ["dragleave", "drop"].forEach((ev) =>
        drop.addEventListener(ev, (e) => {
            e.preventDefault();
            drop.classList.remove("dragover");
        })
    );
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
        if (!res.ok) {
            const detail = (await res.json()).detail || res.statusText;
            throw new Error(detail);
        }
        const data = await res.json();
        showPhoto(data.url);
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
    document.querySelectorAll(".tryon-btn").forEach((b) => {
        if (b.title.startsWith("Add a photo")) {
            b.disabled = false;
            b.title = "";
        }
    });
}

// Try-on can only dress the body it can see. A landscape shot is almost
// always a webcam/close-up, which makes the AI borrow the product model's body.
function showPhotoAdvice(img) {
    const status = $("#photo-status");
    const landscape = img.naturalWidth > img.naturalHeight * 1.05;
    if (landscape) {
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
        if (!res.ok) {
            const detail = (await res.json()).detail || res.statusText;
            throw new Error(detail);
        }
        const { job_id } = await res.json();
        await pollJob(job_id, product, btn, card);
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
            openModal(product, job.result_url);
            loadGallery();
            return;
        }
        if (job.status === "error") {
            showCardError(card, job.error || "Try-on failed.");
            resetTryBtn(btn);
            return;
        }
        const secs = Math.round((Date.now() - started) / 1000);
        btn.textContent = job.status === "running"
            ? `Fitting… ${secs}s`
            : `Queued… ${secs}s`;
        if (secs > 360) {
            showCardError(card, "Timed out after 6 minutes — the try-on service may be busy. Try again later.");
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

/* ---------------- Gallery ---------------- */

async function clearGallery() {
    const ok = confirm(
        "Delete all your try-on images?\n\n" +
        "They're removed from this computer. Trying the same items again " +
        "will generate (and, with Gemini, charge for) new images.");
    if (!ok) return;
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
            div.innerHTML = `
                <img src="${it.result_url}" alt="${escapeHtml(it.product_name)}" loading="lazy">
                <span>${escapeHtml(it.product_name || "Try-on")}</span>`;
            div.addEventListener("click", () =>
                openModal(
                    { name: it.product_name, image: it.garment_url, url: it.product_url },
                    it.result_url
                )
            );
            strip.appendChild(div);
        }
    } catch { /* non-fatal */ }
}

/* ---------------- Modal ---------------- */

function setupModal() {
    $("#modal-close").addEventListener("click", closeModal);
    $("#modal").addEventListener("click", (e) => {
        if (e.target === $("#modal")) closeModal();
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeModal();
    });
}

function openModal(product, resultUrl) {
    $("#modal-title").textContent = product.name || "Try-on result";
    $("#modal-garment").src = product.image
        ? `/api/image-proxy?url=${encodeURIComponent(product.image)}`
        : "";
    $("#modal-result").src = resultUrl;
    $("#modal-download").href = resultUrl;
    const shop = $("#modal-product");
    if (product.url) {
        shop.href = product.url;
        shop.style.display = "";
    } else {
        shop.style.display = "none";
    }
    $("#modal").hidden = false;
}

function closeModal() {
    $("#modal").hidden = true;
}

/* ---------------- Utils ---------------- */

function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
}

function escapeHtml(s) {
    return String(s ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

init();
