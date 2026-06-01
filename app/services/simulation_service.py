import os
import subprocess
import threading
import traceback
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..repositories.simulation_repository import SimulationRepository
from ..dto.simulation_dto import SimulationCreateRequest, InitialConditionCreateRequest, TaskType
from ..models.simulation import (
    Simulation, InitialCondition, ConstructionParameter, PotentialFlowParameter,
    BoundaryIdentifier, BladeChord, TimeParameter, InitialTemperature,
    ElasticityParameter, StressOutputParameter
)
from ..models.blade import (
    Approximation, LegendreCoefficient, BladeAssembly,
    ProfileCoordinate
)
from ..models.material import Material, ElValue
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


    def _ensure_approximation(self, blade_id: int):
        """
        Проверяет наличие актуальной аппроксимации для лопатки.
        Если её нет — выполняет автоматически.
        """
        approx = self.session.scalar(
            select(Approximation).where(Approximation.blade_id == blade_id)
            .order_by(Approximation.approximation_id.desc())
        )
        if approx:
            coeffs_count = self.session.scalar(
                select(func.count(LegendreCoefficient.legendre_coefficients_id))
                .where(LegendreCoefficient.approximation_id == approx.approximation_id)
            )
            if coeffs_count is not None and coeffs_count >= 10:
                logger.info(f"Аппроксимация для лопатки {blade_id} уже существует ({coeffs_count} коэффициентов)")
                return

        logger.info(f"Аппроксимация для лопатки {blade_id} не найдена или некорректна — запускаем автоматически")
        from ..services.approximation_service import ApproximationService
        approx_service = ApproximationService(self.session)
        approx_service.execute_approximation(blade_id)
        self.session.flush()

    def _get_blade_legendre_coeffs(self, blade_id: int):
        """Возвращает список LegendreCoefficient для лопатки (ровно 10 штук)."""
        approx = self.session.scalar(
            select(Approximation).where(Approximation.blade_id == blade_id)
            .order_by(Approximation.approximation_id.desc())
        )
        if not approx:
            raise ValueError(f"Аппроксимация для лопатки {blade_id} не найдена даже после автозапуска.")

        coeffs = self.session.scalars(
            select(LegendreCoefficient)
            .where(LegendreCoefficient.approximation_id == approx.approximation_id)
            .order_by(LegendreCoefficient.legendre_coefficients_id)
            .limit(10)
        ).all()

        if len(coeffs) < 10:
            raise ValueError(
                f"Недостаточно коэффициентов Лежандра для лопатки {blade_id} (найдено {len(coeffs)}, требуется 10).")

        logger.debug(f"Получено {len(coeffs)} коэффициентов для лопатки {blade_id}")
        return coeffs

    @staticmethod
    def _write_coeffs_csv(path: str, upper_vals, lower_vals):
        """
        Записывает коэффициенты Лежандра в CSV в десятичном формате (не e-нотация).
        Формат e-нотации (1.23e-05) некоторые версии FreeFEM++ читают некорректно
        через >>, что приводит к ошибке 'border points too close'.
        """

        def fmt(v):
            return f"{float(v):.15f}"

        upper_vals = upper_vals[:10]
        lower_vals = lower_vals[:10]

        with open(path, 'w', encoding='utf-8') as f:
            f.write(" ".join(fmt(v) for v in upper_vals) + "\n")
            f.write(" ".join(fmt(v) for v in lower_vals) + "\n")

        logger.debug(f"Записано {len(upper_vals)} коэффициентов в {path}")

    def create_simulation(self, data: SimulationCreateRequest):
        if data.task_type == TaskType.GAS_DYNAMICS:
            if data.assembly_id is not None or data.blade_id is None:
                raise ValueError(
                    "Для газодинамики необходимо указать конкретную лопатку (blade_id); assembly_id не допускается")
        else:
            if data.blade_id is None and data.assembly_id is None:
                raise ValueError("Для этой задачи выберите лопатку или объединение")

        if data.assembly_id is not None and data.task_type != TaskType.GAS_DYNAMICS:
            return self._create_assembly_simulation(data)
        else:
            return self._create_single_simulation(data)

    def _create_assembly_simulation(self, data: SimulationCreateRequest) -> int:
        """Создаёт одну симуляцию для объединения (задачи 2 и 3).
        Первый член сборки — внешняя лопатка, второй — внутренняя полость.
        """
        assembly = self.session.get(BladeAssembly, data.assembly_id)
        if not assembly or not assembly.members:
            raise ValueError("Объединение не содержит лопаток")
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
            raise ValueError("Объединение для задач 2-3 должно содержать ровно две лопатки")

        outer_blade = members[0].blade
        inner_blade = members[1].blade
        if not outer_blade or not inner_blade:
            raise ValueError("Не удалось загрузить лопатки объединения")

        self._ensure_approximation(outer_blade.blade_id)
        self._ensure_approximation(inner_blade.blade_id)

        sim_data = {
            'name': data.name,
            'blade_id': outer_blade.blade_id,   # внешняя лопатка — основная ссылка
            'blade_assembly_id': data.assembly_id,
            'initial_conditions_id': data.initial_conditions_id,
            'task_type': data.task_type.value,
            'status': 'pending'
        }
        sim = self.repo.create(**sim_data)
        sim_id = sim.simulation_id
        self.repo.add_materials(sim_id, data.material_ids)
        self.session.commit()

        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        os.makedirs(sim_dir, exist_ok=True)
        edp_path = os.path.join(sim_dir, "blade_sim.edp")

        try:
            self._generate_assembly_freefem_code(
                sim_id, sim_dir, edp_path,
                outer_blade.blade_id, inner_blade.blade_id
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            sim_update = self.session.get(Simulation, sim_id)
            sim_update.status = 'failed'
            sim_update.error_message = f"Ошибка генерации .edp (сборка): {str(e)}"
            self.session.commit()

        return sim_id

    def _create_single_simulation(self, data: SimulationCreateRequest) -> int:
        self._ensure_approximation(data.blade_id)

        sim_data = {
            'name': data.name,
            'blade_id': data.blade_id,
            'blade_assembly_id': data.assembly_id,
            'initial_conditions_id': data.initial_conditions_id,
            'task_type': data.task_type.value,
            'status': 'pending'
        }
        sim = self.repo.create(**sim_data)
        sim_id = sim.simulation_id
        self.repo.add_materials(sim_id, data.material_ids)
        self.session.commit()

        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        os.makedirs(sim_dir, exist_ok=True)
        edp_path = os.path.join(sim_dir, "blade_sim.edp")

        try:
            self._generate_freefem_code(sim_id, sim_dir, edp_path)
            logger.info(f"Скрипт сгенерирован: {edp_path}")
        except Exception as e:
            logger.error(traceback.format_exc())
            sim.status = 'failed'
            sim.error_message = f"Ошибка генерации .edp: {str(e)}"
            self.session.commit()
            return sim_id

        return sim_id

    def run_simulation_now(self, sim_id: int):
        """Запускает симуляцию в фоне (вызывается по кнопке)"""
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        edp_path = os.path.join(sim_dir, "blade_sim.edp")

        sim = self.session.get(Simulation, sim_id)
        if not sim:
            raise ValueError("Симуляция не найдена")

        if sim.status == 'running' or sim.status == 'completed':
            raise ValueError("Расчёт уже запущен или завершён")

        sim.status = "running"
        sim.progress = 0
        self.session.commit()

        thread = threading.Thread(
            target=self._run_simulation_background,
            args=(sim_id, edp_path, sim_dir),
            daemon=True
        )
        thread.start()
        return {"message": "Расчёт запущен"}

    def get_edp_content(self, sim_id: int) -> str:
        """Возвращает содержимое .edp файла для скачивания"""
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        edp_path = os.path.join(sim_dir, "blade_sim.edp")
        if not os.path.exists(edp_path):
            raise ValueError(f"Файл {edp_path} не найден")
        with open(edp_path, 'r', encoding='utf-8') as f:
            return f.read()

    def get_edp_path(self, sim_id: int) -> str:
        """Возвращает путь к .edp файлу"""
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        edp_path = os.path.join(sim_dir, "blade_sim.edp")
        return edp_path

    def _run_simulation_background(self, sim_id: int, edp_path: str, sim_dir: str):
        from sqlalchemy.orm import sessionmaker
        from ..utils.database import get_engine
        from ..repositories.simulation_repository import SimulationRepository

        engine = get_engine()
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            sim = session.get(Simulation, sim_id)
            if not sim:
                return
            sim.progress = 30
            session.commit()

            result = self._run_freefem(edp_path, sim_dir)

            log_path = os.path.join(sim_dir, "console.log")
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(result.get('stdout', '') + '\n--- STDERR ---\n' + result.get('stderr', ''))

            repo = SimulationRepository(session)
            repo.add_result(sim_id, "log", log_path, "FreeFEM++ console output")

            if result['success']:
                sim.status = "completed"
                sim.progress = 100
                vtk_path = os.path.join(sim_dir, "result.vtk")
                if os.path.exists(vtk_path):
                    repo.add_result(sim_id, "vtk", vtk_path, "Mesh & Field data")

                if sim.task_type == TaskType.THERMAL_FIELD.value:
                    for csv_file in ["TFout.csv", "Profout.csv"]:
                        csv_path = os.path.join(sim_dir, csv_file)
                        if os.path.exists(csv_path):
                            repo.add_result(sim_id, "csv", csv_path, f"Output {csv_file}")

                if sim.task_type == TaskType.THERMAL_STRESS.value:
                    for csv_file in ["Profout.csv", "TSout.csv", "TEpsout.csv"]:
                        csv_path = os.path.join(sim_dir, csv_file)
                        if os.path.exists(csv_path):
                            repo.add_result(sim_id, "csv", csv_path, f"Output {csv_file}")
            else:
                sim.status = "failed"
                sim.error_message = result.get('stderr') or result.get('error') or "FreeFEM завершился с ошибкой"
                logger.error(f"❌ Симуляция {sim_id} ошибка: {sim.error_message}")
            session.commit()
        except Exception as e:
            logger.error(f"💥 Ошибка в фоновой задаче: {e}", exc_info=True)
            sim = session.get(Simulation, sim_id)
            if sim:
                sim.status = "failed"
                sim.error_message = f"Внутренняя ошибка: {str(e)}"
                session.commit()
        finally:
            session.close()

    def get_simulations_list(self):
        return self.repo.get_all_simulations()


    def _generate_freefem_code(self, sim_id: int, sim_dir: str, edp_path: str):
        sim = self.session.get(Simulation, sim_id)
        if not sim.blade_id:
            raise ValueError("Для моделирования необходима лопатка (аппроксимация привязана к лопатке)")

        ic_id = sim.initial_conditions_id
        task_type = TaskType(sim.task_type)

        coeffs = self._get_blade_legendre_coeffs(sim.blade_id)

        coeffs_csv = os.path.join(sim_dir, "out_L_blade.csv")
        self._write_coeffs_csv(
            coeffs_csv,
            [c.upper_value for c in coeffs],
            [c.lower_value for c in coeffs]
        )

        chord = self.session.scalar(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id))
        constr = self.session.scalar(
            select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        boundary = self.session.scalar(
            select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))
        flow = self.session.scalar(
            select(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))

        replacements = {
            "Chord1": str(chord.value if chord else 1.0),
            "S1": str(boundary.value if boundary else 100),
            "beta": str(flow.beta if flow else 0.0),
            "B": str(flow.B if flow else 1.0),
            "NC": str(constr.NC if constr and constr.NC > 0 else 50),
            "NSp": str(constr.NSp if constr and constr.NSp > 0 else 50),
            "NSm": str(constr.NSm if constr and constr.NSm > 0 else 50),
            "NSpm": str(constr.NSpm if constr and constr.NSpm > 0 else 20),
            "NSpn": str(constr.NSpn if constr and constr.NSpn > 0 else 10),
            "rho": str(sim.materials[0].material.density if sim.materials else 1.0),
        }

        if task_type == TaskType.GAS_DYNAMICS:
            template_name = "gas_dynamics.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp = self.session.scalar(
                select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            material = sim.materials[0].material if sim.materials else None
            k_steel = material.thermal_conductivity if material and material.thermal_conductivity else 0.1
            replacements.update({
                "dt": str(time_params.dt if time_params else 0.05),
                "nbT": str(time_params.nbT if time_params else 25),
                "T_initial": str(init_temp.value if init_temp else 250),
                "ksteel": str(k_steel),
                "kair": "0.01",
            })

        elif task_type == TaskType.THERMAL_FIELD:
            template_name = "thermal_field.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp   = self.session.scalar(select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            stress_out  = self.session.scalar(select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
            replacements.update({
                "Time":      str(time_params.time if time_params and time_params.time else 0.1),
                "dt":        str(time_params.dt   if time_params else 0.05),
                "Nplot":     str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value if init_temp else 250),
                "a_steel":   "12.54",
                "a_air":     "21.02",
                "delt":      str(stress_out.delt if stress_out else 0.4),
                "Npt":       str(stress_out.Npt  if stress_out else 200),
            })
            # создаём папку plots внутри sim_dir (FreeFEM пишет туда eps)
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        elif task_type == TaskType.THERMAL_STRESS:
            template_name = "thermal_stress.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp   = self.session.scalar(select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            elastic     = self.session.scalar(select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
            stress_out  = self.session.scalar(select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
            material    = sim.materials[0].material if sim.materials else None
            ei_value    = None
            if elastic and material:
                ei_value = self.session.scalar(
                    select(ElValue).where(
                        ElValue.elasticity_parameters_id == elastic.elasticity_parameters_id,
                        ElValue.material_id == material.material_id
                    )
                )
            E_steel = ei_value.value if ei_value else 2.1e5
            replacements.update({
                "Time":      str(time_params.time if time_params and time_params.time else 0.1),
                "dt":        str(time_params.dt   if time_params else 0.05),
                "Nplot":     str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value if init_temp else 250),
                "a_steel":   "12.54",
                "a_air":     "21.02",
                "b":         str(elastic.b   if elastic else 1.0),
                "nu":        str(elastic.nu  if elastic else 0.28),
                "KLT":       str(elastic.KLT if elastic else 10.5e-6),
                "E_steel":   str(E_steel),
                "delt":      str(stress_out.delt if stress_out else 0.4),
                "Npt":       str(stress_out.Npt  if stress_out else 200),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)
        else:
            raise ValueError(f"Неподдерживаемый тип задачи: {task_type}")

        self._render_template(template_name, replacements, edp_path)
        logger.info(f"Скрипт {task_type.value} (одиночная) сохранён: {edp_path}")


    def _generate_assembly_freefem_code(
            self, sim_id: int, sim_dir: str, edp_path: str,
            outer_blade_id: int, inner_blade_id: int
    ):
        sim = self.session.get(Simulation, sim_id)
        ic_id = sim.initial_conditions_id
        task_type = TaskType(sim.task_type)

        outer_coeffs = self._get_blade_legendre_coeffs(outer_blade_id)
        inner_coeffs = self._get_blade_legendre_coeffs(inner_blade_id)

        # FreeFEM читает все коэффициенты через >> из одного файла подряд:
        # coeffsUp(0..9), coeffsLow(0..9), coeffsUp2(0..9), coeffsLow2(0..9)
        # Записываем в десятичном формате (не e-нотация) через пробел
        coeffs_csv = os.path.join(sim_dir, "out_L.csv")
        def fmt(v): return f"{float(v):.15f}"
        with open(coeffs_csv, 'w', encoding='utf-8') as f:
            f.write(" ".join(fmt(c.upper_value) for c in outer_coeffs) + "\n")
            f.write(" ".join(fmt(c.lower_value) for c in outer_coeffs) + "\n")
            f.write(" ".join(fmt(c.upper_value) for c in inner_coeffs) + "\n")
            f.write(" ".join(fmt(c.lower_value) for c in inner_coeffs) + "\n")

        chord = self.session.scalar(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id))
        constr = self.session.scalar(
            select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        boundary = self.session.scalar(
            select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))

        chord_outer = float(chord.value) if chord else 1.0
        outer_source_chord = self._get_profile_source_chord(outer_blade_id)
        inner_source_chord = self._get_profile_source_chord(inner_blade_id)
        if outer_source_chord and inner_source_chord:
            chord_inner = chord_outer * inner_source_chord / outer_source_chord
        else:
            chord_inner = chord_outer * (9.0 / 21.7)
        if chord_inner <= 0 or chord_inner >= chord_outer:
            chord_inner = chord_outer * (9.0 / 21.7)

        S1 = int(boundary.value) if boundary else 100
        S2 = S1 + 1
        NC = constr.NC if constr and constr.NC > 0 else 50
        NSp = constr.NSp if constr and constr.NSp > 0 else 50
        NSm = constr.NSm if constr and constr.NSm > 0 else 50
        NSpm = constr.NSpm if constr and constr.NSpm > 0 else 20

        replacements = {
            "Chord1": str(chord_outer),
            "Chord2": str(chord_inner),
            "S1": str(S1),
            "S2": str(S2),
            "NC": str(NC),
            "NSp": str(NSp),
            "NSm": str(NSm),
            "NSpm": str(NSpm),
        }

        if task_type == TaskType.THERMAL_FIELD:
            template_name = "thermal_field_assembly.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp   = self.session.scalar(select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            stress_out  = self.session.scalar(select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
            replacements.update({
                "Time":      str(time_params.time  if time_params and time_params.time  else 0.1),
                "dt":        str(time_params.dt    if time_params else 0.05),
                "Nplot":     str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value   if init_temp else 250),
                "a_steel":   "12.54",
                "a_air":     "21.02",
                "delt":      str(stress_out.delt if stress_out else 0.4),
                "Npt":       str(stress_out.Npt  if stress_out else 200),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        elif task_type == TaskType.THERMAL_STRESS:
            template_name = "thermal_stress_assembly.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp   = self.session.scalar(select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            elastic     = self.session.scalar(select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
            stress_out  = self.session.scalar(select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
            material    = sim.materials[0].material if sim.materials else None
            ei_value    = None
            if elastic and material:
                ei_value = self.session.scalar(
                    select(ElValue).where(
                        ElValue.elasticity_parameters_id == elastic.elasticity_parameters_id,
                        ElValue.material_id == material.material_id
                    )
                )
            E_steel = ei_value.value if ei_value else 2.1e5
            replacements.update({
                "Time":      str(time_params.time  if time_params and time_params.time  else 0.1),
                "dt":        str(time_params.dt    if time_params else 0.05),
                "Nplot":     str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value   if init_temp else 250),
                "a_steel":   "12.54",
                "a_air":     "21.02",
                "b":         str(elastic.b   if elastic else 1.0),
                "nu":        str(elastic.nu  if elastic else 0.28),
                "KLT":       str(elastic.KLT if elastic else 10.5e-6),
                "E_steel":   str(E_steel),
                "delt":      str(stress_out.delt if stress_out else 0.4),
                "Npt":       str(stress_out.Npt  if stress_out else 200),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)
        else:
            raise ValueError(f"Для сборки поддерживаются только задачи thermal_field и thermal_stress")

        self._render_template(template_name, replacements, edp_path)
        logger.info(f"Скрипт {task_type.value} (сборка) сохранён: {edp_path}")

    def _get_profile_source_chord(self, blade_id: int):
        coords = self.session.scalars(
            select(ProfileCoordinate).where(ProfileCoordinate.blade_id == blade_id)
        ).all()
        xs = [float(c.x) for c in coords]
        if not xs:
            return None
        chord = max(xs) - min(xs)
        return chord if chord > 0 else None

    def _render_template(self, template_name: str, replacements: dict, output_path: str):
        template_path = Path(__file__).parent.parent / "templates" / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Шаблон {template_name} не найден в templates/")
        with open(template_path, 'r', encoding='utf-8') as f:
            script = f.read()
        for key, val in replacements.items():
            script = script.replace(f"{{{{{key}}}}}", str(val))
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(script)

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

    def delete_simulation(self, sim_id: int):
        sim = self.session.get(Simulation, sim_id)
        if not sim:
            raise ValueError("Симуляция не найдена")
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        if os.path.exists(sim_dir):
            import shutil
            shutil.rmtree(sim_dir)
        self.session.delete(sim)

    def delete_failed_simulations(self) -> int:
        stmt = select(Simulation).where(Simulation.status == 'failed')
        failed_sims = self.session.scalars(stmt).all()
        count = 0
        for sim in failed_sims:
            sim_dir = os.path.join(self.upload_dir, f"sim_{sim.simulation_id}")
            if os.path.exists(sim_dir):
                import shutil
                shutil.rmtree(sim_dir)
            self.session.delete(sim)
            count += 1
        return count

    def generate_plots(self, sim_id: int) -> dict:
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        from numpy.linalg import eig
        from PIL import Image
        import glob
        import os

        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        sim = self.session.get(Simulation, sim_id)
        if not sim:
            return {"error": "Симуляция не найдена"}

        task_type = sim.task_type
        plots = {}

        def mizes2(tensor):
            eig_vals, _ = eig(tensor)
            miz = np.sqrt(((eig_vals[0] - eig_vals[1]) ** 2) / 2)
            return np.hstack((eig_vals, miz))

        def calc_eigMiz(data_select):
            eigMiz = np.zeros((np.shape(data_select)[0], 3))
            for i in range(np.shape(data_select)[0]):
                T_mat = np.array([[data_select[i, 0], data_select[i, 1]],
                                  [data_select[i, 1], data_select[i, 2]]])
                eigMiz[i] = mizes2(T_mat)
            return eigMiz

        # ================= ЗАДАЧА 1: ГАЗОДИНАМИКА =================
        if task_type == 'gas_dynamics':
            eps_files = sorted(glob.glob(os.path.join(sim_dir, "plot_*.eps")))
            titles = {
                'plot_1': 'Сетка',
                'plot_2': 'Функция ψ',
                'plot_3': 'Поле скорости',
                'plot_4': 'Давление (p)',
                'plot_5': 'Давление (изолинии)'
            }
            for eps in eps_files:
                base = os.path.basename(eps).replace('.eps', '')
                if base in titles:
                    try:
                        img = Image.open(eps)
                        png_file = eps.replace('.eps', '.png')
                        img.save(png_file, 'PNG')
                        with open(png_file, 'rb') as f:
                            plots[titles[base]] = base64.b64encode(f.read()).decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Не удалось конвертировать {eps}: {e}")

            temp_final = os.path.join(sim_dir, "temp_final.eps")
            if os.path.exists(temp_final):
                try:
                    img = Image.open(temp_final)
                    png_file = temp_final.replace('.eps', '.png')
                    img.save(png_file, 'PNG')
                    with open(png_file, 'rb') as f:
                        plots['Температурное поле в конце моделирования'] = base64.b64encode(f.read()).decode('utf-8')
                except Exception as e:
                    logger.warning(f"Не удалось конвертировать temp_final.eps: {e}")

            temp_eps = sorted(glob.glob(os.path.join(sim_dir, "temp_*.eps")))
            temp_eps = [f for f in temp_eps if not f.endswith('temp_final.eps')]
            if temp_eps:
                frames = []
                for eps in temp_eps:
                    try:
                        img = Image.open(eps)
                        frames.append(img)
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить кадр {eps}: {e}")
                if frames:
                    gif_path = os.path.join(sim_dir, "temperature_animation.gif")
                    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                                   duration=200, loop=0, format='GIF')
                    with open(gif_path, 'rb') as f:
                        plots['Анимация температурного поля'] = base64.b64encode(f.read()).decode('utf-8')

        # ================= ЗАДАЧА 2: ТЕПЛОВОЕ ПОЛЕ =================
        elif task_type == 'thermal_field':
            # Единственный график: диаграмма распределения температуры по внешнему контуру (TFout.csv)
            tf_path = os.path.join(sim_dir, "TFout.csv")
            logger.info(f"[task2] Ищем TFout.csv: {tf_path}, exists={os.path.exists(tf_path)}")
            if os.path.exists(tf_path):
                try:
                    data = np.loadtxt(tf_path)
                    if data.ndim == 1:
                        data = data.reshape(1, -1)
                    # Столбцы: xdc  ydUp  T(верх)  ydLw  T(низ)
                    x_coords = data[:, 0]
                    T_up = data[:, 2]
                    T_lw = data[:, 4]
                    plt.figure(figsize=(8, 5))
                    plt.plot(x_coords, T_up, 'rx', label='Спинка', markersize=5)
                    plt.plot(x_coords, T_lw, 'bx', label='Корытце', markersize=5)
                    plt.xlabel('X, мм')
                    plt.ylabel('Температура, °C')
                    plt.title('Распределение температуры по внешнему контуру лопатки после охлаждения')
                    plt.legend()
                    plt.grid(True, alpha=0.3)
                    buf = BytesIO()
                    plt.savefig(buf, format='png', dpi=100)
                    buf.seek(0)
                    plots['Распределение температуры по контуру'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                    plt.close()
                    logger.info(f"[task2] График температуры по контуру построен успешно")
                except Exception as e:
                    logger.error(f"[task2] Ошибка при построении графика температуры: {e}", exc_info=True)
            else:
                logger.warning(f"[task2] TFout.csv не найден — возможно FreeFEM не завершил запись или шаблон не обновлён")

        # ================= ЗАДАЧА 3: ТЕРМОУПРУГОСТЬ =================
        elif task_type == 'thermal_stress':
            # 1. Профиль лопатки (Profout.csv)
            prof_path = os.path.join(sim_dir, "Profout.csv")
            if os.path.exists(prof_path):
                try:
                    data = np.loadtxt(prof_path)
                    plt.figure(figsize=(8, 5))
                    plt.plot(data[:, 0], data[:, 1], 'b-', label='Спинка (исх.)')
                    plt.plot(data[:, 0], data[:, 2], 'b-', label='Корытце (исх.)')
                    plt.plot(data[:, 3], data[:, 4], 'r-', label='Спинка (деф.)')
                    plt.plot(data[:, 3], data[:, 5], 'r-', label='Корытце (деф.)')
                    plt.xlabel('X, мм')
                    plt.ylabel('Y, мм')
                    plt.title('Профиль лопатки')
                    plt.legend(loc='best')
                    plt.grid(True, alpha=0.3)
                    buf = BytesIO()
                    plt.savefig(buf, format='png', dpi=100)
                    buf.seek(0)
                    plots['Профиль лопатки'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                    plt.close()
                except Exception as e:
                    logger.error(f"Ошибка при построении профиля лопатки: {e}")

            # 2. Деформации Мизеса (TEpsout.csv)
            eps_path = os.path.join(sim_dir, "TEpsout.csv")
            if os.path.exists(eps_path):
                try:
                    data = np.loadtxt(eps_path)
                    x_coords = data[:, 0]

                    eps_up = calc_eigMiz(data[:, 3:6])[:, 2] * 100
                    eps_lw = calc_eigMiz(data[:, 8:11])[:, 2] * 100

                    plt.figure(figsize=(8, 5))
                    plt.plot(x_coords, eps_up, 'ro-', label='Спинка', markersize=4)
                    plt.plot(x_coords, eps_lw, 'bo-', label='Корытце', markersize=4)
                    plt.xlabel('X, мм')
                    plt.ylabel('Деформация, %')
                    plt.title('Эквивалентная деформация Мизеса по контуру лопатки')
                    plt.legend()
                    plt.grid(True, alpha=0.3)
                    buf = BytesIO()
                    plt.savefig(buf, format='png', dpi=100)
                    buf.seek(0)
                    plots['Деформация Мизеса'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                    plt.close()
                except Exception as e:
                    logger.error(f"Ошибка при обработке TEpsout.csv: {e}")

            # 3. Напряжения (TSout.csv)
            stress_path = os.path.join(sim_dir, "TSout.csv")
            if os.path.exists(stress_path):
                try:
                    data = np.loadtxt(stress_path)
                    x_coords = data[:, 0]
                    sig_up = calc_eigMiz(data[:, 3:6])[:, 2]
                    sig_lw = calc_eigMiz(data[:, 8:11])[:, 2]

                    plt.figure(figsize=(8, 5))
                    plt.plot(x_coords, sig_up, 'ro-', label='Спинка', markersize=4)
                    plt.plot(x_coords, sig_lw, 'bo-', label='Корытце', markersize=4)
                    plt.xlabel('X, мм')
                    plt.ylabel('Напряжение, МПа')
                    plt.title('Эквивалентное напряжение Мизеса')
                    plt.legend()
                    plt.grid(True, alpha=0.3)
                    buf = BytesIO()
                    plt.savefig(buf, format='png', dpi=100)
                    buf.seek(0)
                    plots['Напряжение Мизеса'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                    plt.close()
                except Exception as e:
                    logger.error(f"Ошибка при обработке TSout.csv: {e}")

            # 4. Компоненты напряжений из eps (sig1, sig2, sig12) — в plots/
            for sig_file, sig_name in [("sig1.eps", "Напряжение σ₁"), ("sig2.eps", "Напряжение σ₂"), ("sig12.eps", "Напряжение σ₁₂")]:
                eps = os.path.join(sim_dir, "plots", sig_file)
                if os.path.exists(eps):
                    try:
                        img = Image.open(eps)
                        png_file = eps.replace('.eps', '.png')
                        img.save(png_file, 'PNG')
                        with open(png_file, 'rb') as f:
                            plots[sig_name] = base64.b64encode(f.read()).decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Не удалось конвертировать {eps}: {e}")

        return plots
