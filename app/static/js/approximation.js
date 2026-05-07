// static/js/approximation.js

let currentData = { coords: [], coeffs: [], params: [] };
let currentBladeId = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadBladesList();
    const urlParams = new URLSearchParams(window.location.search);
    const preselectBladeId = urlParams.get('blade_id');
    if (preselectBladeId) {
        const select = document.getElementById('bladeSelect');
        if (select && select.querySelector(`option[value="${preselectBladeId}"]`)) {
            select.value = preselectBladeId;
            await onBladeSelect(preselectBladeId);
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }
});

async function loadBladesList() {
    try {
        const res = await fetch('/approximation/blades');
        if (!res.ok) throw new Error('Ошибка загрузки списка');
        const blades = await res.json();
        const sel = document.getElementById('bladeSelect');
        sel.innerHTML = '<option value="">-- Выберите лопатку --</option>' +
            blades.map(b => `<option value="${b.id}">${escapeHtml(b.name)} (ID: ${b.id})</option>`).join('');
    } catch (err) {
        console.error('Ошибка:', err);
        showError('Не удалось загрузить список лопаток');
    }
}

async function onBladeSelect(bladeId) {
    if (!bladeId) {
        document.getElementById('results').style.display = 'none';
        document.getElementById('retryBtn').style.display = 'none';
        return;
    }
    currentBladeId = bladeId;
    await executeApproximation();
}

async function executeApproximation() {
    if (!currentBladeId) return;
    setLoading(true);
    document.getElementById('results').style.display = 'none';
    document.getElementById('error').style.display = 'none';
    document.getElementById('retryBtn').style.display = 'none';

    try {
        const res = await fetch(`/approximation/execute/${currentBladeId}`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Ошибка выполнения аппроксимации');
        await loadResults(currentBladeId);
    } catch (e) {
        showError('Ошибка: ' + e.message);
        document.getElementById('retryBtn').style.display = 'inline-block';
    } finally {
        setLoading(false);
    }
}

async function loadResults(bladeId) {
    try {
        const [resData, resPlot] = await Promise.all([
            fetch(`/approximation/results/${bladeId}`).then(async r => {
                if (!r.ok) throw new Error('Ошибка загрузки результатов');
                return r.json();
            }),
            fetch(`/approximation/plot/${bladeId}`).then(async r => {
                if (!r.ok) throw new Error('Ошибка загрузки графика');
                return r.json();
            })
        ]);

        document.getElementById('plotImg').src = resPlot.image;

        document.getElementById('coordsBody').innerHTML = (resData.transformed_coords || []).map(c =>
            `<tr><td>${c.type === 'upper' ? 'Верхний' : 'Нижний'}</td><td>${c.x.toFixed(6)}</td><td>${c.y.toFixed(6)}</td></tr>`
        ).join('') || '<tr><td colspan="3" style="text-align:center;color:#64748b">Нет данных</td></tr>';

        document.getElementById('coeffsBody').innerHTML = (resData.legendre_coeffs || []).map(c =>
            `<tr><td>${c.idx}</td><td>${c.upper.toFixed(6)}</td><td>${c.lower.toFixed(6)}</td></tr>`
        ).join('') || '<tr><td colspan="3" style="text-align:center;color:#64748b">Нет данных</td></tr>';

        document.getElementById('paramsBody').innerHTML = (resData.approximation_params || []).map(p =>
            `<tr><td>${p.type === 'upper' ? 'Верхний' : 'Нижний'}</td><td>${p.max_val?.toFixed(4) || '—'}</td><td>${p.x_max?.toFixed(4) || '—'}</td><td>${p.r2?.toFixed(4) || '—'}</td></tr>`
        ).join('') || '<tr><td colspan="4" style="text-align:center;color:#64748b">Нет данных</td></tr>';

        currentData.coords = resData.transformed_coords || [];
        currentData.coeffs = resData.legendre_coeffs || [];
        currentData.params = resData.approximation_params || [];

        document.getElementById('results').style.display = 'block';
        switchTab('plot');
    } catch (e) {
        showError('Ошибка загрузки данных: ' + e.message);
        document.getElementById('results').style.display = 'none';
        document.getElementById('retryBtn').style.display = 'inline-block';
    }
}

function switchTab(tabName) {
    const btns = document.querySelectorAll('.tab-btn');
    const contents = document.querySelectorAll('.tab-content');
    const map = ['plot', 'coords', 'coeffs', 'params'];
    const idx = map.indexOf(tabName);
    if (idx !== -1) {
        btns.forEach(btn => btn.classList.remove('active'));
        contents.forEach(c => c.classList.remove('active'));
        btns[idx].classList.add('active');
        contents[idx].classList.add('active');
    }
}

function showError(message) {
    const el = document.getElementById('error');
    el.textContent = message;
    el.style.display = 'block';
}

function setLoading(show) {
    const el = document.getElementById('loading');
    if (el) el.style.display = show ? 'block' : 'none';
}

function savePlot() {
    const link = document.createElement('a');
    link.href = document.getElementById('plotImg').src;
    link.download = 'approximation_plot.png';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function saveTable(type) {
    const headers = type === 'coords' ? ['Type','X','Y'] :
                    type === 'coeffs' ? ['Index','Upper','Lower'] :
                    ['Type','Max_Y','X_at_Max','R2'];
    const data = currentData[type];
    let csv = headers.join(',') + '\n';
    if (type === 'coords') data.forEach(r => csv += `${r.type},${r.x},${r.y}\n`);
    if (type === 'coeffs') data.forEach(r => csv += `${r.idx},${r.upper},${r.lower}\n`);
    if (type === 'params') data.forEach(r => csv += `${r.type},${r.max_val??''},${r.x_max??''},${r.r2??''}\n`);
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `approx_${type}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Делаем функции глобальными для вызова из HTML-атрибутов
window.onBladeSelect = onBladeSelect;
window.executeApproximation = executeApproximation;
window.switchTab = switchTab;
window.savePlot = savePlot;
window.saveTable = saveTable;