// static/js/results.js
const simId = parseInt(document.body.dataset.simId || window.location.pathname.split('/').slice(-2)[0]);

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
        if (data.temperature) {
            html += `<div><h4>Распределение температуры</h4><img src="data:image/png;base64,${data.temperature}" style="max-width:100%; margin-bottom:20px;"></div>`;
        }
        if (data.mises_strain) {
            html += `<div><h4>Эквивалентная деформация Мизеса</h4><img src="data:image/png;base64,${data.mises_strain}" style="max-width:100%; margin-bottom:20px;"></div>`;
        }
        if (data.mises_stress) {
            html += `<div><h4>Эквивалентное напряжение Мизеса</h4><img src="data:image/png;base64,${data.mises_stress}" style="max-width:100%; margin-bottom:20px;"></div>`;
        }
        if (data.profile) {
            html += `<div><h4>Профиль лопатки</h4><img src="data:image/png;base64,${data.profile}" style="max-width:100%; margin-bottom:20px;"></div>`;
        }
        if (html === '') html = '<div class="status-message">Нет данных для отображения (возможно, расчёт не завершён или это не задача 3).</div>';
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadPlots();
});