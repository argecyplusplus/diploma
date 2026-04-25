import numpy as np
import os
import sys
import argparse

# --- Математическое ядро (единое для всех версий) ---

def gauss_extremum(l, A, B, sigma, C, L):
    x = l - L/2
    return A + B * np.exp(-x**2/(2*sigma**2)) + C * (x/(L/2))**2

def read_gauss_params(filename):
    data = np.genfromtxt(filename, delimiter=',', names=True)
    t_arr = data['t']
    params_metal = np.vstack([data['A_metal'], data['B_metal'], data['sigma_metal'], data['C_metal']]).T
    params_gas = np.vstack([data['A_gas'], data['B_gas'], data['sigma_gas'], data['C_gas']]).T
    return t_arr, params_metal, params_gas

def get_profile_from_params(l_grid, t_arr, params_arr, t_query, L):
    idx = np.argmin(np.abs(t_arr - t_query))
    p = params_arr[idx]
    return gauss_extremum(l_grid, *p, L)

def safe_array(x, min_size=1):
    arr = np.atleast_1d(x)
    if arr.size < min_size:
        arr = np.full(min_size, arr.item() if arr.size > 0 else 0.0)
    return arr

def check_and_fix_values(array):
    array = safe_array(array, 1)
    array = np.where(np.isnan(array), 300.0, array)
    array = np.where(np.isposinf(array), 2000.0, array)
    array = np.where(np.isneginf(array), 100.0, array)
    return array

def safe_power_four(T):
    T = safe_array(T, 1)
    T_safe = np.clip(T, 1.0, 2500.0)
    T4 = np.zeros_like(T_safe)
    mask_low = T_safe <= 2000.0
    T4[mask_low] = T_safe[mask_low]**4
    mask_high = T_safe > 2000.0
    if np.any(mask_high):
        log_T4 = 4 * np.log(T_safe[mask_high])
        log_T4_safe = np.clip(log_T4, 0, 50)
        T4[mask_high] = np.exp(log_T4_safe)
    return T4

def safe_radiation_heat_flux(T_hot, T_cold, epsilon, sigma_SB):
    T_hot = np.atleast_1d(T_hot)
    T_cold = np.atleast_1d(T_cold)
    if T_hot.size == 1 and T_cold.size > 1:
        T_hot = np.full_like(T_cold, T_hot.item())
    if T_cold.size == 1 and T_hot.size > 1:
        T_cold = np.full_like(T_hot, T_cold.item())
    T_diff = T_hot - T_cold
    T_avg = (T_hot + T_cold) / 2
    mask_small_diff = np.abs(T_diff) < 50.0
    q_rad = np.zeros_like(T_hot)
    if np.any(mask_small_diff):
        T_avg_subset = T_avg[mask_small_diff]
        T_avg_cubed = safe_power_four(T_avg_subset) / T_avg_subset
        q_rad[mask_small_diff] = epsilon * sigma_SB * 4 * T_avg_cubed * T_diff[mask_small_diff]
    mask_large_diff = ~mask_small_diff
    if np.any(mask_large_diff):
        T_hot_4 = safe_power_four(T_hot[mask_large_diff])
        T_cold_4 = safe_power_four(T_cold[mask_large_diff])
        q_rad[mask_large_diff] = epsilon * sigma_SB * (T_hot_4 - T_cold_4)
    q_rad = np.clip(q_rad, -1e8, 1e8)
    return q_rad

def solve_transient_curved_layer_with_gauss(l_grid, t_array, T_initial, Tmetal_func, Tout_func, params):
    xi, eta, h = params['xi'], params['eta'], params['h']
    rho, c_heat = params['rho'], params['c_heat']
    epsilon, sigma_SB = params['epsilon'], params['sigma_SB']
    h_conv, h_cool = params['h_conv'], params['h_cool']

    N_l, N_t = len(l_grid), len(t_array)
    L = l_grid[-1]
    dl = L / (N_l - 1)
    A, B = np.zeros((N_l, N_t)), np.zeros((N_l, N_t))
    A[:, 0] = T_initial

    for n in range(N_t - 1):
        t_curr = t_array[n]
        T_cov_int = A[:, n]
        T_cov_ext = A[:, n] + B[:, n] * h

        q_ext = h_conv * (Tout_func(t_curr) - T_cov_ext) + safe_radiation_heat_flux(Tout_func(t_curr), T_cov_ext, epsilon, sigma_SB)
        q_int = h_cool * (Tmetal_func(t_curr) - T_cov_int)
        
        lam_vec = np.clip(xi + eta * T_cov_ext, 0.5, 3.0)
        
        # Расчет вторых производных (центральные разности)
        d2A_dl2 = np.zeros(N_l)
        # Упрощенная схема теплопроводности вдоль профиля
        d2A_dl2[1:-1] = (A[2:, n] - 2*A[1:-1, n] + A[:-2, n]) / (dl**2)
        d2A_dl2[0] = d2A_dl2[-1] = (A[1, n] - 2*A[0, n] + A[-2, n]) / (dl**2)

        dt = t_array[n+1] - t_array[n]
        dA_dt = (lam_vec * d2A_dl2 + (q_ext - q_int)/h) / (rho * c_heat)
        
        A[:, n+1] = check_and_fix_values(A[:, n] + dA_dt * dt)
        B[:, n+1] = check_and_fix_values(-q_ext / lam_vec)
        
    return l_grid, t_array, A, B

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ver", required=True, help="Версия расчета (v001 или v1)")
    args = parser.parse_args()
    v = args.ver

    # Навигация по путям
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # если скрипт в /scripts/
    
    # Где искать gauss_params.csv? 
    # В папке scripts/v_001/ или scripts/v_1/
    v_folder = 'v_001' if v == 'v001' else 'v_1'
    params_file = os.path.join(script_dir, v_folder, 'gauss_params.csv')
    
    if not os.path.exists(params_file):
        print(f"ОШИБКА: Конфиг {params_file} не найден!")
        sys.exit(1)

    # Инициализация параметров
    L, N_l = 0.51, 80
    l_grid = np.linspace(0, L, N_l)
    t_arr, params_metal, params_gas = read_gauss_params(params_file)
    
    t_unique = np.unique(t_arr)
    dt = np.min(np.diff(t_unique))
    t_array = np.arange(np.min(t_unique), np.max(t_unique) + dt/2, dt)
    
    T_initial = np.full(N_l, 1223.15)
    phys_params = {
        'h_conv': 800.0, 'h_cool': 400.0, 'epsilon': 0.85,
        'sigma_SB': 5.67e-8, 'xi': 1.0, 'eta': 0.0005,
        'h': 0.0003, 'rho': 5600, 'c_heat': 450
    }

    def T_m(t): return get_profile_from_params(l_grid, t_arr, params_metal, t, L)
    def T_o(t): return get_profile_from_params(l_grid, t_arr, params_gas, t, L)

    # Расчет
    print(f"Запуск универсального расчета для версии: {v}")
    l, t, A, B = solve_transient_curved_layer_with_gauss(l_grid, t_array, T_initial, T_m, T_o, phys_params)

    # Сохранение в results/v...
    output_dir = os.path.join(project_root, 'results', v)
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, f'stable_results_from_gauss_{v}.npz')
    
    np.savez_compressed(save_path, l_grid=l, t_array=t, A=A, B=B, h=phys_params['h'])
    print(f"Успешно сохранено: {save_path}")