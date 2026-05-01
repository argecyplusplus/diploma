import os
import subprocess
import threading
import re
from pathlib import Path
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..repositories.simulation_repository import SimulationRepository
from ..dto.simulation_dto import SimulationCreateRequest, InitialConditionCreateRequest
from ..models.simulation import (
    Simulation, InitialCondition, ConstructionParameter, PotentialFlowParameter,
    BoundaryIdentifier, BladeChord, TimeParameter
)
from ..models.blade import Approximation, LegendreCoefficient
from ..models.material import Material
from ..utils.database import get_db_session

logger = logging.getLogger(__name__)


class SimulationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = SimulationRepository(session)
        self.upload_dir = os.path.join(os.getcwd(), 'uploads', 'simulations')
        os.makedirs(self.upload_dir, exist_ok=True)

    def create_initial_condition(self, data: InitialConditionCreateRequest) -> int:
        ic_data = data.model_dump()
        ic = self.repo.create_initial_condition(ic_data)
        return ic.initial_conditions_id

    def get_initial_conditions_list(self):
        return self.repo.get_all_initial_conditions()

    def get_simulation_status(self, sim_id: int) -> dict:
        sim = self.session.get(Simulation, sim_id)
        if not sim:
            return {"error": "Not found"}
        return {"status": sim.status, "progress": getattr(sim, 'progress', 0)}

    def create_simulation(self, data: SimulationCreateRequest) -> int:
        # Проверка: ровно один из id должен быть указан
        if (data.blade_id is None and data.assembly_id is None) or \
                (data.blade_id is not None and data.assembly_id is not None):
            raise ValueError("Должна быть указана либо лопатка, либо объединение, но не оба")

        sim_data = data.model_dump(exclude={'tasks', 'material_ids'})
        sim_data = {k: v for k, v in sim_data.items() if v is not None}
        if 'assembly_id' in sim_data:
            sim_data['blade_assembly_id'] = sim_data.pop('assembly_id')

        # Устанавливаем начальный статус
        sim_data['status'] = 'pending'
        sim = self.repo.create(**sim_data)
        sim_id = sim.simulation_id

        self.repo.add_materials(sim_id, data.material_ids)
        self.repo.add_tasks(sim_id, [t.model_dump() for t in data.tasks])
        self.session.commit()   # сохраняем, чтобы запись была до фоновой задачи

        # Создаём папку и генерируем .edp (синхронно)
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        os.makedirs(sim_dir, exist_ok=True)
        edp_path = os.path.join(sim_dir, "blade_sim.edp")

        try:
            self._generate_freefem_code(sim_id, sim_dir, edp_path)
        except Exception as e:
            # Если генерация кода упала, помечаем симуляцию как failed
            sim.status = 'failed'
            self.session.commit()
            raise e

        # Запускаем фоновый поток для выполнения FreeFEM
        thread = threading.Thread(target=self._run_simulation_background,
                                   args=(sim_id, edp_path, sim_dir),
                                   daemon=True)
        thread.start()

        return sim_id

    def _run_simulation_background(self, sim_id: int, edp_path: str, sim_dir: str):
        from sqlalchemy.orm import sessionmaker
        from ..utils.database import get_engine
        from ..repositories.simulation_repository import SimulationRepository

        engine = get_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            sim = session.get(Simulation, sim_id)
            if not sim:
                logger.error(f"Simulation {sim_id} not found in background")
                return

            sim.status = "running"
            session.commit()

            logger.info(f"🚀 Запуск FreeFEM++ для симуляции {sim_id}...")
            result = self._run_freefem(edp_path, sim_dir)

            # Сохраняем лог
            log_path = os.path.join(sim_dir, "console.log")
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(result.get('stdout', '') + '\n--- ERROR OUTPUT ---\n' + result.get('stderr', ''))

            # Используем репозиторий с нашей сессией
            repo = SimulationRepository(session)
            repo.add_result(sim_id, "log", log_path, "FreeFEM++ console output")

            if result['success']:
                sim.status = "completed"
                vtk_path = os.path.join(sim_dir, "result.vtk")
                if os.path.exists(vtk_path):
                    repo.add_result(sim_id, "vtk", vtk_path, "Mesh & Field data")
            else:
                sim.status = "failed"
                logger.error(f"❌ Симуляция {sim_id} завершилась с ошибкой: {result.get('error')}")

            session.commit()
        except Exception as e:
            logger.error(f"💥 Ошибка в фоновой задаче симуляции {sim_id}: {e}", exc_info=True)
            try:
                sim = session.get(Simulation, sim_id)
                if sim:
                    sim.status = "failed"
                    session.commit()
            except:
                pass
        finally:
            session.close()

    def get_simulations_list(self):
        return self.repo.get_all_simulations()

    # ========================================================================
    # 🔧 Внутренние методы генерации и запуска (без изменений, но модифицируем _generate_freefem_code для проверки blade_id)
    # ========================================================================

    def _generate_freefem_code(self, sim_id: int, sim_dir: str, edp_path: str):
        sim = self.session.get(Simulation, sim_id)
        if not sim.blade_id:
            raise ValueError(
                "Для моделирования необходимо выбрать конкретную лопатку (аппроксимация привязана к лопатке)")
        ic_id = sim.initial_conditions_id

        # 1. Получаем все необходимые параметры из БД
        const_params = self.session.scalar(
            select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        flow_params = self.session.scalar(
            select(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))
        time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
        boundary = self.session.scalar(
            select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))
        chord = self.session.scalar(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id))

        # 2. Материал (берём первый из связанных)
        first_mat_id = sim.materials[0].material_id if sim.materials else None
        material = self.session.get(Material, first_mat_id)
        rho = material.density if material else 1.0

        # 3. Аппроксимация и коэффициенты Лежандра
        approx = self.session.scalar(
            select(Approximation).where(Approximation.blade_id == sim.blade_id)
            .order_by(Approximation.approximation_id.desc()))
        if not approx:
            raise ValueError(
                "Для выбранной лопатки не выполнена аппроксимация. Запустите аппроксимацию перед моделированием.")

        coeffs = self.session.scalars(
            select(LegendreCoefficient).where(LegendreCoefficient.approximation_id == approx.approximation_id)
            .order_by(LegendreCoefficient.legendre_coefficients_id)).all()
        if len(coeffs) < 10:
            raise ValueError("Недостаточно коэффициентов Лежандра (ожидается 10).")

        # 4. Сохраняем коэффициенты в CSV-файл (как требует шаблон)
        coeffs_csv = os.path.join(sim_dir, "out_L_blade.csv")
        with open(coeffs_csv, 'w', encoding='utf-8') as f:
            upper_vals = [f"{c.upper_value:.15e}" for c in coeffs]
            lower_vals = [f"{c.lower_value:.15e}" for c in coeffs]
            f.write(" ".join(upper_vals) + "\n")
            f.write(" ".join(lower_vals) + "\n")

        # 5. Загружаем шаблон
        template_path = Path(__file__).parent.parent / "templates" / "blade_sim.edp.template"
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # 6. Заменяем параметры
        replacements = {
            "{{S1}}": str(boundary.value if boundary else 100),
            "{{Chord1}}": str(chord.value if chord else 1.0),
            "{{beta}}": str(flow_params.beta if flow_params else 0.0),
            "{{B}}": str(flow_params.B if flow_params else 1.0),
            "{{rho}}": str(rho),
            "{{NC}}": str(const_params.NC if const_params else 50),
            "{{NSp}}": str(const_params.NSp if const_params else 50),
            "{{NSm}}": str(const_params.NSm if const_params else 50),
            "{{NSpm}}": str(const_params.NSpm if const_params else 20),
            "{{NSpn}}": str(const_params.NSpn if const_params else 10),
            "{{dt}}": str(time_params.dt if time_params else 0.1),
            "{{nbT}}": str(time_params.nbT if time_params else 100),
        }

        script = template
        for key, val in replacements.items():
            script = script.replace(key, val)

        # 7. Сохраняем финальный .edp файл
        with open(edp_path, 'w', encoding='utf-8') as f:
            f.write(script)

        logger.info(f"📝 Скрипт FreeFEM++ сохранён: {edp_path}")
        logger.info(f"📝 Коэффициенты Лежандра сохранены в: {coeffs_csv}")

    def _run_freefem(self, edp_path: str, work_dir: str) -> dict:
        ff_path = os.getenv("FREEFEM_PATH", "FreeFem++")
        cmd = [ff_path, edp_path, "-nw"]
        env = os.environ.copy()
        env['PWD'] = work_dir

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=work_dir,
                env=env
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.stderr if result.returncode != 0 else None
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Превышено время выполнения (10 мин)"}
        except FileNotFoundError:
            return {"success": False, "error": f"FreeFEM++ не найден по пути: {ff_path}. Укажите FREEFEM_PATH в .env"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_initial_condition(self, ic_id: int):
        ic = self.session.get(InitialCondition, ic_id)
        if ic:
            self.session.delete(ic)