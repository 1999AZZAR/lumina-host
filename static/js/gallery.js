/**
 * Lumina Host - Gallery Logic
 */

// DOM Elements
const elements = {
    grid: document.getElementById('assets-grid'),
    sentinel: document.getElementById('sentinel'),
    form: document.getElementById('uploadForm'),
    loader: document.getElementById('loader'),
    lightbox: document.getElementById('lightbox'),
    dragOverlay: document.getElementById('dragOverlay'),
    queueContainer: document.getElementById('queue-container'),
    queueList: document.getElementById('queue-list'),
    selectModeBtn: document.getElementById('selectModeBtn'),
    bulkActions: document.getElementById('bulk-actions'),
    selectedCountSpan: document.getElementById('selected-count'),
    fabContainer: document.getElementById('fab-container'),
    lightboxImg: document.getElementById('lightbox-img'),
    lightboxTitle: document.getElementById('lightbox-title'),
    lightboxType: document.getElementById('lightbox-type'),
    lightboxDate: document.getElementById('lightbox-date'),
    lightboxDownload: document.getElementById('lightbox-download')
};

// CSRF token for AJAX
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// Redirect to login on 401; show message on 403
function handleAuthResponse(res, data) {
    if (res.status === 401) {
        window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return true;
    }
    if (res.status === 403) {
        if (data && data.error) alert(data.error);
        else alert('Access denied.');
        return true;
    }
    return false;
}

// Download filename with extension (prefer file_name, else title + ext from mime)
function getDownloadFilename(asset) {
    const hasExt = (s) => s && /\.\w+$/.test(s);
    if (asset.fileName && hasExt(asset.fileName)) return asset.fileName.replace(/^.*[/\\]/, '');
    const ext = (asset.type && asset.type.includes('/')) ? '.' + (asset.type.split('/')[1] || 'jpg').replace('jpeg', 'jpg') : '.jpg';
    const base = (asset.title || 'image').replace(/\.[^.]+$/, '').replace(/[/\\]/g, '-') || 'image';
    return base + ext;
}

// State
let state = {
    galleryData: [],
    currentPage: 1,
    hasMore: false,
    isLoading: false,
    searchQuery: '',
    searchDebounceTimer: null,
    currentLightboxIndex: 0,
    isSelectionMode: false,
    selectedIds: new Set(),
    touchStartX: 0,
    touchStartY: 0
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    if (window.LuminaConfig) {
        state.galleryData = window.LuminaConfig.initialAssets || [];
        state.hasMore = window.LuminaConfig.hasMore || false;
    }
    initInfiniteScroll();
    initGlobalListeners();
});

// --- Infinite Scroll ---
function initInfiniteScroll() {
    if (!elements.sentinel) return;
    const observer = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting && state.hasMore && !state.isLoading) loadMore();
    });
    observer.observe(elements.sentinel);
}

async function loadMore() {
    state.isLoading = true;
    if(elements.sentinel) elements.sentinel.classList.remove('opacity-0');
    try {
        const res = await fetch(`/api/assets?page=${state.currentPage + 1}&q=${encodeURIComponent(state.searchQuery)}`);
        const data = await res.json();
        if (handleAuthResponse(res, data)) return;
        if (data.assets.length > 0) {
            data.assets.forEach(asset => {
                const isPublic = asset.is_public !== undefined ? (asset.is_public ? 1 : 0) : 1;
                const mappedAsset = {
                    id: asset.id,
                    urlFull: asset.url_full,
                    urlThumb: asset.url_thumbnail,
                    title: asset.title,
                    fileName: asset.file_name,
                    type: asset.mime_type,
                    date: asset.created_at,
                    isPublic
                };
                state.galleryData.push(mappedAsset);
                elements.grid.insertAdjacentHTML('beforeend', createAssetCard(mappedAsset, state.galleryData.length - 1));
            });
            state.currentPage++;
        }
        state.hasMore = data.has_more;
        if (!state.hasMore && elements.sentinel) elements.sentinel.style.display = 'none';
    } catch (e) { console.error(e); } 
    finally {
        state.isLoading = false;
        if(elements.sentinel) elements.sentinel.classList.add('opacity-0');
    }
}

// --- Search ---
function handleSearch(query) {
    clearTimeout(state.searchDebounceTimer);
    state.searchQuery = query;
    state.searchDebounceTimer = setTimeout(performSearch, 300);
}
async function performSearch() {
    elements.grid.innerHTML = '';
    state.galleryData = [];
    state.currentPage = 0;
    state.hasMore = true;
    if(elements.sentinel) elements.sentinel.style.display = 'flex';
    await loadMore();
}

// --- HTML Generators ---
function createAssetCard(asset, index) {
    const type = asset.type && asset.type.includes('/') ? asset.type.split('/')[1].toUpperCase() : 'IMG';
    const isPublic = asset.isPublic !== undefined ? !!asset.isPublic : true;
    const showVisibility = window.LuminaConfig && window.LuminaConfig.isAuthenticated;
    const visibilityBlock = showVisibility ? `
        <button type="button" class="visibility-toggle absolute top-3 left-3 z-20 w-8 h-8 rounded-full bg-black/50 hover:bg-black/70 text-white flex items-center justify-center transition-all border border-white/10" data-id="${asset.id}" data-public="${isPublic ? 1 : 0}" onclick="event.stopPropagation(); toggleVisibility(this)" title="Toggle public visibility">
            <i class="fa-solid ${isPublic ? 'fa-eye' : 'fa-eye-slash'}"></i>
        </button>
        ${!isPublic ? '<span class="visibility-badge absolute top-3 left-12 z-20 text-[10px] font-bold tracking-wider text-slate-900 bg-amber-400/90 px-2 py-0.5 rounded shadow">Hidden</span>' : ''}` : '';
    return `
    <div class="asset-card group relative glass-panel rounded-2xl overflow-hidden shadow-xl hover:shadow-2xl hover:shadow-emerald-900/20 transition-all duration-500 hover:scale-[1.02] hover:bg-white/10 cursor-pointer animate-[fadeIn_0.5s_ease-out] pointer-events-auto"
         data-id="${asset.id}"
         onclick="handleAssetClick(this, ${index})">
        <div class="selection-overlay absolute top-3 right-3 z-20 ${state.isSelectionMode ? '' : 'hidden'}">
             <div class="w-6 h-6 rounded-full border-2 border-white/50 bg-black/40 flex items-center justify-center transition-all checkbox-circle">
                <i class="fa-solid fa-check text-white text-xs opacity-0 scale-0 transition-all"></i>
             </div>
        </div>${visibilityBlock}
        <div class="aspect-w-4 aspect-h-3 overflow-hidden bg-slate-800 relative">
            <img src="${asset.urlThumb}" alt="${asset.title}" loading="lazy" class="w-full h-64 object-cover transform group-hover:scale-105 transition-transform duration-700 ease-out">
            <div class="absolute inset-0 bg-slate-900/0 group-hover:bg-slate-900/10 transition-colors duration-300"></div>
        </div>
        <div class="info-overlay absolute inset-0 bg-gradient-to-t from-slate-900/95 via-slate-900/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-5">
            <h3 class="text-white font-medium truncate text-lg tracking-wide">${asset.title}</h3>
            <div class="flex justify-between items-center mt-3">
                <span class="text-[10px] font-bold tracking-wider text-slate-900 bg-emerald-400 px-2 py-1 rounded shadow-lg shadow-emerald-400/20">${type}</span>
                <div class="flex gap-2">
                    <span class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:bg-emerald-500 hover:text-white transition-colors">
                        <i class="fa-solid fa-expand text-xs"></i>
                    </span>
                </div>
            </div>
        </div>
    </div>`;
}

// --- Handlers ---
function handleAssetClick(card, index) {
    const id = card.getAttribute('data-id');
    if (state.isSelectionMode) toggleAssetSelection(card, id);
    else {
        const trueIndex = state.galleryData.findIndex(item => String(item.id) === String(id));
        if (trueIndex !== -1) openLightbox(trueIndex);
    }
}

function toggleSelectionMode() {
    state.isSelectionMode = !state.isSelectionMode;
    const btn = elements.selectModeBtn;
    if (state.isSelectionMode) {
        btn.classList.add('bg-indigo-500/20', 'border-indigo-500/50');
        btn.querySelector('span').innerText = 'Cancel';
        document.querySelectorAll('.selection-overlay').forEach(el => el.classList.remove('hidden'));
        if(elements.fabContainer) elements.fabContainer.classList.add('translate-y-32');
    } else {
        btn.classList.remove('bg-indigo-500/20', 'border-indigo-500/50');
        btn.querySelector('span').innerText = 'Select';
        document.querySelectorAll('.selection-overlay').forEach(el => el.classList.add('hidden'));
        if(elements.fabContainer) elements.fabContainer.classList.remove('translate-y-32');
        state.selectedIds.clear();
        updateSelectionUI();
        document.querySelectorAll('.asset-card').forEach(card => {
            const checkbox = card.querySelector('.checkbox-circle');
            const checkIcon = card.querySelector('.fa-check');
            checkbox.classList.remove('bg-emerald-500', 'border-emerald-500');
            checkbox.classList.add('bg-black/40', 'border-white/50');
            checkIcon.classList.remove('opacity-100', 'scale-100');
            card.classList.remove('ring-2', 'ring-emerald-500');
        });
    }
}

function toggleAssetSelection(card, id) {
    const checkbox = card.querySelector('.checkbox-circle');
    const checkIcon = card.querySelector('.fa-check');
    if (state.selectedIds.has(id)) {
        state.selectedIds.delete(id);
        checkbox.classList.remove('bg-emerald-500', 'border-emerald-500');
        checkbox.classList.add('bg-black/40', 'border-white/50');
        checkIcon.classList.remove('opacity-100', 'scale-100');
        card.classList.remove('ring-2', 'ring-emerald-500');
    } else {
        state.selectedIds.add(id);
        checkbox.classList.add('bg-emerald-500', 'border-emerald-500');
        checkbox.classList.remove('bg-black/40', 'border-white/50');
        checkIcon.classList.add('opacity-100', 'scale-100');
        card.classList.add('ring-2', 'ring-emerald-500');
    }
    updateSelectionUI();
}

function updateSelectionUI() {
    if(elements.selectedCountSpan) elements.selectedCountSpan.innerText = state.selectedIds.size;
    if(elements.bulkActions) {
        state.selectedIds.size > 0 ? elements.bulkActions.classList.remove('translate-y-32') : elements.bulkActions.classList.add('translate-y-32');
    }
}

async function toggleVisibility(btn) {
    const id = btn.getAttribute('data-id');
    const current = parseInt(btn.getAttribute('data-public'), 10) === 1;
    const isPublic = !current;
    try {
        const res = await fetch(`/api/assets/${id}/visibility`, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ is_public: isPublic })
        });
        const data = await res.json().catch(() => ({}));
        if (handleAuthResponse(res, data)) return;
        if (!res.ok) {
            alert(data.error || 'Failed to update visibility.');
            return;
        }
        btn.setAttribute('data-public', isPublic ? 1 : 0);
        const icon = btn.querySelector('i');
        if (icon) {
            icon.classList.remove('fa-eye', 'fa-eye-slash');
            icon.classList.add(isPublic ? 'fa-eye' : 'fa-eye-slash');
        }
        const card = btn.closest('.asset-card');
        const badge = card ? card.querySelector('.visibility-badge') : null;
        if (isPublic && badge) badge.remove();
        if (!isPublic && card && !badge) {
            btn.insertAdjacentHTML('afterend', '<span class="visibility-badge absolute top-3 left-12 z-20 text-[10px] font-bold tracking-wider text-slate-900 bg-amber-400/90 px-2 py-0.5 rounded shadow">Hidden</span>');
        }
        const asset = state.galleryData.find(item => String(item.id) === String(id));
        if (asset) asset.isPublic = isPublic ? 1 : 0;
    } catch (e) {
        console.error(e);
        alert('Failed to update visibility.');
    }
}

// --- Bulk Actions ---
async function downloadSelected() {
    if (state.selectedIds.size === 0) return;
    toggleLoader(true);
    const zip = new JSZip();
    const promises = [];
    const folder = zip.folder("lumina-assets");
    state.selectedIds.forEach(id => {
        const asset = state.galleryData.find(item => String(item.id) === String(id));
        if (!asset) return;
        const proxyUrl = `/proxy_download?url=${encodeURIComponent(asset.urlFull)}`;
        promises.push(fetch(proxyUrl).then(r => r.blob()).then(blob => folder.file(getDownloadFilename(asset), blob)));
    });
    try {
        await Promise.all(promises);
        const content = await zip.generateAsync({type:"blob"});
        saveAs(content, "lumina-gallery.zip");
        toggleSelectionMode();
    } catch (e) { alert("Download failed."); } 
    finally { toggleLoader(false); }
}

function confirmDelete() {
    showModal({ title: 'Delete Assets?', message: `Delete ${state.selectedIds.size} items?`, color: 'rose', icon: 'fa-trash-can', onConfirm: performDelete });
}

async function performDelete() {
    toggleLoader(true);
    try {
        const res = await fetch('/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest'},
            body: JSON.stringify({ ids: Array.from(state.selectedIds) })
        });
        const data = await res.json().catch(() => ({}));
        if (handleAuthResponse(res, data)) return;
        if (res.ok) {
            state.selectedIds.forEach(id => {
                const card = document.querySelector(`.asset-card[data-id="${id}"]`);
                if (card) card.remove();
                const idx = state.galleryData.findIndex(i => String(i.id) === String(id));
                if (idx > -1) state.galleryData.splice(idx, 1);
            });
            toggleSelectionMode();
        }
    } catch(e) { alert('Error'); }
    finally { toggleLoader(false); }
}

// --- Lightbox ---
function updateLightboxContent() {
    const asset = state.galleryData[state.currentLightboxIndex];
    if (!asset) return;
    elements.lightboxImg.style.opacity = '0.5';
    setTimeout(() => {
        elements.lightboxImg.src = asset.urlFull;
        elements.lightboxTitle.innerText = asset.title;
        elements.lightboxType.innerText = asset.type.split('/')[1] || 'IMG';
        elements.lightboxDate.innerText = new Date(asset.date).toLocaleDateString();
        elements.lightboxDownload.href = asset.urlFull;
        elements.lightboxImg.style.opacity = '1';
    }, 150);
}

function openLightbox(index) {
    state.currentLightboxIndex = index;
    updateLightboxContent();
    elements.lightbox.classList.remove('hidden');
    void elements.lightbox.offsetWidth;
    elements.lightbox.classList.remove('opacity-0');
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    elements.lightbox.classList.add('opacity-0');
    setTimeout(() => { elements.lightbox.classList.add('hidden'); document.body.style.overflow = ''; }, 300);
}

function nextImage(e) { if(e) e.stopPropagation(); state.currentLightboxIndex = (state.currentLightboxIndex + 1) % state.galleryData.length; updateLightboxContent(); }
function prevImage(e) { if(e) e.stopPropagation(); state.currentLightboxIndex = (state.currentLightboxIndex - 1 + state.galleryData.length) % state.galleryData.length; updateLightboxContent(); }

async function saveLightboxImage() {
    const asset = state.galleryData[state.currentLightboxIndex];
    if(!asset) return;
    toggleLoader(true);
    try {
        const proxyUrl = `/proxy_download?url=${encodeURIComponent(asset.urlFull)}`;
        const res = await fetch(proxyUrl);
        const blob = await res.blob();
        saveAs(blob, getDownloadFilename(asset));
    } catch(e) { alert('Save failed'); } 
    finally { toggleLoader(false); }
}

function shareLightboxImage() {
    const asset = state.galleryData[state.currentLightboxIndex];
    if(!asset) return;
    const copyToClipboard = (text) => {
        if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
        let textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed"; textArea.style.left = "-9999px";
        document.body.appendChild(textArea);
        textArea.focus(); textArea.select();
        return new Promise((resolve, reject) => { document.execCommand('copy') ? resolve() : reject(); textArea.remove(); });
    };
    copyToClipboard(asset.urlFull).then(() => {
        const toast = document.createElement('div');
        toast.className = 'fixed top-24 left-1/2 -translate-x-1/2 z-[300] glass-panel px-6 py-2 rounded-full text-emerald-400 font-medium text-sm border border-emerald-500/30 animate-bounce shadow-xl flex items-center gap-2 pointer-events-none';
        toast.innerHTML = '<i class="fa-solid fa-link"></i> Link Copied!';
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.5s'; setTimeout(() => toast.remove(), 500); }, 2000);
    });
}

// --- Queue ---
class UploadQueue {
    constructor() { this.queue = []; this.isProcessing = false; }
    add(files) {
        this.show();
        Array.from(files).forEach(file => {
            const id = Math.random().toString(36).substr(2, 9);
            const item = { id, file, status: 'pending', element: null, controller: new AbortController() };
            this.queue.push(item);
            this.createUI(item);
        });
        this.process();
    }
    show() { if(elements.queueContainer) elements.queueContainer.classList.remove('translate-y-4', 'opacity-0'); }
    createUI(item) {
        if(!elements.queueList) return;
        const el = document.createElement('div');
        el.className = 'p-2 rounded-lg bg-white/5 flex items-center gap-3 border border-white/5 transition-all duration-300';
        el.innerHTML = `<div class="w-8 h-8 rounded bg-white/10 flex items-center justify-center shrink-0"><i class="fa-regular fa-image text-slate-300 text-xs"></i></div>
            <div class="flex-1 min-w-0">
                <div class="flex justify-between items-center mb-1">
                    <p class="text-xs font-medium text-white truncate pr-2 max-w-[150px]">${item.file.name}</p>
                    <span class="text-[10px] uppercase tracking-wider text-slate-400 status-text">Pending</span>
                </div>
                <div class="w-full bg-slate-700/50 rounded-full h-1 overflow-hidden"><div class="progress-bar bg-emerald-400 h-full w-0 transition-all duration-300"></div></div>
            </div>
            <button onclick="uploader.cancel('${item.id}')" class="w-6 h-6 rounded-full hover:bg-white/10 flex items-center justify-center text-slate-400 hover:text-white transition-colors"><i class="fa-solid fa-xmark text-xs"></i></button>`;
        elements.queueList.appendChild(el);
        elements.queueList.scrollTop = elements.queueList.scrollHeight;
        item.element = el;
    }
    cancel(id) {
        const idx = this.queue.findIndex(i => i.id === id);
        if (idx === -1) return;
        const item = this.queue[idx];
        if (item.status === 'uploading') item.controller.abort();
        this.queue.splice(idx, 1);
        if(item.element) item.element.remove();
        if (item.status === 'uploading') { this.isProcessing = false; setTimeout(() => this.process(), 300); }
        if (elements.queueList && elements.queueList.children.length === 0) elements.queueContainer.classList.add('translate-y-4', 'opacity-0');
    }
    clearCompleted() {
        const pending = this.queue.filter(i => i.status === 'pending' || i.status === 'uploading');
        this.queue.forEach(i => { if ((i.status === 'success' || i.status === 'error') && i.element) i.element.remove(); });
        this.queue = pending;
        if (this.queue.length === 0 && elements.queueContainer) elements.queueContainer.classList.add('translate-y-4', 'opacity-0');
    }
    async process() {
        if (this.isProcessing || this.queue.length === 0) return;
        const item = this.queue.find(i => i.status === 'pending');
        if (!item) return;
        this.isProcessing = true;
        item.status = 'uploading';
        await this.upload(item);
        this.isProcessing = false;
        setTimeout(() => this.process(), 300);
    }
    async upload(item) {
        const formData = new FormData();
        formData.append('file', item.file);
        this.updateUI(item, 'uploading', 50);
        try {
            const res = await fetch('/upload', { method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCsrfToken() }, signal: item.controller.signal });
            const data = await res.json();
            if (res.status === 401) { window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname); return; }
            if (res.status === 403) { this.updateUI(item, 'error', 0); item.status = 'error'; if (data.error) alert(data.error); return; }
            if (res.ok) {
                this.updateUI(item, 'success', 100);
                if (data.assets) this.addToGallery(data.assets[0]);
                item.status = 'success';
            } else { throw new Error(data.error || 'Upload failed'); }
        } catch (e) {
            if (e.name !== 'AbortError') { this.updateUI(item, 'error', 0); item.status = 'error'; }
        }
    }
    updateUI(item, status, progress) {
        if (!item.element) return;
        const bar = item.element.querySelector('.progress-bar');
        const txt = item.element.querySelector('.status-text');
        const btn = item.element.querySelector('button');
        if(status === 'uploading') { txt.innerText = '...'; bar.style.width = progress+'%'; }
        if(status === 'success') { txt.innerText = 'Done'; bar.style.width = '100%'; txt.className += ' text-emerald-400'; if(btn) btn.remove(); }
        if(status === 'error') { txt.innerText = 'Err'; bar.style.width = '100%'; bar.className = 'progress-bar bg-rose-400 h-full'; }
    }
    addToGallery(asset) {
        const mapped = { id: asset.wp_media_id || Math.random(), urlFull: asset.url_full, urlThumb: asset.url_thumbnail || asset.url_full, title: asset.title, fileName: asset.file_name, type: asset.mime_type, date: new Date().toISOString() };
        state.galleryData.unshift(mapped);
        elements.grid.insertAdjacentHTML('afterbegin', createAssetCard(mapped, 0));
    }
}

const uploader = new UploadQueue();

function toggleLoader(show) {
    if(!elements.loader) return;
    show ? (elements.loader.classList.remove('hidden'), elements.loader.classList.add('flex')) : (elements.loader.classList.add('hidden'), elements.loader.classList.remove('flex'));
}

function submitUpload() {
    const input = document.getElementById('uploadInput');
    if (input && input.files.length) { uploader.add(input.files); input.value = ''; }
}

function initGlobalListeners() {
    document.addEventListener('dragenter', () => elements.dragOverlay && elements.dragOverlay.classList.remove('hidden'));
    document.addEventListener('dragleave', (e) => { if(e.relatedTarget === null && elements.dragOverlay) elements.dragOverlay.classList.add('hidden'); });
    document.addEventListener('dragover', (e) => e.preventDefault());
    document.addEventListener('drop', (e) => {
        e.preventDefault(); 
        if(elements.dragOverlay) elements.dragOverlay.classList.add('hidden');
        if(e.dataTransfer.files.length) uploader.add(e.dataTransfer.files);
    });
    document.addEventListener('keydown', (e) => {
        if (elements.lightbox && !elements.lightbox.classList.contains('hidden')) {
            if (e.key === 'Escape') closeLightbox();
            if (e.key === 'ArrowRight') nextImage();
            if (e.key === 'ArrowLeft') prevImage();
        }
    });
    if(elements.lightbox) {
        elements.lightbox.addEventListener('click', (e) => { if (e.target === elements.lightbox) closeLightbox(); });
        elements.lightbox.addEventListener('touchstart', (e) => { state.touchStartX = e.changedTouches[0].screenX; state.touchStartY = e.changedTouches[0].screenY; }, {passive: true});
        elements.lightbox.addEventListener('touchend', (e) => {
            const deltaX = e.changedTouches[0].screenX - state.touchStartX;
            const deltaY = e.changedTouches[0].screenY - state.touchStartY;
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) deltaX < 0 ? nextImage() : prevImage();
            else if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > 50 && deltaY > 0) closeLightbox();
        }, {passive: true});
    }
}