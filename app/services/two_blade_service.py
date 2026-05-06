import os
import subprocess
import threading
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..repositories.blade_repository import BladeRepository
from ..models.blade import LegendreCoefficient
from ..dto.two_blade_dto import TwoBladeCreateRequest

logger = logging.getLogger(__name__)

class TwoBladeService:
    def __init__(self, session: Session):
        self.session = session
        self.blade_repo = BladeRepository(session)
        self.upload_dir = os.path.join(os.getcwd(), 'uploads', 'two_blade_simulations')
        os.makedirs(self.upload_dir, exist_ok=True)

    def run_simulation(self, data: TwoBladeCreateRequest) -> int:
        # Генерируем ID моделирования (пока просто временный, можно сохранять в БД позже)
        sim_id = self._get_next_id()
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        os.makedirs(sim_dir, exist_ok=True)

        # 1. Получаем коэффициенты Лежандра для обеих лопаток
        coeffs_main = self._get_legendre_coeffs(data.blade_id)
        coeffs_small = self._get_legendre_coeffs(data.blade_id_small)
        if not coeffs_main or not coeffs_small:
            raise ValueError("Не удалось загрузить коэффициенты Лежандра для одной из лопаток")

        # 2. Генерируем out_L.csv
        csv_path = os.path.join(sim_dir, "out_L.csv")
        self._generate_out_csv(csv_path, coeffs_main, coeffs_small)

        # 3. Подставляем параметры в шаблон и сохраняем .edp
        template_path = Path(__file__).parent.parent / "templates" / "two_blade_sim.edp.template"
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        script = self._fill_template(template, data, sim_dir)
        edp_path = os.path.join(sim_dir, "AeroTherm_gen.edp")
        with open(edp_path, 'w', encoding='utf-8') as f:
            f.write(script)

        # 4. Запускаем FreeFEM в фоновом потоке
        thread = threading.Thread(target=self._run_freefem, args=(edp_path, sim_dir, sim_id), daemon=True)
        thread.start()
        return sim_id

    def _get_next_id(self) -> int:
        # Простейший способ: смотрим существующие папки
        existing = [int(d.name.split('_')[1]) for d in Path(self.upload_dir).iterdir() if d.is_dir() and d.name.startswith('sim_')]
        return max(existing) + 1 if existing else 1

    def _get_legendre_coeffs(self, blade_id: int):
        """Возвращает два списка: upper_value и lower_value (по 10 элементов)"""
        coeffs = self.session.scalars(
            select(LegendreCoefficient)
            .where(LegendreCoefficient.blade_id == blade_id)
            .order_by(LegendreCoefficient.legendre_coefficients_id)
        ).all()
        if len(coeffs) != 10:
            raise ValueError(f"Для лопатки {blade_id} недостаточно коэффициентов Лежандра (ожидается 10)")
        upper = [c.upper_value for c in coeffs]
        lower = [c.lower_value for c in coeffs]
        return (upper, lower)

    def _generate_out_csv(self, path: str, main, small):
        with open(path, 'w', encoding='utf-8') as f:
            # 4 строки: верх большой, низ большой, верх малой, низ малой
            f.write(" ".join(f"{v:.15e}" for v in main[0]) + "\n")
            f.write(" ".join(f"{v:.15e}" for v in main[1]) + "\n")
            f.write(" ".join(f"{v:.15e}" for v in small[0]) + "\n")
            f.write(" ".join(f"{v:.15e}" for v in small[1]) + "\n")

    def _fill_template(self, template: str, data: TwoBladeCreateRequest, work_dir: str) -> str:
        # Заменяем все {{ param }} на значения из data
        replacements = {
            "{{ chord }}": str(data.chord),
            "{{ chord2 }}": str(data.chord2),
            "{{ dely_offset }}": str(data.dely_offset),
            "{{ t_gas }}": str(data.t_gas),
            "{{ t_cool }}": str(data.t_cool),
            "{{ t_blade }}": str(data.t_blade),
            "{{ press0 }}": str(data.press0),
            "{{ u0 }}": str(data.u0),
            "{{ beta }}": str(data.beta),
            "{{ houter }}": str(data.houter),
            "{{ hinner }}": str(data.hinner),
            "{{ rgas }}": str(data.rgas),
            "{{ cpgas }}": str(data.cpgas),
            "{{ kgas }}": str(data.kgas),
            "{{ rhosteel }}": str(data.rhosteel),
            "{{ cpsteel }}": str(data.cpsteel),
            "{{ ksteel }}": str(data.ksteel),
        }
        script = template
        for key, val in replacements.items():
            script = script.replace(key, val)
        return script

    def _run_freefem(self, edp_path: str, work_dir: str, sim_id: int):
        ff_path = os.getenv("FREEFEM_PATH", "FreeFem++")
        cmd = [ff_path, edp_path, "-nw"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=work_dir)
            if result.returncode != 0:
                logger.error(f"FreeFEM error for sim {sim_id}: {result.stderr}")
            else:
                logger.info(f"FreeFEM completed for sim {sim_id}")
        except Exception as e:
            logger.exception(f"Error running FreeFEM for sim {sim_id}: {e}")