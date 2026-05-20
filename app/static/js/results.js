const simId = parseInt(window.location.pathname.split('/').slice(-2)[0]);

async function loadPlots() {
    const container = document.getElementById('plotsContent');
    if (!container) return;
    container.innerHTML = '<div class="status-message">⏳ Загрузка графиков...</div>';
    try {
        const res = await fetch(`/simulation/${simId}/plots`);
        if (!res.ok) throw new Error('Ошибка загрузки');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        let html = '';
        // Словарь для понятных названий графиков
        const plotNames = {
            'plot_1': 'Сетка',
            'plot_2': 'Функция тока / Температура',
            'plot_3': 'Скорость / Напряжение σ₁',
            'plot_4': 'Давление / Напряжение σ₂',
            'plot_5': 'Давление (изолинии) / Напряжение σ₁₂',
            'profile': 'Профиль лопатки',
            'temperature': 'Распределение температуры',
            'mises_strain': 'Деформация Мизеса',
            'mises_stress': 'Напряжение Мизеса',
            'sig1': 'Напряжение σ₁',
            'sig2': 'Напряжение σ₂',
            'sig12': 'Напряжение σ₁₂',
            'ThermalDistrib': 'Температурное поле'
        };
        for (const [name, imgBase64] of Object.entries(data)) {
            if (name === 'error') continue;
            let displayName = plotNames[name] || name;
            html += `<div><h4>${displayName}</h4><img src="data:image/png;base64,${imgBase64}" style="max-width:100%; margin-bottom:20px;"></div>`;
        }
        if (html === '') html = '<div class="status-message">Нет данных для отображения</div>';
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
    }
}

async function loadFiles() {
    const container = document.getElementById('filesContent');
    if (!container) return;
    container.innerHTML = '<div class="status-message">Загрузка...</div>';
    try {
        const res = await fetch(`/simulation/${simId}/files`);
        if (!res.ok) throw new Error('Ошибка загрузки списка файлов');
        const files = await res.json();
        if (files.length === 0) {
            container.innerHTML = '<div class="status-message">Нет доступных файлов</div>';
            return;
        }
        let html = '';
        files.forEach(file => {
            let btnClass = 'btn-secondary';
            if (file.name === 'result.vtk') btnClass = 'btn-primary';
            html += `<a href="/simulation/${simId}/result/${file.name.split('.')[0].toLowerCase()}" class="${btnClass}">📥 ${file.description}</a>`;
        });
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadPlots();
    loadFiles();
});