let currentData = { coords: [], coeffs: [], params: [] };
let currentItemId = null;
let currentItemType = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadItemsList();
    const urlParams = new URLSearchParams(window.location.search);
    const preselectId = urlParams.get('item_id');
    const preselectType = urlParams.get('item_type');
    if (preselectId && preselectType) {
        const select = document.getElementById('bladeSelect');
        const option = select.querySelector(`option[data-id="${preselectId}"][data-type="${preselectType}"]`);
        if (option) {
            select.value = option.value;
            await onItemSelect(preselectId, preselectType);
        }
        window.history.replaceState({}, document.title, window.location.pathname);
    }
});

async function loadItemsList() {
    try {
        const res = await fetch('/approximation/items');
        if (!res.ok) throw new Error('Ошибка загрузки списка');
        const items = await res.json();
        const sel = document.getElementById('bladeSelect');
        sel.innerHTML = '<option value="">-- Выберите объект --</option>';
        for (const item of items) {
            const option = document.createElement('option');
            option.value = `${item.type}_${item.id}`;
            option.textContent = `${item.name} (${item.type === 'blade' ? 'лопатка' : 'сборка'})`;
            option.dataset.id = item.id;
            option.dataset.type = item.type;
            sel.appendChild(option);
        }
    } catch (err) {
        console.error('Ошибка:', err);
        showError('Не удалось загрузить список объектов');
    }
}

async function onItemSelect(id, type) {
    if (!id) {
        document.getElementById('results').style.display = 'none';
        document.getElementById('retryBtn').style.display = 'none';
        return;
    }
    currentItemId = id;
    currentItemType = type;
    await executeApproximation();
}

async function executeApproximation() {
    if (!currentItemId || !currentItemType) return;
    setLoading(true);
    document.getElementById('results').style.display = 'none';
    document.getElementById('error').style.display = 'none';
    document.getElementById('retryBtn').style.display = 'none';

    try {
        if (currentItemType === 'blade') {
            // 1. Запускаем аппроксимацию лопатки
            const execRes = await fetch(`/approximation/execute/${currentItemId}`, { method: 'POST' });
            const execData = await execRes.json();
            if (!execRes.ok) throw new Error(execData.error || 'Ошибка выполнения аппроксимации');
            // 2. Загружаем результаты и график
            await loadResults(currentItemId);
        } else {
            // Для сборки: прямой запрос, возвращает полные данные
            const res = await fetch(`/approximation/execute_assembly/${currentItemId}`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Ошибка выполнения аппроксимации');
            displayResults(data);
        }
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
        // Приводим к формату, ожидаемому displayResults
        const data = {
            plot: resPlot.image,
            transformed_coords: resData.transformed_coords,
            legendre_coeffs: resData.legendre_coeffs.map(c => ({ upper: c.upper, lower: c.lower })),
            approximation_params: resData.approximation_params
        };
        displayResults(data);
    } catch (e) {
        showError('Ошибка загрузки данных: ' + e.message);
        document.getElementById('results').style.display = 'none';
        document.getElementById('retryBtn').style.display = 'inline-block';
    }
}

// Замените старую функцию displayResults на эту:

function displayResults(data) {
    // data может быть от одной лопатки (старый формат) или от сборки (с полями outer, inner)
    if (data.outer && data.inner) {
        // Это сборка из двух лопаток
        document.getElementById('plotImg').src = data.plot;

        // Объединяем координаты, коэффициенты и параметры для отображения в таблицах
        const combinedCoords = [];
        const combinedCoeffs = [];
        const combinedParams = [];

        // Внешняя лопатка
        for (const c of data.outer.transformed_coords) {
            combinedCoords.push({ ...c, blade_name: data.outer.blade_name });
        }
        data.outer.legendre_coeffs.forEach((c, idx) => {
            combinedCoeffs.push({ idx, upper: c.upper, lower: c.lower, blade_name: data.outer.blade_name });
        });
        combinedParams.push({ profile: 'верхний', ...data.outer.params.upper, blade_name: data.outer.blade_name });
        combinedParams.push({ profile: 'нижний', ...data.outer.params.lower, blade_name: data.outer.blade_name });

        // Внутренняя лопатка
        for (const c of data.inner.transformed_coords) {
            combinedCoords.push({ ...c, blade_name: data.inner.blade_name });
        }
        data.inner.legendre_coeffs.forEach((c, idx) => {
            combinedCoeffs.push({ idx, upper: c.upper, lower: c.lower, blade_name: data.inner.blade_name });
        });
        combinedParams.push({ profile: 'верхний', ...data.inner.params.upper, blade_name: data.inner.blade_name });
        combinedParams.push({ profile: 'нижний', ...data.inner.params.lower, blade_name: data.inner.blade_name });

        // Отображаем координаты (добавляем колонку "Лопатка")
        document.getElementById('coordsBody').innerHTML = combinedCoords.map(c =>
            `<tr><td>${escapeHtml(c.blade_name)}</td><td>${c.type === 'upper' ? 'Верхний' : 'Нижний'}</td><td>${c.x.toFixed(6)}</td><td>${c.y.toFixed(6)}</td></tr>`
        ).join('') || '<tr><td colspan="4" class="status-message">Нет данных</td></tr>';

        // Отображаем коэффициенты
        document.getElementById('coeffsBody').innerHTML = combinedCoeffs.map(c =>
            `<tr><td>${escapeHtml(c.blade_name)}</td><td>${c.idx}</td><td>${c.upper.toFixed(6)}</td><td>${c.lower.toFixed(6)}</td></tr>`
        ).join('') || '<tr><td colspan="4" class="status-message">Нет данных</td></tr>';

        // Отображаем параметры
        document.getElementById('paramsBody').innerHTML = combinedParams.map(p =>
            `<tr><td>${escapeHtml(p.blade_name)}</td><td>${p.profile === 'верхний' ? 'Верхний' : 'Нижний'}</td><td>${p.max_y?.toFixed(4) || '—'}</td><td>${p.x_at_max?.toFixed(4) || '—'}</td><td>${p.r2?.toFixed(4) || '—'}</td></tr>`
        ).join('') || '<tr><td colspan="5" class="status-message">Нет данных</td></tr>';

        // Сохраняем данные для экспорта (объединённые)
        currentData.coords = combinedCoords;
        currentData.coeffs = combinedCoeffs;
        currentData.params = combinedParams;
    } else {
        // Старый формат (одна лопатка) — оставляем без изменений
        document.getElementById('plotImg').src = data.plot;
        document.getElementById('coordsBody').innerHTML = (data.transformed_coords || []).map(c =>
            `<tr><td>${c.type === 'upper' ? 'Верхний' : 'Нижний'}</td><td>${c.x.toFixed(6)}</td><td>${c.y.toFixed(6)}</td><tr>`
        ).join('') || '<tr><td colspan="3" class="status-message">Нет данных</td></tr>';
        document.getElementById('coeffsBody').innerHTML = (data.legendre_coeffs || []).map((c, idx) =>
            `<tr><td>${idx}</td><td>${c.upper.toFixed(6)}</td><td>${c.lower.toFixed(6)}</td></tr>`
        ).join('') || '<tr><td colspan="3" class="status-message">Нет данных</td></tr>';
        document.getElementById('paramsBody').innerHTML = (data.approximation_params || []).map(p =>
            `<tr><td>${p.type === 'upper' ? 'Верхний' : 'Нижний'}</td><td>${p.max_val?.toFixed(4) || '—'}</td><td>${p.x_max?.toFixed(4) || '—'}</td><td>${p.r2?.toFixed(4) || '—'}</td></tr>`
        ).join('') || '<tr><td colspan="4" class="status-message">Нет данных</td></tr>';
        currentData.coords = data.transformed_coords || [];
        currentData.coeffs = data.legendre_coeffs || [];
        currentData.params = data.approximation_params || [];
    }

    document.getElementById('results').style.display = 'block';
    switchTab('plot');
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

window.onItemSelect = onItemSelect;
window.executeApproximation = executeApproximation;
window.switchTab = switchTab;
window.savePlot = savePlot;
window.saveTable = saveTable;