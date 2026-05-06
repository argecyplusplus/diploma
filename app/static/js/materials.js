// static/js/materials.js
let materials = [];      // химические элементы
let alloys = [];         // сплавы
let allMaterials = [];   // объединённый список (элементы + сплавы)

document.addEventListener('DOMContentLoaded', () => {
    loadAllMaterials();
    document.getElementById('matForm').onsubmit = saveMaterial;
    document.getElementById('alloyForm').onsubmit = saveAlloy;
});

// ===== ЗАГРУЗКА ДАННЫХ =====
async function loadAllMaterials() {
    await Promise.all([loadMaterials(), loadAlloys()]);
    allMaterials = [...materials, ...alloys];
}

async function loadMaterials() {
    try {
        const res = await fetch('/api/elements');
        if (!res.ok) throw new Error('Ошибка загрузки');
        materials = await res.json();
        renderMaterialsTable();
    } catch (e) {
        document.getElementById('elementsTable').innerHTML = `<tr><td colspan="7" class="text-center" style="color:#ef4444">Ошибка: ${e.message}</td></tr>`;
    }
}

async function loadAlloys() {
    try {
        const res = await fetch('/api/alloys');
        if (!res.ok) throw new Error('Ошибка загрузки');
        alloys = await res.json();
        renderAlloysTable();
    } catch (e) {
        document.getElementById('alloysTable').innerHTML = `<tr><td colspan="5" class="text-center" style="color:#ef4444">Ошибка: ${e.message}</td></tr>`;
    }
}

function renderMaterialsTable() {
    const tbody = document.getElementById('elementsTable');
    if (!materials.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center">Нет материалов</td></tr>`;
        return;
    }
    tbody.innerHTML = materials.map(m => `
        <tr class="clickable-row" data-material-id="${m.material_id}" onclick="editMaterial(${m.material_id})">
            <td>${m.material_id}</td>
            <td>${escapeHtml(m.name)}</td>
            <td>${m.type || '—'}</td>
            <td>${m.density?.toFixed(1) || '—'}</td>
            <td>${m.thermal_conductivity?.toFixed(2) || '—'}</td>
            <td>${m.heat_capacity?.toFixed(1) || '—'}</td>
            <td>
                <div class="table-actions">
                    <button class="btn-edit" onclick="event.stopPropagation(); editMaterial(${m.material_id})">✏️</button>
                    <button class="btn-delete" onclick="event.stopPropagation(); deleteMaterialById(${m.material_id})">🗑️</button>
                </div>
             </td>
        </tr>
    `).join('');
}

function renderAlloysTable() {
    const tbody = document.getElementById('alloysTable');
    if (!alloys.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center">Нет сплавов</td></tr>`;
        return;
    }
    tbody.innerHTML = alloys.map(a => `
        <tr class="clickable-row" data-alloy-id="${a.material_id}" onclick="viewAlloy(${a.material_id})">
            <td>${a.material_id}</td>
            <td>${escapeHtml(a.name)}</td>
            <td>${a.density?.toFixed(1) || '—'}</td>
            <td>${a.melting_point?.toFixed(0) || '—'}</td>
            <td>
                <div class="table-actions">
                    <button class="btn-edit" onclick="event.stopPropagation(); editAlloy(${a.material_id})">✏️</button>
                    <button class="btn-delete" onclick="event.stopPropagation(); deleteAlloyById(${a.material_id})">🗑️</button>
                </div>
             </td>
        </tr>
    `).join('');
}

// ===== МАТЕРИАЛЫ =====
function openMaterialModal(id = null) {
    document.getElementById('matId').value = id || '';
    document.getElementById('matModalTitle').textContent = id ? 'Редактировать' : 'Добавить';
    document.getElementById('matDeleteBtn').style.display = id ? 'inline-block' : 'none';
    document.getElementById('matForm').reset();
    if (id) {
        const m = materials.find(x => x.material_id == id);
        if (m) {
            document.getElementById('matName').value = m.name;
            document.getElementById('elementType').value = m.type || 'Металл';
            document.getElementById('matDensity').value = m.density || '';
            document.getElementById('matHardness').value = m.hardness || '';
            document.getElementById('matLambda').value = m.thermal_conductivity || '';
            document.getElementById('matCp').value = m.heat_capacity || '';
            document.getElementById('matTmelt').value = m.melting_point || '';
            document.getElementById('matKLT').value = m.thermal_expansion_coef || '';
        }
    }
    openModal('materialModal');
}

async function saveMaterial(e) {
    e.preventDefault();
    const id = document.getElementById('matId').value;
    const payload = {
        name: document.getElementById('matName').value,
        type: document.getElementById('elementType').value,
        density: +document.getElementById('matDensity').value,
        thermal_conductivity: +document.getElementById('matLambda').value,
        heat_capacity: +document.getElementById('matCp').value,
        thermal_expansion_coef: +document.getElementById('matKLT').value,
        hardness: document.getElementById('matHardness').value ? +document.getElementById('matHardness').value : null,
        melting_point: document.getElementById('matTmelt').value ? +document.getElementById('matTmelt').value : null
    };
    try {
        const url = id ? `/api/elements/${id}` : '/api/elements';
        const method = id ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method,
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || 'Ошибка сохранения');
        }
        closeModal('materialModal');
        await loadAllMaterials(); // обновляем оба списка
    } catch (err) {
        alert('Ошибка: ' + err.message);
    }
}

async function deleteMaterial() {
    const id = document.getElementById('matId').value;
    if (confirm('Удалить элемент? Все сплавы с этим компонентом будут пересчитаны.')) {
        try {
            await fetch(`/api/elements/${id}`, { method: 'DELETE' });
            closeModal('materialModal');
            await loadAllMaterials();
        } catch (e) { alert('Ошибка: ' + e.message); }
    }
}

async function deleteMaterialById(id) {
    if (confirm('Удалить этот элемент?')) {
        try {
            await fetch(`/api/elements/${id}`, { method: 'DELETE' });
            await loadAllMaterials();
        } catch (e) { alert('Ошибка: ' + e.message); }
    }
}

function editMaterial(id) { openMaterialModal(id); }

// ===== СПЛАВЫ =====
async function openAlloyModal(id = null) {
    document.getElementById('alloyId').value = id || '';
    document.getElementById('alloyModalTitle').textContent = id ? 'Редактировать сплав' : 'Создать сплав';
    document.getElementById('alloyDeleteBtn').style.display = id ? 'inline-block' : 'none';
    document.getElementById('alloyComponents').innerHTML = '';
    document.getElementById('alloyForm').reset();

    if (id) {
        try {
            const res = await fetch(`/api/alloys/${id}`);
            const data = await res.json();
            document.getElementById('alloyName').value = data.alloy.name;
            data.components.forEach(c => {
                addAlloyComponentRow(c.component_material_id, (c.mass_fraction * 100).toFixed(4));
            });
            validateMassSum();
        } catch (e) { console.error(e); }
    } else {
        addAlloyComponentRow(); addAlloyComponentRow();
    }
    openModal('alloyModal');
}

function addAlloyComponentRow(selectedId = '', fraction = '') {
    const div = document.createElement('div');
    div.className = 'comp-row';
    const options = allMaterials.map(m => `<option value="${m.material_id}" ${m.material_id == selectedId ? 'selected' : ''}>${escapeHtml(m.name)}</option>`).join('');
    div.innerHTML = `
        <select class="comp-select"><option value="">Выберите...</option>${options}</select>
        <input type="number" class="comp-frac" placeholder="%" min="0" max="100" step="any" value="${fraction}" oninput="validateMassSum()">
        <button type="button" class="btn-remove" onclick="this.parentElement.remove(); validateMassSum()">✕</button>
    `;
    document.getElementById('alloyComponents').appendChild(div);
}

function validateMassSum() {
    const inputs = document.querySelectorAll('.comp-frac');
    let sum = 0;
    inputs.forEach(i => {
        let val = i.value;
        if (typeof val === 'string') val = val.replace(',', '.');
        const v = parseFloat(val);
        if (!isNaN(v)) sum += v;
    });
    document.getElementById('massSum').textContent = sum.toFixed(2);
    const err = document.getElementById('massSumError');
    const isValid = Math.abs(sum - 100) <= 0.1;
    err.classList.toggle('show', !isValid);
    return isValid;
}

async function saveAlloy(e) {
    e.preventDefault();
    if (!validateMassSum()) { alert('Сумма массовых долей должна быть 100%!'); return; }
    const id = document.getElementById('alloyId').value;
    const name = document.getElementById('alloyName').value;
    const components = [];
    document.querySelectorAll('.comp-row').forEach(row => {
        const matId = row.querySelector('.comp-select').value;
        const frac = parseFloat(row.querySelector('.comp-frac').value.replace(',', '.')) / 100;
        if (matId && frac > 0) components.push({ component_material_id: +matId, mass_fraction: frac });
    });
    if (components.length < 2) { alert('Нужно минимум 2 компонента'); return; }
    try {
        const url = id ? `/api/alloys/${id}` : '/api/alloys';
        const method = id ? 'PUT' : 'POST';
        const res = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify({ name, components }) });
        if (!res.ok) throw new Error('Ошибка сохранения');
        closeModal('alloyModal');
        await loadAllMaterials();
    } catch (err) { alert('Ошибка: ' + err.message); }
}

async function deleteAlloy() {
    const id = document.getElementById('alloyId').value;
    if (confirm('Удалить сплав?')) {
        try {
            await fetch(`/api/alloys/${id}`, { method: 'DELETE' });
            closeModal('alloyModal');
            await loadAllMaterials();
        } catch (e) { alert('Ошибка: ' + e.message); }
    }
}

async function deleteAlloyById(id) {
    if (confirm('Удалить этот сплав?')) {
        try {
            await fetch(`/api/alloys/${id}`, { method: 'DELETE' });
            await loadAllMaterials();
        } catch (e) { alert('Ошибка: ' + e.message); }
    }
}

function editAlloy(id) { openAlloyModal(id); }

async function viewAlloy(id) {
    try {
        const res = await fetch(`/api/alloys/${id}`);
        const data = await res.json();
        document.getElementById('viewAlloyName').textContent = data.alloy.name;
        document.getElementById('viewDensity').textContent = data.alloy.density?.toFixed(1) || '—';
        document.getElementById('viewLambda').textContent = data.alloy.thermal_conductivity?.toFixed(2) || '—';
        document.getElementById('viewCp').textContent = data.alloy.heat_capacity?.toFixed(1) || '—';
        document.getElementById('viewTmelt').textContent = data.alloy.melting_point?.toFixed(0) || '—';
        document.getElementById('viewKLT').textContent = data.alloy.thermal_expansion_coef?.toFixed(2) || '—';
        document.getElementById('viewHardness').textContent = data.alloy.hardness?.toFixed(1) || '—';
        document.getElementById('viewAlloyComps').innerHTML = data.components.map(c => {
            const mat = allMaterials.find(m => m.material_id == c.component_material_id);
            const name = mat ? escapeHtml(mat.name) : `Материал #${c.component_material_id}`;
            return `<tr><td>${name}</td><td>${(c.mass_fraction * 100).toFixed(2)}%</tr>`;
        }).join('');
        openModal('viewAlloyModal');
    } catch (e) { alert('Ошибка: ' + e.message); }
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}