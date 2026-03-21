import numpy as np
import os
import sys
import matplotlib
matplotlib.use('Agg') # СТРОГО ЗДЕСЬ
import matplotlib.pyplot as plt


def plot_from_npz(filename, output_dir='.'):

    # Добавьте этот принт, чтобы убедиться, что скрипт вообще начал работу
    print(f"Starting plot_from_npz with {filename} in {os.getcwd()}")

    # Если файла нет, выходим с ошибкой, чтобы Flask это зафиксировал
    if not os.path.exists(filename):
        print(f"ERROR: Файл данных {filename} не найден в {os.getcwd()}")
        return False

    # Загрузка данных
    try:
        data = np.load(filename)
        l_grid = data['l_grid']
        t_array = data['t_array']
        A = data['A']
        B = data['B']
        h = data['h'] if 'h' in data else 0.0003
    except Exception as e:
        print(f"ERROR при чтении NPZ: {e}")
        return False

    # Температура на внешней поверхности
    T_surface = A + B * h

    # Индекс середины профиля для графиков эволюции
    mid_idx = len(l_grid) // 2

    # --- График 1: Эволюция во времени ---
    plt.figure(figsize=(10, 6))
    plt.plot(t_array, A[mid_idx, :], label='Центр покрытия', linewidth=2)
    plt.plot(t_array, T_surface[mid_idx, :], '--', label='Внешняя поверхность', linewidth=2)
    plt.xlabel('Время, с')
    plt.ylabel('Температура, К')
    plt.title(f'Термический цикл (середина профиля L={l_grid[mid_idx]:.3f}м)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_evolution_v001.png'), dpi=150)
    plt.close()

    # --- График 2: Профиль в разные моменты времени ---
    plt.figure(figsize=(10, 6))
    # Выбираем 4 равномерных момента времени
    steps = [0, len(t_array)//4, len(t_array)//2, -1]
    for t_idx in steps:
        plt.plot(l_grid, A[:, t_idx], label=f't = {t_array[t_idx]:.2f} с')
    
    plt.xlabel('Координата вдоль профиля (S), м')
    plt.ylabel('Температура, К')
    plt.title('Распределение температуры вдоль поверхности лопатки')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_profile_v001.png'), dpi=150)
    plt.close()

    # --- График 3: Карта (Heatmap) ---
    plt.figure(figsize=(12, 5))
    img = plt.imshow(
        A,
        aspect='auto',
        extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]],
        origin='lower',
        cmap='magma' # Более наглядная шкала для температур
    )
    plt.colorbar(img, label='Температура, К')
    plt.xlabel('Время, с')
    plt.ylabel('Координата по профилю, м')
    plt.title('Поле температур в слое покрытия (Time-Space map)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_heatmap_v001.png'), dpi=150)
    plt.close()
    
    print("SUCCESS: Графики успешно созданы.")
    return True

if __name__ == "__main__":
    # Основное имя файла, которое генерирует ваш расчетный скрипт
    target_file = 'stable_results_from_gauss_v001.npz'
    
    # Проверка: если файла нет в текущей директории (generated)
    if not os.path.exists(target_file):
        print(f"ERROR: Не нашел файл {target_file}")
        print(f"Содержимое папки {os.getcwd()}: {os.listdir('.')}")
    else:
        plot_from_npz(target_file)