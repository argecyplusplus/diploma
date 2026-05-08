// static/js/main.js
let currentDb = null;

async function loadConfig() {
    try {
        const [settingsRes, dbsRes] = await Promise.all([
            fetch('/api/settings'),
            fetch('/api/settings/dbs')
        ]);
        const settingsData = await settingsRes.json();
        const dbData = await dbsRes.json();

        const freefemPath = settingsData.freefem_path || '';
        const freefemInput = document.getElementById('freefemPath');
        if (freefemInput) freefemInput.value = freefemPath;

        const dbs = dbData.databases || [];
        currentDb = dbData.current_db || null;
        renderDbList(dbs);
        updateDbStatus();
        if (!currentDb) {
            openModal('settingsModal');
        }
    } catch (e) {
        console.error('Ошибка загрузки:', e);
        const dbList = document.getElementById('dbList');
        if (dbList) dbList.innerHTML = `<div class="db-item" style="color:red;">Ошибка загрузки</div>`;
    }
}

function updateDbStatus() {
    const statusSpan = document.getElementById('db-status-text');
    if (statusSpan) {
        if (currentDb) {
            statusSpan.innerHTML = `✅ Активна: ${currentDb}`;
        } else {
            statusSpan.innerHTML = `❌ БД не выбрана`;
        }
    }
}

function renderDbList(dbs) {
    const container = document.getElementById('dbList');
    if (!container) return;
    if (!dbs.length) {
        container.innerHTML = '<div class="db-item">Нет доступных баз данных</div>';
        return;
    }
    const unique = [...new Set(dbs)];
    container.innerHTML = unique.map(db => `
        <div class="db-item ${db === currentDb ? 'active' : ''}" onclick="selectDb('${db}')">
            <span>📄 ${db}</span>
            <button class="btn-danger-sm" onclick="event.stopPropagation(); deleteDb('${db}')">✕</button>
        </div>
    `).join('');
}

async function createDb() {
    const nameInput = document.getElementById('newDbName');
    if (!nameInput) return;
    const name = nameInput.value.trim();
    if (!name) return alert('Введите имя базы данных');
    const res = await fetch('/api/settings/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name})
    });
    if (res.ok) {
        nameInput.value = '';
        await loadConfig();
    } else {
        const err = await res.json();
        alert('Ошибка: ' + (err.error || 'Неизвестная'));
    }
}

async function selectDb(name) {
    const res = await fetch('/api/settings/select', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name})
    });
    if (res.ok) {
        await loadConfig();
        location.reload();
    } else {
        alert('Ошибка выбора БД');
    }
}

async function deleteDb(name) {
    if (!confirm(`Удалить базу данных "${name}"? Все данные будут потеряны.`)) return;
    const res = await fetch(`/api/settings/delete/${name}`, { method: 'DELETE' });
    if (res.ok) {
        await loadConfig();
    } else {
        alert('Ошибка удаления');
    }
}

async function saveSettings() {
    const freefemPath = document.getElementById('freefemPath')?.value.trim() || '';
    const res = await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ freefem_path: freefemPath })
    });
    if (res.ok) {
        alert('Настройки сохранены');
        closeModal('settingsModal');
    } else {
        const err = await res.json();
        alert('Ошибка: ' + (err.error || 'Неизвестная'));
    }
}

function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
    if (id === 'settingsModal' && !currentDb) {
        setTimeout(() => {
            if (!currentDb) openModal('settingsModal');
        }, 100);
    }
}

// Закрытие по клику на оверлей
document.addEventListener('click', (e) => {
    document.querySelectorAll('.modal-overlay.active').forEach(overlay => {
        if (e.target === overlay) closeModal(overlay.id);
    });
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(overlay => closeModal(overlay.id));
    }
});
document.querySelectorAll('.modal').forEach(modal => modal.addEventListener('click', e => e.stopPropagation()));

// Подсветка активного пункта меню
function highlightActiveNav() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    highlightActiveNav();
});