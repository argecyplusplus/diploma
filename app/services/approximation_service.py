# app/services/approximation_service.py
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from ..models.blade import Blade, ProfileCoordinate, Approximation, ApproximationParameter, LegendreCoefficient, TransformedCoordinate
from app.utils.approximation_math import Lezh, calc_L, R2, transform_coordinates
import numpy as np

class ApproximationService:
    def __init__(self, session: Session):
        self.session = session

    def execute_approximation(self, blade_id: int) -> Dict[str, Any]:
        # 1. Загрузка координат
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

        # 2. Трансформация
        x_u_t, y_u_t, x_l_t, y_l_t = transform_coordinates(x_u, y_u, x_l, y_l)

        # 3. Очистка старых данных аппроксимации
        approx_stmt = select(Approximation).where(Approximation.blade_id == blade_id)
        old_approx = self.session.scalars(approx_stmt).first()
        if old_approx:
            self.session.execute(delete(Approximation).where(Approximation.blade_id == blade_id))
            self.session.flush()

        # 4. Создание записи аппроксимации
        approx = Approximation(blade_id=blade_id, type='legendre_9')
        self.session.add(approx)
        self.session.flush()
        aid = approx.approximation_id

        # 5. Сохранение преобразованных координат
        for x, y in zip(x_u_t, y_u_t):
            self.session.add(TransformedCoordinate(approximation_id=aid, profile_type='upper', x_transformed=float(x), y_transformed=float(y)))
        for x, y in zip(x_l_t, y_l_t):
            self.session.add(TransformedCoordinate(approximation_id=aid, profile_type='lower', x_transformed=float(x), y_transformed=float(y)))

        # 6. Расчет и сохранение коэффициентов Лежандра
        L_u = calc_L(x_u_t, y_u_t)
        L_l = calc_L(x_l_t, y_l_t)
        if L_u is None or L_l is None:
            raise ValueError("Ошибка вычисления коэффициентов (матрица вырождена)")

        for i in range(len(L_u)):
            self.session.add(LegendreCoefficient(approximation_id=aid, upper_value=float(L_u[i]), lower_value=float(L_l[i])))

        # 7. Расчет и сохранение параметров
        y_u_calc = np.dot(L_u, Lezh(x_u_t))
        self.session.add(ApproximationParameter(approximation_id=aid, profile_type='upper',
            max_profile_value=float(np.max(y_u_calc)), x_coordinate_max=float(x_u_t[np.argmax(y_u_calc)]), r_squared=float(R2(y_u_calc, y_u_t))))

        y_l_calc = np.dot(L_l, Lezh(x_l_t))
        self.session.add(ApproximationParameter(approximation_id=aid, profile_type='lower',
            max_profile_value=float(np.max(y_l_calc)), x_coordinate_max=float(x_l_t[np.argmax(y_l_calc)]), r_squared=float(R2(y_l_calc, y_l_t))))

        self.session.flush()
        return {"approximation_id": aid, "message": "Аппроксимация выполнена успешно"}