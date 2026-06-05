import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from ..models.blade import Blade, ProfileCoordinate, Approximation, ApproximationParameter, LegendreCoefficient, TransformedCoordinate, BladeAssembly
from ..utils.approximation_math import Lezh, calc_L, R2, transform_coordinates, inverse_transform
import numpy as np

logger = logging.getLogger(__name__)

class ApproximationService:
    def __init__(self, session: Session):
        self.session = session

    def execute_approximation(self, blade_id: int) -> Dict[str, Any]:
        """Аппроксимация одной лопатки (как в WGKM_L5.py)"""
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

        x_u_t, y_u_t, x_l_t, y_l_t, tr_params = transform_coordinates(x_u, y_u, x_l, y_l)

        old_approx = self.session.scalar(select(Approximation).where(Approximation.blade_id == blade_id))
        if old_approx:
            self.session.delete(old_approx)
            self.session.flush()

        approx = Approximation(blade_id=blade_id, type='legendre_9')
        self.session.add(approx)
        self.session.flush()
        aid = approx.approximation_id

        for x, y in zip(x_u_t, y_u_t):
            self.session.add(TransformedCoordinate(
                approximation_id=aid, profile_type='upper',
                x_transformed=float(x), y_transformed=float(y)
            ))
        for x, y in zip(x_l_t, y_l_t):
            self.session.add(TransformedCoordinate(
                approximation_id=aid, profile_type='lower',
                x_transformed=float(x), y_transformed=float(y)
            ))

        L_u = calc_L(x_u_t, y_u_t)
        L_l = calc_L(x_l_t, y_l_t)
        if L_u is None or L_l is None:
            raise ValueError("Ошибка вычисления коэффициентов (матрица вырождена)")

        for i in range(10):
            upper_val = float(L_u[i]) if i < len(L_u) else 0.0
            lower_val = float(L_l[i]) if i < len(L_l) else 0.0
            self.session.add(LegendreCoefficient(
                approximation_id=aid,
                upper_value=upper_val,
                lower_value=lower_val
            ))

        y_u_calc = np.dot(L_u, Lezh(x_u_t))
        y_l_calc = np.dot(L_l, Lezh(x_l_t))

        self.session.add(ApproximationParameter(
            approximation_id=aid, profile_type='upper',
            max_profile_value=float(np.max(y_u_calc)),
            x_coordinate_max=float(x_u_t[np.argmax(y_u_calc)]),
            r_squared=float(R2(y_u_calc, y_u_t))
        ))
        self.session.add(ApproximationParameter(
            approximation_id=aid, profile_type='lower',
            max_profile_value=float(np.max(y_l_calc)),
            x_coordinate_max=float(x_l_t[np.argmax(y_l_calc)]),
            r_squared=float(R2(y_l_calc, y_l_t))
        ))

        self.session.flush()
        return {"approximation_id": aid, "message": "Аппроксимация выполнена успешно"}

    def execute_assembly_approximation(self, assembly_id: int) -> Dict[str, Any]:
        """
        Аппроксимация сборки (ровно две лопатки).
        Первая лопатка (описание 'outer') — внешняя.
        Вторая лопатка (описание 'inner') — внутренняя полость.
        """
        assembly = self.session.get(BladeAssembly, assembly_id)
        if not assembly:
            raise ValueError("Сборка не найдена")

        members = sorted(
            list(assembly.members),
            key=lambda m: (
                0 if (m.description or '').lower() == 'outer' else
                1 if (m.description or '').lower() == 'inner' else
                2,
                m.blade_assembly_members_id
            )
        )

        if len(members) != 2:
            raise ValueError("Сборка должна содержать ровно две лопатки: внешнюю и внутреннюю")

        outer_blade = members[0].blade
        inner_blade = members[1].blade

        outer_result = self._approx_single_blade_full(outer_blade.blade_id, outer_blade.name)
        inner_result = self._approx_single_blade_full(inner_blade.blade_id, inner_blade.name)

        self._save_assembly_coeffs_to_file(assembly.name, outer_result, inner_result)

        combined_plot = self._generate_combined_plot(outer_result, inner_result, assembly.name)

        return {
            "assembly_name": assembly.name,
            "outer": outer_result,
            "inner": inner_result,
            "plot": combined_plot
        }

    def _save_assembly_coeffs_to_file(self, assembly_name: str, outer_result: Dict, inner_result: Dict):
        """Сохраняет коэффициенты Лежандра в файл out_L_{name}.csv в формате эталона"""
        from pathlib import Path

        out_dir = Path(__file__).parent.parent.parent / "out_files"
        out_dir.mkdir(exist_ok=True)

        filename = out_dir / f"out_L_{assembly_name}.csv"

        with open(filename, 'w', encoding='utf-8') as f:
            # Внешняя лопатка: верхний профиль
            upper_outer = [str(c['upper']) for c in outer_result['legendre_coeffs']]
            f.write(" ".join(upper_outer) + "\n")
            # Внешняя лопатка: нижний профиль
            lower_outer = [str(c['lower']) for c in outer_result['legendre_coeffs']]
            f.write(" ".join(lower_outer) + "\n")
            # Внутренняя лопатка: верхний профиль
            upper_inner = [str(c['upper']) for c in inner_result['legendre_coeffs']]
            f.write(" ".join(upper_inner) + "\n")
            # Внутренняя лопатка: нижний профиль
            lower_inner = [str(c['lower']) for c in inner_result['legendre_coeffs']]
            f.write(" ".join(lower_inner) + "\n")

        logger.info(f"Сохранены коэффициенты сборки в {filename}")

    def _approx_single_blade_full(self, blade_id: int, blade_name: str) -> Dict[str, Any]:
        """
        Полная аппроксимация одной лопатки.
        Возвращает исходные координаты и аппроксимированную кривую
        в исходных абсолютных координатах через полное обратное преобразование.
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

        x_u_orig = np.array([p[0] for p in upper])
        y_u_orig = np.array([p[1] for p in upper])
        x_l_orig = np.array([p[0] for p in lower])
        y_l_orig = np.array([p[1] for p in lower])

        min_x_orig = float(min(np.min(x_u_orig), np.min(x_l_orig)))
        max_x_orig = float(max(np.max(x_u_orig), np.max(x_l_orig)))
        chord_orig = max_x_orig - min_x_orig if max_x_orig != min_x_orig else 1.0
        max_y_orig = float(max(np.max(y_u_orig), np.max(y_l_orig)))

        x_u_t, y_u_t, x_l_t, y_l_t, tr_params = transform_coordinates(
            x_u_orig, y_u_orig, x_l_orig, y_l_orig
        )

        L_u = calc_L(x_u_t, y_u_t)
        L_l = calc_L(x_l_t, y_l_t)
        if L_u is None or L_l is None:
            raise ValueError(f"Ошибка вычисления коэффициентов для лопатки {blade_name}")

        legendre_coeffs = [{"upper": float(L_u[i]), "lower": float(L_l[i])} for i in range(len(L_u))]

        y_u_calc = np.dot(L_u, Lezh(x_u_t))
        max_y_u  = float(np.max(y_u_calc))
        x_max_u  = float(x_u_t[np.argmax(y_u_calc)])
        r2_u     = float(R2(y_u_calc, y_u_t))

        y_l_calc = np.dot(L_l, Lezh(x_l_t))
        max_y_l  = float(np.max(y_l_calc))
        x_max_l  = float(x_l_t[np.argmax(y_l_calc)])
        r2_l     = float(R2(y_l_calc, y_l_t))

        transformed_coords = []
        for i in range(len(x_u_t)):
            transformed_coords.append({"type": "upper", "x": float(x_u_t[i]), "y": float(y_u_t[i])})
        for i in range(len(x_l_t)):
            transformed_coords.append({"type": "lower", "x": float(x_l_t[i]), "y": float(y_l_t[i])})

        original_coords = {
            "upper": [{"x": float(x), "y": float(y)} for x, y in zip(x_u_orig, y_u_orig)],
            "lower": [{"x": float(x), "y": float(y)} for x, y in zip(x_l_orig, y_l_orig)]
        }
        x_norm = np.linspace(float(np.min(x_u_t)), float(np.max(x_u_t)), 200)
        lezh_mat   = Lezh(x_norm)
        y_u_norm   = np.dot(L_u, lezh_mat)
        y_l_norm   = np.dot(L_l, lezh_mat)

        x_u_curve, y_u_curve = inverse_transform(x_norm, y_u_norm, tr_params)
        x_l_curve, y_l_curve = inverse_transform(x_norm, y_l_norm, tr_params)

        approx_curve_original = {
            "upper": {"x": x_u_curve.tolist(), "y": y_u_curve.tolist()},
            "lower": {"x": x_l_curve.tolist(), "y": y_l_curve.tolist()}
        }

        plot_img = self._generate_single_plot(x_u_t, y_u_t, x_l_t, y_l_t, L_u, L_l, blade_name)

        return {
            "blade_id": blade_id,
            "blade_name": blade_name,
            "min_x": min_x_orig,
            "max_x": max_x_orig,
            "chord": chord_orig,
            "max_y_orig": max_y_orig,
            "original_coords": original_coords,
            "approx_curve_original": approx_curve_original,
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
        Генерирует PNG‑график сборки в исходных абсолютных координатах.
        Исходные точки и аппроксимированные кривые находятся в одном пространстве,
        поэтому отражение Y применяется одинаково к тем и другим.
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64

        max_y_global = max(outer['max_y_orig'], inner['max_y_orig'])

        plt.figure(figsize=(8, 4.5))

        def plot_points(coords_dict, color, label_prefix):
            up  = coords_dict["upper"]
            low = coords_dict["lower"]
            if up:
                plt.plot([p["x"] for p in up],
                         [max_y_global - p["y"] for p in up],
                         'o', markersize=3, color=color, label=f"{label_prefix} (верх)")
            if low:
                plt.plot([p["x"] for p in low],
                         [max_y_global - p["y"] for p in low],
                         '+', markersize=4, color=color, label=f"{label_prefix} (низ)")

        plot_points(outer["original_coords"], 'blue', outer['blade_name'])
        plot_points(inner["original_coords"], 'red',  inner['blade_name'])

        def plot_approx(blade_data, color, label_prefix):
            curve = blade_data["approx_curve_original"]
            x_u = np.array(curve["upper"]["x"])
            y_u = np.array(curve["upper"]["y"])
            x_l = np.array(curve["lower"]["x"])
            y_l = np.array(curve["lower"]["y"])
            plt.plot(x_u, max_y_global - y_u, '-',  linewidth=2, color=color, alpha=0.7,
                     label=f"{label_prefix} (аппрокс. верх)")
            plt.plot(x_l, max_y_global - y_l, '--', linewidth=2, color=color, alpha=0.7,
                     label=f"{label_prefix} (аппрокс. низ)")

        plot_approx(outer, 'green',  outer['blade_name'])
        plot_approx(inner, 'orange', inner['blade_name'])

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
        """Генерирует PNG‑график для одной лопатки (нормированные координаты)."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64

        plt.figure(figsize=(8, 4.5))
        x_plot      = np.linspace(0, 1, 200)
        lezh_matrix = Lezh(x_plot)

        plt.plot(x_u, y_u, 'o', markersize=4, label='Верхний (точки)')
        plt.plot(x_l, y_l, '+', markersize=5, label='Нижний (точки)')
        plt.plot(x_plot, np.dot(L_u, lezh_matrix), '-',  linewidth=2, label='Аппрокс. верх')
        plt.plot(x_plot, np.dot(L_l, lezh_matrix), '--', linewidth=2, label='Аппрокс. низ')

        plt.legend()
        plt.grid(True, alpha=0.6)
        plt.xlabel('X (нормированная хорда)')
        plt.ylabel('Y (нормированная)')
        plt.title(f'Аппроксимация: {title_name}')

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{img_b64}"

    def save_single_blade_coeffs_to_file(self, blade_id: int, blade_name: str) -> str:
        """Сохраняет коэффициенты Лежандра для одной лопатки в файл out_L_{blade_name}.csv"""
        from pathlib import Path

        approx = self.session.scalar(
            select(Approximation).where(Approximation.blade_id == blade_id)
            .order_by(Approximation.approximation_id.desc())
        )
        if not approx:
            raise ValueError(f"Аппроксимация для лопатки {blade_name} не найдена")

        coeffs = self.session.scalars(
            select(LegendreCoefficient).where(LegendreCoefficient.approximation_id == approx.approximation_id)
            .order_by(LegendreCoefficient.legendre_coefficients_id)
        ).all()

        if len(coeffs) < 10:
            raise ValueError(f"Недостаточно коэффициентов (найдено {len(coeffs)}, требуется 10)")

        out_dir = Path(__file__).parent.parent.parent / "out_files"
        out_dir.mkdir(exist_ok=True)

        filename = out_dir / f"out_L_{blade_name}.csv"

        with open(filename, 'w', encoding='utf-8') as f:
            upper_vals = " ".join(f"{c.upper_value:.15f}" for c in coeffs[:10])
            f.write(upper_vals + "\n")
            lower_vals = " ".join(f"{c.lower_value:.15f}" for c in coeffs[:10])
            f.write(lower_vals + "\n")

        logger.info(f"Сохранены коэффициенты лопатки {blade_name} в {filename}")
        return str(filename)