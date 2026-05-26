import numpy as np
from numpy.linalg import inv


def Lezh(x):
    """Вычисляет полиномы Лежандра до 9-й степени. Возвращает матрицу (10, len(x))"""
    x = np.asarray(x)
    y = np.zeros((10, len(x)))
    y[0, :] = 1
    y[1, :] = x
    y[2, :] = (3 * x ** 2 - 1) / 2
    y[3, :] = (5 * x ** 3 - 3 * x) / 2
    y[4, :] = (35 * x ** 4 - 30 * x ** 2 + 3) / 8
    y[5, :] = (63 * x ** 5 - 70 * x ** 3 + 15 * x) / 8
    y[6, :] = 231 / 16 * x ** 6 - 315 / 16 * x ** 4 + 105 / 16 * x ** 2 - 5 / 16
    y[7, :] = 429 / 16 * x ** 7 - 693 / 16 * x ** 5 + 315 / 16 * x ** 3 - 35 / 16 * x
    y[8, :] = 6435 / 128 * x ** 8 - 3003 / 32 * x ** 6 + 3465 / 64 * x ** 4 - 315 / 32 * x ** 2 + 35 / 128
    y[9, :] = 12155 / 128 * x ** 9 - 6435 / 32 * x ** 7 + 9009 / 64 * x ** 5 - 1155 / 32 * x ** 3 + 315 / 128 * x
    return y


def calc_L(x, y_exp):
    """Расчет коэффициентов аппроксимации методом наименьших квадратов"""
    X = Lezh(x)
    if y_exp.ndim == 1:
        y_exp = y_exp.reshape(-1, 1)
    try:
        L = np.dot(inv(np.dot(X, X.T)), np.dot(X, y_exp))
    except np.linalg.LinAlgError:
        return None
    return L.flatten()


def R2(y_calc, y_exp):
    """Расчет коэффициента детерминации"""
    SS_reg = np.sum((y_exp - y_calc) ** 2)
    SS_tot = np.sum((y_exp - np.mean(y_exp)) ** 2)
    return 1 - SS_reg / SS_tot if SS_tot != 0 else 0.0


def transform_coordinates(x_upper, y_upper, x_lower, y_lower):
    """Трансформация координат: отражение Y, сдвиг, поворот, нормировка на хорду.

    Возвращает (x_u_norm, y_u_norm, x_l_norm, y_l_norm, transform_params), где
    transform_params — словарь со всеми параметрами трансформации, необходимыми
    для корректного обратного преобразования через inverse_transform().
    """
    max_y = np.max(np.concatenate((y_upper, y_lower)))
    y_upper_t = max_y - y_upper
    y_lower_t = max_y - y_lower

    delta_x = np.min([x_upper[0], x_lower[0]])
    x_upper_t = x_upper - delta_x
    x_lower_t = x_lower - delta_x

    dy = y_lower_t[-1] - np.min(y_lower_t)
    dx = x_lower_t[-1] - x_lower_t[np.argmin(y_lower_t)]
    phi = -np.arctan2(dy, dx) if (dx != 0 or dy != 0) else 0
    R = np.array([[np.cos(phi), -np.sin(phi)], [np.sin(phi), np.cos(phi)]])

    shift_x = x_lower_t[np.argmin(y_lower_t)]
    shift_y = np.min(y_lower_t)

    rotated_upper = R.dot(np.array([x_upper_t - shift_x, y_upper_t - shift_y]))
    rotated_lower = R.dot(np.array([x_lower_t - shift_x, y_lower_t - shift_y]))

    x_u_f = rotated_upper[0] + shift_x
    y_u_f = rotated_upper[1] + shift_y
    x_l_f = rotated_lower[0] + shift_x
    y_l_f = rotated_lower[1] + shift_y

    min_x = np.min([np.min(x_u_f), np.min(x_l_f)])
    min_x_correction = float(min_x) if min_x < 0 else 0.0
    if min_x < 0:
        x_u_f -= min_x
        x_l_f -= min_x

    chord = np.max([x_u_f[-1] - x_u_f[0], x_l_f[-1] - x_l_f[0]])
    if chord == 0:
        chord = 1.0

    transform_params = {
        'max_y': float(max_y),
        'delta_x': float(delta_x),
        'phi': float(phi),
        'R': R,
        'shift_x': float(shift_x),
        'shift_y': float(shift_y),
        'min_x_correction': min_x_correction,
        'chord': float(chord),
    }

    return x_u_f / chord, y_u_f / chord, x_l_f / chord, y_l_f / chord, transform_params


def inverse_transform(x_norm, y_norm, transform_params):
    """Обратное преобразование из нормированного пространства в исходные координаты.

    Применяет все шаги трансформации в обратном порядке:
    нормировка -> коррекция min_x -> обратный поворот -> отражение Y.

    Args:
        x_norm, y_norm: координаты в нормированном пространстве (np.array)
        transform_params: словарь, возвращённый transform_coordinates()

    Returns:
        x_orig, y_orig: координаты в исходном абсолютном пространстве
    """
    chord          = transform_params['chord']
    max_y          = transform_params['max_y']
    delta_x        = transform_params['delta_x']
    R              = transform_params['R']
    shift_x        = transform_params['shift_x']
    shift_y        = transform_params['shift_y']
    min_x_corr     = transform_params['min_x_correction']

    # 1. Отменяем нормировку на chord
    x_f = x_norm * chord
    y_f = y_norm * chord

    # 2. Отменяем коррекцию отрицательного min_x
    x_f = x_f + min_x_corr

    # 3. Отменяем сдвиг shift, обратный поворот (R^-1 = R^T), возвращаем shift
    x_r = x_f - shift_x
    y_r = y_f - shift_y
    unrotated = R.T.dot(np.array([x_r, y_r]))
    x_t = unrotated[0] + shift_x
    y_t = unrotated[1] + shift_y

    # 4. Отменяем сдвиг delta_x
    x_orig = x_t + delta_x

    # 5. Отменяем отражение Y: y_t = max_y - y_orig  =>  y_orig = max_y - y_t
    y_orig = max_y - y_t

    return x_orig, y_orig