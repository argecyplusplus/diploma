// static/js/freefem_plots.js
let currentPlots = [];
let currentPlotIndex = 0;
let conversionInterval = null;

async function loadFreeFemPlots() {
    const simId = parseInt(window.location.pathname.split('/').slice(-2)[0]);
    const container = document.getElementById('freefemPlotsContent');

    if (!container) return;

    // Показываем начальный статус
    container.innerHTML = `
        <div class="status-message">
            <div class="conversion-status">
                <div class="conversion-spinner"></div>
                <div class="conversion-text">⏳ Поиск графиков FreeFEM...</div>
            </div>
        </div>
    `;

    try {
        const res = await fetch(`/simulation/${simId}/freefem_plots`);
        const data = await res.json();

        if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');

        if (!data.success || data.plots.length === 0) {
            container.innerHTML = `<div class="status-message">${data.message || 'Графики FreeFEM не найдены'}</div>`;
            return;
        }

        // Если есть прогресс и не всё сконвертировано - показываем прогресс
        if (data.progress && data.progress.total > 0 && data.progress.converted < data.progress.total) {
            showConversionProgress(data.progress);
            // Проверяем статус конвертации каждые 2 секунды
            if (conversionInterval) clearInterval(conversionInterval);
            conversionInterval = setInterval(() => checkConversionStatus(simId), 2000);
            return;
        }

        // Всё готово - показываем галерею
        currentPlots = data.plots;
        currentPlotIndex = 0;

        // Предзагрузка изображений
        container.innerHTML = '<div class="status-message">🖼️ Загрузка изображений...</div>';
        await preloadAllImages(currentPlots);
        renderPlotGallery();

        if (conversionInterval) clearInterval(conversionInterval);

    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">❌ Ошибка: ${e.message}</div>`;
    }
}

async function checkConversionStatus(simId) {
    try {
        const res = await fetch(`/simulation/${simId}/freefem_plots`);
        const data = await res.json();

        if (!res.ok) return;

        if (data.progress && data.progress.converted >= data.progress.total) {
            // Конвертация завершена
            if (conversionInterval) clearInterval(conversionInterval);

            // Перезагружаем графики
            const finalRes = await fetch(`/simulation/${simId}/freefem_plots`);
            const finalData = await finalRes.json();

            if (finalData.success && finalData.plots.length > 0) {
                currentPlots = finalData.plots;
                currentPlotIndex = 0;
                await preloadAllImages(currentPlots);
                renderPlotGallery();
            } else {
                document.getElementById('freefemPlotsContent').innerHTML =
                    `<div class="status-message">${finalData.message || 'Графики не найдены'}</div>`;
            }
        } else if (data.progress) {
            // Обновляем прогресс
            showConversionProgress(data.progress);
        }
    } catch(e) {
        console.error('Error checking conversion status:', e);
    }
}

function showConversionProgress(progress) {
    const container = document.getElementById('freefemPlotsContent');
    if (!container) return;

    const percent = progress.percent || 0;
    const converted = progress.converted || 0;
    const total = progress.total || 0;

    container.innerHTML = `
        <div class="status-message">
            <div class="conversion-status">
                <div class="conversion-spinner"></div>
                <div class="conversion-text">🖼️ Конвертация графиков FreeFEM...</div>
                <div class="conversion-progress-bar">
                    <div class="conversion-progress-fill" style="width: ${percent}%"></div>
                </div>
                <div class="conversion-count">${converted} из ${total} графиков готово</div>
            </div>
        </div>
    `;
}

async function preloadAllImages(plots) {
    const promises = plots.map((plot) => {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => resolve(true);
            img.onerror = () => resolve(false);
            img.src = plot.url;
        });
    });
    await Promise.all(promises);
}

function renderPlotGallery() {
    const container = document.getElementById('freefemPlotsContent');
    if (!container) return;

    if (currentPlots.length === 0) {
        container.innerHTML = '<div class="status-message">Нет графиков для отображения</div>';
        return;
    }

    const current = currentPlots[currentPlotIndex];

    let html = `
        <div class="plot-gallery">
            <div class="plot-counter">${currentPlotIndex + 1} из ${currentPlots.length}</div>
            <div class="plot-title">${escapeHtml(current.name)}</div>
            <div class="plot-image-container">
                <img src="${current.url}" alt="${escapeHtml(current.name)}" class="plot-image">
            </div>
            <div class="plot-nav">
                <button class="btn-secondary" onclick="prevPlot()" ${currentPlotIndex === 0 ? 'disabled' : ''}>◀ Предыдущий</button>
                <button class="btn-secondary" onclick="nextPlot()" ${currentPlotIndex === currentPlots.length - 1 ? 'disabled' : ''}>Следующий ▶</button>
            </div>
            <div class="plot-thumbnails">
                ${currentPlots.map((plot, idx) => `
                    <div class="plot-thumbnail ${idx === currentPlotIndex ? 'active' : ''}" onclick="goToPlot(${idx})">
                        <img src="${plot.url}" alt="${escapeHtml(plot.name)}">
                        <span>${escapeHtml(plot.name.substring(0, 20))}${plot.name.length > 20 ? '...' : ''}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function nextPlot() {
    if (currentPlotIndex < currentPlots.length - 1) {
        currentPlotIndex++;
        renderPlotGallery();
    }
}

function prevPlot() {
    if (currentPlotIndex > 0) {
        currentPlotIndex--;
        renderPlotGallery();
    }
}

function goToPlot(index) {
    if (index >= 0 && index < currentPlots.length) {
        currentPlotIndex = index;
        renderPlotGallery();
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}