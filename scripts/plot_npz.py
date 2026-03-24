import numpy as np
import os
import sys
import matplotlib
matplotlib.use('Agg') # Для работы в фоновом режиме
import matplotlib.pyplot as plt
import argparse

def plot_from_npz(filename, output_dir, version_label):
    print(f"--- Отрисовка графиков для {version_label} ---")
    print(f"Файл данных: {os.path.abspath(filename)}")
    
    if not os.path.exists(filename):
        print(f"ERROR: Файл {filename} не найден.")
        return False

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

    T_surface = A + B * h
    mid_idx = len(l_grid) // 2
    os.makedirs(output_dir, exist_ok=True)

    # 1. Эволюция во времени
    plt.figure(figsize=(10, 6))
    plt.plot(t_array, A[mid_idx, :], label='Центр покрытия', linewidth=2)
    plt.plot(t_array, T_surface[mid_idx, :], '--', label='Внешняя поверхность', linewidth=2)
    plt.xlabel('Время, с')
    plt.ylabel('Температура, К')
    plt.title(f'Термический цикл ({version_label}) - середина профиля')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'plot_evolution_{version_label}.png'), dpi=150)
    plt.close()

    # 2. По профилю
    plt.figure(figsize=(10, 6))
    steps = [0, len(t_array)//4, len(t_array)//2, -1]
    for t_idx in steps:
        plt.plot(l_grid, A[:, t_idx], label=f't = {t_array[t_idx]:.2f} с')
    plt.xlabel('S, м')
    plt.ylabel('Температура, К')
    plt.title(f'Распределение температуры ({version_label})')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'plot_profile_{version_label}.png'), dpi=150)
    plt.close()

    # 3. Карта (Heatmap)
    plt.figure(figsize=(12, 5))
    img = plt.imshow(A, aspect='auto', extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]],
                     origin='lower', cmap='magma')
    plt.colorbar(img, label='Температура, К')
    plt.xlabel('Время, с')
    plt.ylabel('S, м')
    plt.title(f'Карта температур ({version_label})')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'plot_heatmap_{version_label}.png'), dpi=150)
    plt.close()
    
    print(f"SUCCESS: Графики {version_label} сохранены в {output_dir}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Универсальный отрисовщик NPZ")
    parser.add_argument("--ver", required=True, help="Версия (v001 или v1)")
    args = parser.parse_args()
    v = args.ver 
    
    # --- ИСПРАВЛЕННАЯ ЛОГИКА ПУТЕЙ ---
    # Получаем путь к папке, где лежит этот скрипт (т.е. .../scripts/)
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Корень проекта — это на один уровень выше папки scripts/
    project_root = os.path.dirname(current_script_dir)
    
    # Если скрипт вызван из подпапки (например scripts/v_1/), поднимаемся еще выше
    if os.path.basename(current_script_dir).startswith('v_'):
        project_root = os.path.dirname(project_root)

    target_dir = os.path.join(project_root, 'results', v)
    target_file = os.path.join(target_dir, f'stable_results_from_gauss_{v}.npz')

    # Запуск отрисовки
    plot_from_npz(target_file, target_dir, v)