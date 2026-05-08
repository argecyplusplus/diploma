/**
 * FF Pro — Base JavaScript
 * Управление настройками: БД, путь к FreeFEM++, модальные окна
 */

let currentDb = null;
let allDbs = []; // Кэш списка БД для поиска

// ================= ЗАГРУЗКА КОНФИГУРАЦИИ =================
async function loadConfig() {
    try {
        // 1. Настройки FreeFEM
        const settingsRes = await fetch('/api/settings');
        const settingsData = await settingsRes.json();
        if (settingsData.freefem_path) {
            const fpInput = document.getElementById('freefemPath');
            if (fpInput) fpInput.value = settingsData.freefem_path;
        }

        // 2. Список БД
        const dbRes = await fetch('/api/settings/dbs');
        const dbData = await dbRes.json();

        const dbs = dbData.databases || [];
        const current = dbData.current_db || null;

        currentDb = current;
        allDbs = dbs; // Сохраняем для поиска
        renderDbList(dbs);

        // Обновляем статус в хедере
        const statusEl = document.getElementById('dbStatusText');
        if (statusEl) {
            statusEl.textContent = current ? `Текущая БД: 🗄️ ${current}` : 'БД не выбрана';
            statusEl.className = current ? 'db-status connected' : 'db-status';
        }

        // Автооткрытие, если БД не выбрана
        if (!current) openModal('settingsModal');
    } catch (e) {
        console.error('Ошибка загрузки:', e);
        const dbList = document.getElementById('dbList');
        if (dbList) {
            dbList.innerHTML = `<div class="db-error">❌ Ошибка: ${e.message}</div>`;
        }
    }
}

// ================= ОТРИСОВКА СПИСКА БД (УЛУЧШЕННАЯ) =================
function renderDbList(dbs, filter = '') {
    const list = document.getElementById('dbList');
    if (!list) return;

    // Фильтрация
    const filtered = dbs.filter(db => db.toLowerCase().includes(filter.toLowerCase()));

    if (filtered.length === 0) {
        list.innerHTML = dbs.length === 0
            ? `<div class="db-empty">📭 Нет баз данных<br><small>Создайте первую базу выше</small></div>`
            : `<div class="db-empty">🔍 Ничего не найдено по запросу "${filter}"</div>`;
        return;
    }

    // Сортировка: активная БД всегда первая
    const sorted = [...filtered].sort((a, b) => {
        if (a === currentDb) return -1;
        if (b === currentDb) return 1;
        return a.localeCompare(b);
    });

    list.innerHTML = sorted.map(db => {
        const isActive = db === currentDb;
        const dbIcon = isActive ? '🗄️' : '📁';
        const dbStatus = isActive ? '<span class="db-badge-active">● Активна</span>' : '';

        return `
        <div class="db-card ${isActive ? 'active' : ''}" onclick="selectDb('${db}')">
            <div class="db-card-main">
                <span class="db-icon">${dbIcon}</span>
                <div class="db-info">
                    <strong class="db-name">${db}</strong>
                    <span class="db-meta">${isActive ? 'Текущая сессия' : 'Доступна'}</span>
                </div>
            </div>
            <div class="db-card-actions">
                ${dbStatus}
                <button class="db-btn-delete" onclick="event.stopPropagation(); deleteDb('${db}')" title="Удалить">✕</button>
            </div>
        </div>`;
    }).join('');
}

// ================= ПОИСК ПО БД =================
function initDbSearch() {
    const searchInput = document.getElementById('dbSearch');
    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        renderDbList(allDbs, e.target.value);
    });
}

// ================= CRUD БД =================
async function createDb() {
    const input = document.getElementById('newDbName');
    const name = input?.value.trim();
    if (!name) return alert('Введите имя базы данных');

    // Валидация имени
    if (!/^[a-zA-Z0-9_]+$/.test(name)) {
        return alert('Имя может содержать только латинские буквы, цифры и подчёркивание');
    }

    try {
        const res = await fetch('/api/settings/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });
        const data = await res.json();

        if (res.ok) {
            input.value = '';
            document.getElementById('dbSearch').value = '';
            loadConfig();
        } else {
            alert('Ошибка: ' + (data.error || 'Неизвестная'));
        }
    } catch (e) {
        alert('Ошибка сети: ' + e.message);
    }
}

async function selectDb(name) {
    if (name === currentDb) return; // Уже выбрана

    try {
        const res = await fetch('/api/settings/select', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });
        if (res.ok) {
            loadConfig();
            // Визуальный фидбек
            const cards = document.querySelectorAll('.db-card');
            cards.forEach(c => c.classList.remove('pulse'));
            setTimeout(() => {
                const activeCard = document.querySelector(`.db-card.active`);
                if (activeCard) activeCard.classList.add('pulse');
            }, 100);
        } else {
            alert('Ошибка выбора БД');
        }
    } catch (e) {
        alert('Ошибка сети: ' + e.message);
    }
}

async function deleteDb(name) {
    if (name === currentDb) {
        return alert('⚠️ Нельзя удалить активную базу данных.\nСначала выберите другую БД.');
    }
    if (!confirm(`Удалить базу "${name}"?\nЭто действие необратимо.`)) return;

    try {
        const res = await fetch(`/api/settings/delete/${name}`, { method: 'DELETE' });
        if (res.ok) {
            loadConfig();
        } else {
            alert('Ошибка удаления');
        }
    } catch (e) {
        alert('Ошибка сети: ' + e.message);
    }
}

// ================= СОХРАНЕНИЕ НАСТРОЕК =================
async function saveSettings() {
    const freefemPath = document.getElementById('freefemPath')?.value.trim() || '';
    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ freefem_path: freefemPath })
        });
        if (res.ok) {
            alert('✅ Настройки сохранены!');
            closeModal('settingsModal');
        } else {
            const err = await res.json();
            alert('❌ Ошибка: ' + (err.error || 'Неизвестная'));
        }
    } catch(e) {
        alert('❌ Ошибка сети: ' + e.message);
    }
}

// ================= МОДАЛЬНЫЕ ОКНА =================
function openModal(modalId = 'settingsModal') {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.add('active');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Фокус на поиск при открытии
    setTimeout(() => {
        document.getElementById('dbSearch')?.focus();
    }, 100);
}

function closeModal(modalId = 'settingsModal') {
    if (modalId === 'settingsModal' && !currentDb) {
        return alert('⚠️ Необходимо выбрать или создать базу данных!');
    }
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('active');
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

// ================= ОБРАБОТЧИКИ СОБЫТИЙ =================
function initModalHandlers() {
    // Поиск по БД
    initDbSearch();

    // Закрытие по клику на оверлей
    document.addEventListener('click', function(e) {
        document.querySelectorAll('.modal-overlay.active').forEach(overlay => {
            const modalContent = overlay.querySelector('.modal');
            if (e.target === overlay && !modalContent?.contains(e.target)) {
                closeModal(overlay.id);
            }
        });
    });

    // Закрытие по Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(overlay => {
                closeModal(overlay.id);
            });
        }
    });

    // Предотвращаем закрытие при клике внутри модалки
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) { e.stopPropagation(); });
    });
}

// ================= ЭКСПОРТ ДЛЯ ONCLICK =================
window.openModal = openModal;
window.closeModal = closeModal;
window.createDb = createDb;
window.selectDb = selectDb;
window.deleteDb = deleteDb;
window.saveSettings = saveSettings;
window.loadConfig = loadConfig;

// ================= ИНИЦИАЛИЗАЦИЯ =================
document.addEventListener('DOMContentLoaded', function() {
    initModalHandlers();
    loadConfig();
});