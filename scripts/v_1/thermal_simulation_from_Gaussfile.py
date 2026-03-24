import numpy as np
import matplotlib.pyplot as plt

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
    xi = params.get('xi', 1.0)
    eta = params.get('eta', 0.0005)
    h = params.get('h', 0.0003)
    rho = params.get('rho', 5600)
    c_heat = params.get('c_heat', 450)
    epsilon = params['epsilon']
    sigma_SB = params['sigma_SB']
    h_conv = params['h_conv']
    h_cool = params['h_cool']

    N_l = len(l_grid)
    N_t = len(t_array)
    L = l_grid[-1]
    dl = L / (N_l - 1)
    A = np.zeros((N_l, N_t))
    B = np.zeros((N_l, N_t))
    A[:, 0] = T_initial
    B[:, 0] = 0

    for n in range(N_t - 1):
        t_curr = t_array[n]
        Tmetal = Tmetal_func(t_curr)
        Tout = Tout_func(t_curr)
        A_curr = A[:, n]
        B_curr = B[:, n]
        T_cov_int = A_curr
        T_cov_ext = A_curr + B_curr * h

        q_ext = h_conv * (Tout - T_cov_ext) + safe_radiation_heat_flux(Tout, T_cov_ext, epsilon, sigma_SB)
        q_int = h_cool * (Tmetal - T_cov_int)
        q_ext = np.clip(q_ext, -1e7, 1e7)
        q_int = np.clip(q_int, -1e7, 1e7)

        lam_vec = xi + eta * T_cov_ext
        lam_vec = np.clip(lam_vec, 0.5, 3.0)

        lam_left = np.zeros(N_l)
        lam_right = np.zeros(N_l)
        lam_left[1:] = 2 * lam_vec[1:] * lam_vec[:-1] / (lam_vec[1:] + lam_vec[:-1])
        lam_left[0] = lam_vec[0]
        lam_right[:-1] = 2 * lam_vec[:-1] * lam_vec[1:] / (lam_vec[:-1] + lam_vec[1:])
        lam_right[-1] = lam_vec[-1]
        d2A_dl2 = np.zeros(N_l)
        for i in range(1, N_l-1):
            d2A_dl2[i] = (lam_right[i]*(A[i+1,n]-A[i,n]) - lam_left[i]*(A[i,n]-A[i-1,n])) / (dl**2)
        d2A_dl2[0] = (lam_right[0]*(A[1,n]-A[0,n]) - lam_left[0]*(A[0,n]-A[-1,n])) / (dl**2)
        d2A_dl2[-1] = (lam_right[-1]*(A[0,n]-A[-1,n]) - lam_left[-1]*(A[-1,n]-A[-2,n])) / (dl**2)

        max_flux = max(np.abs(q_ext).max(), np.abs(q_int).max(), 1e3)
        dt = t_array[n+1] - t_array[n]
        dt_eff = min(dt, 0.1 * 1e6 / max_flux)
        dA_dt = (d2A_dl2 + (q_ext - q_int)/lam_vec) / (rho * c_heat * h)
        dA_dt = np.clip(dA_dt, -1000.0, 1000.0)
        A[:, n+1] = A[:, n] + dA_dt * dt_eff
        A[:, n+1] = np.clip(A[:, n+1], 100.0, 2500.0)
        B_new = -q_ext / lam_vec
        B_new = np.clip(B_new, -1e4, 1e4)
        B[:, n+1] = B_new
        A[0, n+1] = A[-1, n+1]
        B[0, n+1] = B[-1, n+1]
        A[:, n+1] = check_and_fix_values(A[:, n+1])
        B[:, n+1] = check_and_fix_values(B[:, n+1])
        if n % max(1, N_t//20) == 0:
            T_avg = np.mean(A[:, n])
            T_max = np.max(A[:, n] + B[:, n] * h)
            print(f"t = {t_curr:.2f} с, T_avg = {T_avg:.1f} K, T_max = {T_max:.1f} K")
    return l_grid, t_array, A, B

if __name__ == "__main__":
    # --- Параметры профиля и расчёта ---
    L = 0.51  # длина дуги профиля, м
    N_l = 80  # число точек по профилю (можно изменить)
    l_grid = np.linspace(0, L, N_l)

    # --- Загрузка параметров гауссовской аппроксимации ---
    params_file = 'gauss_params.csv'
    t_arr, params_metal, params_gas = read_gauss_params(params_file)
    t_unique = np.unique(t_arr)
    dt = np.min(np.diff(t_unique))
    t_final = np.max(t_unique)
    t_array = np.arange(np.min(t_unique), t_final + dt/2, dt)

    # --- Начальная температура покрытия ---
    T_initial = np.full(N_l, 1223.15)  # 950°C в К

    params = {
        'h_conv': 800.0,
        'h_cool': 400.0,
        'epsilon': 0.85,
        'sigma_SB': 5.67e-8,
        'xi': 1.0,
        'eta': 0.0005,
        'h': 0.0003,
        'rho': 5600,
        'c_heat': 450
    }

    def Tmetal_func(t_query):
        return get_profile_from_params(l_grid, t_arr, params_metal, t_query, L)

    def Tout_func(t_query):
        return get_profile_from_params(l_grid, t_arr, params_gas, t_query, L)

    l_grid, t_array, A, B = solve_transient_curved_layer_with_gauss(
        l_grid, t_array, T_initial, Tmetal_func, Tout_func, params
    )

    print("Расчёт завершён успешно")
    print(f"Температурный диапазон: {A.min():.1f} - {(A+B*params['h']).max():.1f} K")
    np.savez_compressed('stable_results_from_gauss.npz', l_grid=l_grid, t_array=t_array, A=A, B=B)

    # --- Визуализация ---
    # Теперь для всех графиков используем температуру в центре покрытия: A
    plt.figure(figsize=(10, 6))
    plt.plot(t_array, A[len(l_grid)//2, :], label='Центр покрытия')
    plt.xlabel('Время, с')
    plt.ylabel('Температура, К')
    plt.title('Температура в центре покрытия (середина профиля)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    # График 2: температурное поле вдоль профиля в разные моменты времени (в центре покрытия)
    plt.figure(figsize=(10, 6))
    for t_idx in [0, len(t_array)//4, len(t_array)//2, -1]:
        plt.plot(l_grid, A[:, t_idx], label=f't = {t_array[t_idx]:.2f} с')
    plt.xlabel('Координата вдоль профиля, м')
    plt.ylabel('Температура в центре покрытия, К')
    plt.title('Распределение температуры по профилю (центр покрытия)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    # График 3: карта температурного поля (центр покрытия)
    plt.figure(figsize=(10, 6))
    plt.imshow(
        A,
        aspect='auto',
        extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]],
        origin='lower',
        cmap='hot'
    )
    plt.colorbar(label='Температура, К')
    plt.xlabel('Время, с')
    plt.ylabel('Координата вдоль профиля, м')
    plt.title('Карта температурного поля (центр покрытия)')
    plt.tight_layout()
    plt.show()
