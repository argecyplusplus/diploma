let bladesData = [];
let assembliesData = [];
let currentCoords = { upper: [], lower: [] };
let currentViewBladeId = null;
let editingCoords = { upper: [], lower: [] };

document.addEventListener('DOMContentLoaded', () => {
    loadBlades();
    loadAssemblies();
});

async function loadBlades() {
    showLoading(true);
    try {
        const res = await fetch('/api/blades');
        if (!res.ok) {
            if (res.status === 403) {
                alert('⚠️ База данных не выбрана! Откройте настройки.');
                const settingsModal = document.getElementById('settingsModal');
                if (settingsModal) settingsModal.classList.add('active');
                return;
            }
            throw new Error('Ошибка загрузки: ' + res.status);
        }
        bladesData = await res.json();
        renderBladesTable();
    } catch (e) {
        showError('Не удалось загрузить список лопаток: ' + e.message);
    } finally {
        showLoading(false);
    }
}

async function loadAssemblies() {
    try {
        const res = await fetch('/api/assemblies');
        if (!res.ok) throw new Error('Ошибка загрузки');
        assembliesData = await res.json();
        renderAssembliesTable();
    } catch (e) {
        console.error('Ошибка загрузки объединений:', e);
    }
}

function renderBladesTable() {
    const tbody = document.getElementById('bladesTableBody');
    if (bladesData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">✏️ Лопаток пока нет. Нажмите «+ Создать профиль»</td></tr>`;
        return;
    }
    tbody.innerHTML = bladesData.map(blade => `
        <tr class="clickable-row" data-blade-id="${blade.blade_id}" onclick="viewBladeCoords(${blade.blade_id})">
            <td>${blade.blade_id}</td>
            <td>${escapeHtml(blade.name)}</td>
            <td>
                <div class="table-actions">
                    <button class="btn-edit" onclick="event.stopPropagation(); editBlade(${blade.blade_id})">Редактировать</button>
                    <button class="btn-approx" onclick="event.stopPropagation(); goToApproximation(${blade.blade_id})">Аппроксимировать</button>
                    <button class="btn-delete" onclick="event.stopPropagation(); confirmDeleteBlade(${blade.blade_id})">Удалить</button>
                </div>
            </td>
        </tr>
    `).join('');
}

function renderAssembliesTable() {
    const tbody = document.getElementById('assembliesTableBody');
    if (!assembliesData || assembliesData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:20px;color:#64748b">Объединений пока нет</td></tr>`;
        return;
    }
    tbody.innerHTML = assembliesData.map(a => `
        <tr class="clickable-row" data-assembly-id="${a.blade_assembly_id}" onclick="openViewAssemblyModal(${a.blade_assembly_id}, '${escapeHtml(a.name)}')">
            <td>${a.blade_assembly_id}</td>
            <td>${escapeHtml(a.name)}</td>
            <td></td>
        </tr>
    `).join('');
}

// ================= CRUD ЛОПАТОК =================
function openCreateBladeModal() {
    if (typeof currentDb === 'undefined' || !currentDb) {
        alert('⚠️ Сначала выберите или создайте базу данных в настройках!');
        const settingsModal = document.getElementById('settingsModal');
        if (settingsModal) settingsModal.classList.add('active');
        return;
    }
    document.getElementById('bladeModalTitle').textContent = 'Создать лопатку';
    document.getElementById('bladeId').value = '';
    document.getElementById('bladeName').value = '';
    document.getElementById('deleteBladeBtn').style.display = 'none';
    currentCoords = { upper: [], lower: [] };
    editingCoords = { upper: [], lower: [] };
    renderCoordTables();
    openModal('bladeModal');
}

async function editBlade(bladeId) {
    const blade = bladesData.find(b => b.blade_id === bladeId);
    if (!blade) return;
    document.getElementById('bladeModalTitle').textContent = 'Редактировать лопатку';
    document.getElementById('bladeId').value = blade.blade_id;
    document.getElementById('bladeName').value = blade.name;
    document.getElementById('deleteBladeBtn').style.display = 'inline-block';
    await loadBladeCoordinates(bladeId);
    editingCoords.upper = [...currentCoords.upper];
    editingCoords.lower = [...currentCoords.lower];
    renderCoordTables();
    openModal('bladeModal');
}

async function loadBladeCoordinates(bladeId) {
    try {
        const res = await fetch(`/api/blades/${bladeId}/coordinates`);
        if (!res.ok) return;
        const coords = await res.json();
        currentCoords.upper = coords.filter(c => c.profile_type === 'upper');
        currentCoords.lower = coords.filter(c => c.profile_type === 'lower');
    } catch (e) {
        console.error('Ошибка загрузки координат:', e);
    }
}

function renderCoordTables() {
    renderCoordTable('upper');
    renderCoordTable('lower');
}

function renderCoordTable(type) {
    const tbody = document.getElementById(`${type}CoordsTableBody`);
    const coords = editingCoords[type];
    if (coords.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:#64748b;padding:20px">Нет точек. Загрузите файл или добавьте вручную.</td></tr>`;
        return;
    }
    tbody.innerHTML = coords.map((coord, index) => `
        <tr>
            <td>${index + 1}</td>
            <td><input type="number" step="any" value="${coord.x}" onchange="updateCoord('${type}', ${index}, 'x', this.value)"></td>
            <td><input type="number" step="any" value="${coord.y}" onchange="updateCoord('${type}', ${index}, 'y', this.value)"></td>
            <td><button class="action-btn" onclick="removeCoordFromTable('${type}', ${index})">✕</button></td>
        </tr>
    `).join('');
}

function updateCoord(type, index, field, value) {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
        editingCoords[type][index][field] = numValue;
    }
}

function addCoordPointToTable(type) {
    editingCoords[type].push({ profile_type: type, x: 0, y: 0 });
    renderCoordTable(type);
}

function removeCoordFromTable(type, index) {
    editingCoords[type].splice(index, 1);
    renderCoordTable(type);
}

async function loadCoordsFromFile(profileType, fileInput) {
    const file = fileInput.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const lines = text.trim().split('\n');
        let loadedCount = 0;
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;
            const parts = trimmed.split(/[\s,;]+/);
            if (parts.length >= 2) {
                const x = parseFloat(parts[0]);
                const y = parseFloat(parts[1]);
                if (!isNaN(x) && !isNaN(y)) {
                    editingCoords[profileType].push({ profile_type: profileType, x: x, y: y });
                    loadedCount++;
                }
            }
        }
        renderCoordTable(profileType);
        alert(`✅ Загружено ${loadedCount} точек для ${profileType === 'upper' ? 'верхнего' : 'нижнего'} профиля`);
    } catch (e) {
        alert(`❌ Ошибка чтения файла: ${e.message}`);
        console.error(e);
    } finally {
        fileInput.value = '';
    }
}

function switchCoordTab(type, event) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById(`${type}Tab`).classList.add('active');
}

async function saveBlade() {
    const bladeId = document.getElementById('bladeId').value;
    const name = document.getElementById('bladeName').value.trim();
    if (!name) {
        alert('Введите наименование лопатки');
        return;
    }
    const allCoords = [...editingCoords.upper, ...editingCoords.lower]
        .map(c => ({ profile_type: c.profile_type, x: parseFloat(c.x), y: parseFloat(c.y) }))
        .filter(c => !isNaN(c.x) && !isNaN(c.y));
    if (allCoords.length === 0 && !bladeId) {
        if (!confirm('Координаты профиля не добавлены. Продолжить?')) return;
    }
    try {
        const url = bladeId ? `/api/blades/${bladeId}` : '/api/blades';
        const method = bladeId ? 'PUT' : 'POST';
        const bladeRes = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!bladeRes.ok) {
            const err = await bladeRes.json();
            throw new Error(err.error || 'Ошибка сохранения');
        }
        const savedBlade = await bladeRes.json();
        const savedBladeId = savedBlade.blade_id || bladeId;
        if (allCoords.length > 0) {
            if (bladeId) await fetch(`/api/blades/${bladeId}/coordinates`, { method: 'DELETE' });
            const coordsRes = await fetch(`/api/blades/${savedBladeId}/coordinates`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(allCoords)
            });
            if (!coordsRes.ok) {
                const err = await coordsRes.json();
                throw new Error(err.error || 'Ошибка сохранения координат');
            }
        }
        closeModal('bladeModal');
        await loadBlades();
        alert('Лопатка сохранена!');
    } catch (e) {
        alert(`Ошибка: ${e.message}`);
    }
}

function confirmDeleteBlade(bladeId) {
    const blade = bladesData.find(b => b.blade_id === bladeId);
    if (!blade) return;
    if (confirm(`Удалить лопатку "${blade.name}"?\nЭто действие необратимо.`)) {
        deleteBlade(bladeId);
    }
}

async function deleteBlade(bladeId) {
    const id = bladeId || document.getElementById('bladeId').value;
    if (!id) return;
    try {
        const res = await fetch(`/api/blades/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Ошибка удаления');
        closeModal('bladeModal');
        await loadBlades();
        alert('Лопатка удалена');
    } catch (e) {
        alert(`Ошибка: ${e.message}`);
    }
}

// ================= ПРОСМОТР КООРДИНАТ =================
async function viewBladeCoords(bladeId) {
    currentViewBladeId = bladeId;
    const blade = bladesData.find(b => b.blade_id === bladeId);
    if (!blade) return;
    document.getElementById('viewProfileName').textContent = blade.name;
    try {
        const res = await fetch(`/api/blades/${bladeId}/coordinates`);
        if (!res.ok) throw new Error('Ошибка загрузки');
        const coords = await res.json();
        document.getElementById('viewCoordsBody').innerHTML = coords.map((c, i) => `
            <tr>
                <td>${i + 1}</td>
                <td>${c.x.toFixed(6)}</td>
                <td>${c.y.toFixed(6)}</td>
                <td>${c.profile_type === 'upper' ? 'Верхний' : 'Нижний'}</td>
            </tr>
        `).join('') || '<tr><td colspan="4" style="text-align:center;color:#64748b">Координат нет</td></tr>';
        openModal('viewCoordsModal');
    } catch (e) {
        alert('Не удалось загрузить координаты');
    }
}

function exportCoords() {
    if (!currentViewBladeId) return;
    const blade = bladesData.find(b => b.blade_id === currentViewBladeId);
    if (!blade) return;
    let csv = 'Type,X,Y\n';
    const coords = currentCoords.upper.concat(currentCoords.lower);
    coords.forEach(c => { csv += `${c.profile_type},${c.x},${c.y}\n`; });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${blade.name}_coords.csv`;
    link.click();
}

// ================= ОБЪЕДИНЕНИЯ =================
function renderMergeBladesSelects() {
    const outerSelect = document.getElementById('mergeOuterBlade');
    const innerSelect = document.getElementById('mergeInnerBlade');
    if (!outerSelect || !innerSelect) return;
    const options = ['<option value="">Выберите лопатку</option>'].concat(
        bladesData.map(b => `<option value="${b.blade_id}">${escapeHtml(b.name)} (#${b.blade_id})</option>`)
    ).join('');
    outerSelect.innerHTML = options;
    innerSelect.innerHTML = options;
}

function getSelectedMergeBladeIds() {
    const outerId = parseInt(document.getElementById('mergeOuterBlade')?.value || '', 10);
    const innerId = parseInt(document.getElementById('mergeInnerBlade')?.value || '', 10);
    return [outerId, innerId].filter(Number.isFinite);
}

function filterMergeBlades() {
    const searchTerm = document.getElementById('mergeBladesSearch').value;
    renderMergeBladesCheckboxes(searchTerm);
}

async function openMergeModal() {
    await loadBlades();
    document.getElementById('mergeAssemblyId').value = '';
    document.getElementById('mergeName').value = '';
    document.getElementById('deleteMergeBtn').style.display = 'none';
    renderMergeBladesSelects();
    openModal('mergeModal');
}

async function saveMerge() {
    const assemblyId = document.getElementById('mergeAssemblyId').value;
    const name = document.getElementById('mergeName').value.trim();
    const [outerBladeId, innerBladeId] = getSelectedMergeBladeIds();
    if (!name || !outerBladeId || !innerBladeId) {
        alert('Введите наименование и выберите две лопатки: внешнюю и внутреннюю полость');
        return;
    }
    if (outerBladeId === innerBladeId) {
        alert('Внешняя лопатка и внутренняя полость должны быть разными');
        return;
    }
    try {
        const url = assemblyId ? `/api/assemblies/${assemblyId}` : '/api/assemblies';
        const method = assemblyId ? 'PUT' : 'POST';
        const payload = assemblyId 
            ? { name, add_blade_ids: [outerBladeId, innerBladeId] } 
            : { name, blade_ids: [outerBladeId, innerBladeId] };
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Ошибка сохранения');
        }
        closeModal('mergeModal');
        await loadAssemblies();
        alert('Сборка сохранена!');
    } catch (e) {
        alert(`Ошибка: ${e.message}`);
    }
}

async function deleteMerge(assemblyId) {
    const id = assemblyId || document.getElementById('mergeAssemblyId').value;
    if (!id) return;
    try {
        const res = await fetch(`/api/assemblies/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Ошибка удаления');
        closeModal('mergeModal');
        await loadAssemblies();
        alert('Сборка удалена');
    } catch (e) {
        alert(`Ошибка: ${e.message}`);
    }
}

async function openViewAssemblyModal(assemblyId, assemblyName) {
    document.getElementById('viewAssemblyId').value = assemblyId;
    document.getElementById('viewAssemblyName').textContent = assemblyName;
    const tbody = document.getElementById('viewAssemblyBlades');
    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center">Загрузка...</td></tr>';
    openModal('assemblyViewModal');
    try {
        const res = await fetch(`/api/assemblies/${assemblyId}/members`);
        if (!res.ok) throw new Error('Ошибка загрузки');
        const members = await res.json();
        if (members.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#64748b">Лопатки не добавлены</td></tr>';
        } else {
            tbody.innerHTML = members.map(m => {
                const blade = bladesData.find(b => b.blade_id === m.blade_id);
                const bladeName = blade ? escapeHtml(blade.name) : (m.blade_name || `Лопатка #${m.blade_id}`);
                return `
                    <tr>
                        <td>${m.blade_id}</td>
                        <td>${bladeName}</td>
                        <td><button class="btn-approx" onclick="goToApproximation(${m.blade_id})">К аппроксимации</button></td>
                    </tr>
                `;
            }).join('');
        }
    } catch (e) {
        console.error(e);
        document.getElementById('viewAssemblyBlades').innerHTML = '<tr><td colspan="3" style="text-align:center;color:#ef4444">Ошибка загрузки</td></tr>';
    }
}

async function deleteAssembly() {
    const assemblyId = document.getElementById('viewAssemblyId').value;
    if (!confirm('Удалить это объединение?\nЛопатки останутся в базе.')) return;
    try {
        const res = await fetch(`/api/assemblies/${assemblyId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Ошибка удаления');
        closeModal('assemblyViewModal');
        await loadAssemblies();
        alert('✅ Объединение удалено');
    } catch (e) {
        alert('❌ Ошибка: ' + e.message);
    }
}

// ================= УТИЛИТЫ =================
function showLoading(show) {
    const el = document.getElementById('loadingStatus');
    if (el) el.style.display = show ? 'block' : 'none';
}

function showError(message) {
    alert(message);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function goToApproximation(bladeId) {
    window.location.href = `/approximation?blade_id=${bladeId}`;
}

// Добавляем глобальные функции для HTML
window.openCreateBladeModal = openCreateBladeModal;
window.openMergeModal = openMergeModal;
window.switchCoordTab = switchCoordTab;
window.loadCoordsFromFile = loadCoordsFromFile;
window.addCoordPointToTable = addCoordPointToTable;
window.saveBlade = saveBlade;
window.confirmDeleteBlade = confirmDeleteBlade;
window.deleteMerge = deleteMerge;
window.saveMerge = saveMerge;
window.viewBladeCoords = viewBladeCoords;
window.exportCoords = exportCoords;
window.openViewAssemblyModal = openViewAssemblyModal;
window.approximateAllInAssembly = approximateAllInAssembly;
window.deleteAssembly = deleteAssembly;
window.closeModal = closeModal;