# app/services/approximation_service.py
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from ..models.blade import Blade, ProfileCoordinate, Approximation, ApproximationParameter, LegendreCoefficient, TransformedCoordinate, BladeAssembly
from ..utils.approximation_math import Lezh, calc_L, R2, transform_coordinates
import numpy as np

class ApproximationService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------
    # Аппроксимация одной лопатки (сохраняется в БД)
    # ------------------------------------------------------------
    def execute_approximation(self, blade_id: int) -> Dict[str, Any]:
        stmt = select(ProfileCoordinate).where(ProfileCoordinate.blade_id == blade_id)
        coords = self.session.scalars(stmt).all()
        if not coords:
            raise ValueError("Нет координат профиля для данной лопатки")

        upper = [(c.x, c.y) for c in coords if c.profile_type == 'upper']
        lower = [(c.x, c.y) for c in coords if c.profile_type == 'lower']
        if not upper or not lower:
            raise ValueError("Отсутствуют координаты для верхнего или нижнего профиля")

        x_u, y_u = np.array([p[0] for p in upper]), np.array([p[1] for p in upper])
        x_l, y_l = np.array([p[0] for p in lower]), np.array([p[1] for p in lower])

        x_u_t, y_u_t, x_l_t, y_l_t = transform_coordinates(x_u, y_u, x_l, y_l)

        approx_stmt = select(Approximation).where(Approximation.blade_id == blade_id)
        old_approx = self.session.scalars(approx_stmt).first()
        if old_approx:
            self.session.execute(delete(Approximation).where(Approximation.blade_id == blade_id))
            self.session.flush()

        approx = Approximation(blade_id=blade_id, type='legendre_9')
        self.session.add(approx)
        self.session.flush()
        aid = approx.approximation_id

        for x, y in zip(x_u_t, y_u_t):
            self.session.add(TransformedCoordinate(approximation_id=aid, profile_type='upper', x_transformed=float(x), y_transformed=float(y)))
        for x, y in zip(x_l_t, y_l_t):
            self.session.add(TransformedCoordinate(approximation_id=aid, profile_type='lower', x_transformed=float(x), y_transformed=float(y)))

        L_u = calc_L(x_u_t, y_u_t)
        L_l = calc_L(x_l_t, y_l_t)
        if L_u is None or L_l is None:
            raise ValueError("Ошибка вычисления коэффициентов (матрица вырождена)")

        for i in range(len(L_u)):
            self.session.add(LegendreCoefficient(approximation_id=aid, upper_value=float(L_u[i]), lower_value=float(L_l[i])))

        y_u_calc = np.dot(L_u, Lezh(x_u_t))
        self.session.add(ApproximationParameter(approximation_id=aid, profile_type='upper',
            max_profile_value=float(np.max(y_u_calc)), x_coordinate_max=float(x_u_t[np.argmax(y_u_calc)]), r_squared=float(R2(y_u_calc, y_u_t))))

        y_l_calc = np.dot(L_l, Lezh(x_l_t))
        self.session.add(ApproximationParameter(approximation_id=aid, profile_type='lower',
            max_profile_value=float(np.max(y_l_calc)), x_coordinate_max=float(x_l_t[np.argmax(y_l_calc)]), r_squared=float(R2(y_l_calc, y_l_t))))

        self.session.flush()
        return {"approximation_id": aid, "message": "Аппроксимация выполнена успешно"}

    # ------------------------------------------------------------
    # Аппроксимация объединения (ровно две лопатки)
    # ------------------------------------------------------------
    def execute_assembly_approximation(self, assembly_id: int) -> Dict[str, Any]:
        """Аппроксимация сборки из двух лопаток: внешняя и внутренняя."""
        assembly = self.session.get(BladeAssembly, assembly_id)
        if not assembly:
            raise ValueError("Сборка не найдена")
        members = list(assembly.members)
        if len(members) != 2:
            raise ValueError("Сборка должна содержать ровно две лопатки: внешнюю и внутреннюю")

        outer_blade = members[0].blade
        inner_blade = members[1].blade
        if not outer_blade or not inner_blade:
            raise ValueError("Не удалось загрузить лопатки сборки")

        outer_result = self._approx_single_blade_full(outer_blade.blade_id, outer_blade.name)
        inner_result = self._approx_single_blade_full(inner_blade.blade_id, inner_blade.name)

        combined_plot = self._generate_combined_plot(outer_result, inner_result, assembly.name)

        return {
            "assembly_name": assembly.name,
            "outer": outer_result,
            "inner": inner_result,
            "plot": combined_plot
        }

    def _approx_single_blade_full(self, blade_id: int, blade_name: str) -> Dict[str, Any]:
        """
        Полная аппроксимация одной лопатки.
        Возвращает исходные координаты, преобразованные (нормированные), коэффициенты Лежандра,
        а также параметры масштабирования для отображения аппроксимированных кривых в исходном масштабе.
        """
        coords = self.session.scalars(
            select(ProfileCoordinate).where(ProfileCoordinate.blade_id == blade_id)
        ).all()
        if not coords:
            raise ValueError(f"Для лопатки {blade_name} нет координат")

        upper = [(c.x, c.y) for c in coords if c.profile_type == 'upper']
        lower = [(c.x, c.y) for c in coords if c.profile_type == 'lower']
        if not upper or not lower:
            raise ValueError(f"У лопатки {blade_name} отсутствует верхний или нижний профиль")

        # Исходные координаты (абсолютные)
        x_u_orig = np.array([p[0] for p in upper])
        y_u_orig = np.array([p[1] for p in upper])
        x_l_orig = np.array([p[0] for p in lower])
        y_l_orig = np.array([p[1] for p in lower])

        # Вычисляем простые параметры исходного масштаба (без учёта поворота)
        min_x_orig = min(np.min(x_u_orig), np.min(x_l_orig))
        max_x_orig = max(np.max(x_u_orig), np.max(x_l_orig))
        chord_orig = max_x_orig - min_x_orig
        if chord_orig == 0:
            chord_orig = 1.0
        max_y_orig = max(np.max(y_u_orig), np.max(y_l_orig))

        # Преобразованные (нормированные) координаты
        x_u_t, y_u_t, x_l_t, y_l_t = transform_coordinates(x_u_orig, y_u_orig, x_l_orig, y_l_orig)

        # Вычисление коэффициентов Лежандра
        L_u = calc_L(x_u_t, y_u_t)
        L_l = calc_L(x_l_t, y_l_t)
        if L_u is None or L_l is None:
            raise ValueError(f"Ошибка вычисления коэффициентов для лопатки {blade_name}")

        legendre_coeffs = [{"upper": float(L_u[i]), "lower": float(L_l[i])} for i in range(len(L_u))]

        # Параметры аппроксимации (нормированные)
        y_u_calc = np.dot(L_u, Lezh(x_u_t))
        max_y_u = float(np.max(y_u_calc))
        x_max_u = float(x_u_t[np.argmax(y_u_calc)])
        r2_u = float(R2(y_u_calc, y_u_t))

        y_l_calc = np.dot(L_l, Lezh(x_l_t))
        max_y_l = float(np.max(y_l_calc))
        x_max_l = float(x_l_t[np.argmax(y_l_calc)])
        r2_l = float(R2(y_l_calc, y_l_t))

        # Преобразованные координаты для детального просмотра
        transformed_coords = []
        for i in range(len(x_u_t)):
            transformed_coords.append({"type": "upper", "x": float(x_u_t[i]), "y": float(y_u_t[i])})
        for i in range(len(x_l_t)):
            transformed_coords.append({"type": "lower", "x": float(x_l_t[i]), "y": float(y_l_t[i])})

        # Исходные координаты для визуализации сборки
        original_coords = {
            "upper": [{"x": float(x), "y": float(y)} for x, y in zip(x_u_orig, y_u_orig)],
            "lower": [{"x": float(x), "y": float(y)} for x, y in zip(x_l_orig, y_l_orig)]
        }

        # Генерируем индивидуальный график (для одиночной лопатки)
        plot_img = self._generate_single_plot(x_u_t, y_u_t, x_l_t, y_l_t, L_u, L_l, blade_name)

        return {
            "blade_id": blade_id,
            "blade_name": blade_name,
            "chord": chord_orig,
            "min_x": min_x_orig,
            "max_y_orig": max_y_orig,
            "original_coords": original_coords,
            "transformed_coords": transformed_coords,
            "legendre_coeffs": legendre_coeffs,
            "params": {
                "upper": {"max_y": max_y_u, "x_at_max": x_max_u, "r2": r2_u},
                "lower": {"max_y": max_y_l, "x_at_max": x_max_l, "r2": r2_l}
            },
            "plot": plot_img
        }

    def _generate_combined_plot(self, outer: Dict, inner: Dict, title: str) -> str:
        """
        Генерирует PNG‑график сборки, используя исходные (абсолютные) координаты лопаток
        с отражением по Y, а также аппроксимированные кривые (полиномы Лежандра),
        приведённые к исходному масштабу.
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        import numpy as np

        # Глобальный максимум Y для отражения (из обеих лопаток)
        max_y_global = max(outer['max_y_orig'], inner['max_y_orig'])

        plt.figure(figsize=(8, 4.5))

        # ---------- Точки исходных профилей ----------
        def plot_points(coords_dict, color, label_prefix):
            up = coords_dict["upper"]
            low = coords_dict["lower"]
            if up:
                x_up = [p["x"] for p in up]
                y_up_ref = [max_y_global - p["y"] for p in up]
                plt.plot(x_up, y_up_ref, 'o', markersize=3, color=color, label=f"{label_prefix} (верх)")
            if low:
                x_low = [p["x"] for p in low]
                y_low_ref = [max_y_global - p["y"] for p in low]
                plt.plot(x_low, y_low_ref, '+', markersize=4, color=color, label=f"{label_prefix} (низ)")

        plot_points(outer["original_coords"], 'blue', outer['blade_name'])
        plot_points(inner["original_coords"], 'red', inner['blade_name'])

        # ---------- Аппроксимированные кривые (Лежандр) ----------
        def plot_approx(blade_data, color, label_prefix):
            chord = blade_data['chord']
            min_x = blade_data['min_x']
            legendre = blade_data['legendre_coeffs']
            # Коэффициенты
            L_u = np.array([c["upper"] for c in legendre])
            L_l = np.array([c["lower"] for c in legendre])
            x_norm = np.linspace(0, 1, 200)
            lezh_mat = Lezh(x_norm)
            y_u_norm = np.dot(L_u, lezh_mat)   # нормализованная высота
            y_l_norm = np.dot(L_l, lezh_mat)
            # Переводим в исходные координаты (без поворота, только масштабирование и сдвиг)
            # Это приближение, но для визуализации даёт разумное совпадение с точками.
            x_orig = min_x + x_norm * chord
            y_u_orig = y_u_norm * blade_data['max_y_orig']
            y_l_orig = y_l_norm * blade_data['max_y_orig']
            # Отражаем Y
            y_u_ref = max_y_global - y_u_orig
            y_l_ref = max_y_global - y_l_orig

            plt.plot(x_orig, y_u_ref, '-', linewidth=2, color=color, alpha=0.7,
                     label=f"{label_prefix} (аппрокс. верх)")
            plt.plot(x_orig, y_l_ref, '--', linewidth=2, color=color, alpha=0.7,
                     label=f"{label_prefix} (аппрокс. низ)")

        plot_approx(outer, 'blue', outer['blade_name'])
        plot_approx(inner, 'red', inner['blade_name'])

        plt.legend(loc='best', fontsize='small')
        plt.grid(True, alpha=0.6)
        plt.xlabel('X (исходные координаты)')
        plt.ylabel('Y (отражённые, исходные)')
        plt.title(f'Аппроксимация сборки: {title}')
        plt.axis('equal')

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{img_b64}"

    def _generate_single_plot(self, x_u, y_u, x_l, y_l, L_u, L_l, title_name):
        """Генерирует PNG‑график для одной лопатки (нормированные координаты с линиями аппроксимации)."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        import numpy as np

        plt.figure(figsize=(8, 4.5))
        x_plot = np.linspace(0, 1, 200)
        lezh_matrix = Lezh(x_plot)

        plt.plot(x_u, y_u, 'o', markersize=4, label='Верхний (точки)')
        plt.plot(x_l, y_l, '+', markersize=5, label='Нижний (точки)')
        y_u_fit = np.dot(L_u, lezh_matrix)
        y_l_fit = np.dot(L_l, lezh_matrix)
        plt.plot(x_plot, y_u_fit, '-', linewidth=2, label='Аппрокс. верх')
        plt.plot(x_plot, y_l_fit, '--', linewidth=2, label='Аппрокс. низ')

        plt.legend(), plt.grid(True, alpha=0.6)
        plt.xlabel('X (нормированная хорда)')
        plt.ylabel('Y (нормированная)')
        plt.title(f'Аппроксимация: {title_name}')
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{img_b64}"