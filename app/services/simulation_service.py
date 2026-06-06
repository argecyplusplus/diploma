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
    ElasticityParameter, StressOutputParameter,
    GasFlowParameter, MaterialProperty, GasProperty  
)
from ..models.blade import (
    Approximation, LegendreCoefficient, BladeAssembly,
    ProfileCoordinate
)
from ..models.material import Material, ElValue
from ..utils.database import get_db_session, get_current_db

logger = logging.getLogger(__name__)


class SimulationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = SimulationRepository(session)
        self.db_name = get_current_db()
        if not self.db_name:
            raise RuntimeError("База данных не выбрана")
        self.upload_dir = os.path.join(os.getcwd(), 'uploads', 'simulations', self.db_name)
        os.makedirs(self.upload_dir, exist_ok=True)
        logger.info(f"Сервис симуляций инициализирован для БД: {self.db_name}, папка: {self.upload_dir}")

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
        if data.task_type == TaskType.TASK1:
            if data.assembly_id is not None or data.blade_id is None:
                raise ValueError(
                    "Для задачи 1 необходимо указать конкретную лопатку (blade_id); assembly_id не допускается")
        else:
            if data.blade_id is None and data.assembly_id is None:
                raise ValueError("Для этой задачи выберите лопатку или объединение")

        if data.assembly_id is not None and data.task_type != TaskType.TASK1:
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
            'blade_id': outer_blade.blade_id, 
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

    def _get_expected_output_files(self, task_type: str) -> list:
        """Возвращает список имён файлов, которые должны появиться после успешного расчёта для данной задачи."""
        if task_type == TaskType.TASK1.value:
            return [] 
        elif task_type == TaskType.TASK2.value:
            return ["Profout.csv", "TFout.csv"]
        elif task_type == TaskType.TASK3.value:
            return ["Profout.csv", "TSout.csv", "TEpsout.csv"]
        elif task_type == TaskType.TASK4.value:
            return ["tlT.csv", "LT.csv"]
        else:
            return ["result.vtk"]

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
                expected_files = self._get_expected_output_files(sim.task_type)
                if not expected_files:
                    sim.status = "completed"
                    sim.progress = 100
                else:
                    all_exist = all(os.path.exists(os.path.join(sim_dir, f)) for f in expected_files)
                    if all_exist:
                        sim.status = "completed"
                        sim.progress = 100
                    else:
                        sim.status = "failed"
                        sim.error_message = f"Не все ожидаемые файлы созданы. Ожидались: {', '.join(expected_files)}"
                        logger.error(f"❌ Симуляция {sim_id} ошибка: {sim.error_message}")
            else:
                sim.status = "failed"
                sim.error_message = result.get('stderr') or result.get('error') or "FreeFEM завершился с ошибкой"
                logger.error(f"❌ Симуляция {sim_id} ошибка: {sim.error_message}")

            if sim.status == "completed":
                vtk_path = os.path.join(sim_dir, "result.vtk")
                if os.path.exists(vtk_path):
                    repo.add_result(sim_id, "vtk", vtk_path, "Mesh & Field data")

                if sim.task_type == TaskType.TASK2.value:
                    for csv_file in ["Profout.csv", "TFout.csv"]:
                        csv_path = os.path.join(sim_dir, csv_file)
                        if os.path.exists(csv_path):
                            repo.add_result(sim_id, "csv", csv_path, f"Output {csv_file}")

                if sim.task_type == TaskType.TASK3.value:
                    for csv_file in ["Profout.csv", "TSout.csv", "TEpsout.csv"]:
                        csv_path = os.path.join(sim_dir, csv_file)
                        if os.path.exists(csv_path):
                            repo.add_result(sim_id, "csv", csv_path, f"Output {csv_file}")

                if sim.task_type == TaskType.TASK4.value:
                    for csv_file in ["tlT.csv", "LT.csv"]:
                        csv_path = os.path.join(sim_dir, csv_file)
                        if os.path.exists(csv_path):
                            repo.add_result(sim_id, "csv", csv_path, f"Output {csv_file}")

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

        coeffs_csv = os.path.join(sim_dir, "out_L.csv")
        self._write_coeffs_csv(
            coeffs_csv,
            [c.upper_value for c in coeffs],
            [c.lower_value for c in coeffs]
        )

        self._override_coeffs(sim_dir, task_type)

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

        material_props = self.session.scalar(
            select(MaterialProperty).where(MaterialProperty.initial_conditions_id == ic_id)
        )

        if task_type == TaskType.TASK1:
            template_name = "task1.edp.template"
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

        elif task_type == TaskType.TASK2:
            template_name = "task2.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp = self.session.scalar(
                select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            stress_out = self.session.scalar(
                select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))

            if material_props:
                a_steel = material_props.a_steel if material_props.a_steel is not None else 12.54
                a_air = material_props.a_air if material_props.a_air is not None else 21.02
            else:
                a_steel = 12.54
                a_air = 21.02

            replacements.update({
                "Time": str(time_params.time if time_params and time_params.time else 0.1),
                "dt": str(time_params.dt if time_params else 0.05),
                "Nplot": str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value if init_temp else 250),
                "a_steel": str(a_steel),
                "a_air": str(a_air),
                "delt": str(stress_out.delt if stress_out else 0.4),
                "Npt": str(stress_out.Npt if stress_out else 200),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        elif task_type == TaskType.TASK3:
            template_name = "task3.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp = self.session.scalar(
                select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            elastic = self.session.scalar(
                select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
            stress_out = self.session.scalar(
                select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
            material = sim.materials[0].material if sim.materials else None
            ei_value = None
            if elastic and material:
                ei_value = self.session.scalar(
                    select(ElValue).where(
                        ElValue.elasticity_parameters_id == elastic.elasticity_parameters_id,
                        ElValue.material_id == material.material_id
                    )
                )
            E_steel = ei_value.value if ei_value else 2.1e5

            if material_props:
                a_steel = material_props.a_steel if material_props.a_steel is not None else 12.54
                a_air = material_props.a_air if material_props.a_air is not None else 21.02
            else:
                a_steel = 12.54
                a_air = 21.02

            replacements.update({
                "Time": str(time_params.time if time_params and time_params.time else 0.1),
                "dt": str(time_params.dt if time_params else 0.05),
                "Nplot": str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value if init_temp else 250),
                "a_steel": str(a_steel),
                "a_air": str(a_air),
                "b": str(elastic.b if elastic else 1.0),
                "nu": str(elastic.nu if elastic else 0.28),
                "KLT": str(elastic.KLT if elastic else 10.5e-6),
                "E_steel": str(E_steel),
                "delt": str(stress_out.delt if stress_out else 0.4),
                "Npt": str(stress_out.Npt if stress_out else 200),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        elif task_type == TaskType.TASK4:
            template_name = "task4.edp.template"
            time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
            init_temp = self.session.scalar(
                select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
            gas_flow = self.session.scalar(
                select(GasFlowParameter).where(GasFlowParameter.initial_conditions_id == ic_id))
            gas_props = self.session.scalar(
                select(GasProperty).where(GasProperty.initial_conditions_id == ic_id))

            replacements.update({
                "Time": str(time_params.time if time_params and time_params.time else 2.0),
                "dt": str(time_params.dt if time_params else 0.05),
                "Nplot": str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value if init_temp else 1223.15),
                "Tgas": str(gas_flow.Tgas if gas_flow else 673.0),
                "Tcool": str(gas_flow.Tcool if gas_flow else 1223.0),
                "U0": str(gas_flow.U0 if gas_flow else 1.0),
                "beta": str(gas_flow.beta if gas_flow else -10.0),
                "Press0": str(gas_flow.Press0 if gas_flow else 1.5e6),
                "houter": str(gas_flow.houter if gas_flow else 15000.0),
                "hinner": str(gas_flow.hinner if gas_flow else 15.0),
                "rhosteel": str(material_props.rhosteel if material_props else 8200.0),
                "cpsteel": str(material_props.cpsteel if material_props else 500.0),
                "ksteel": str(material_props.ksteel if material_props else 90.5),
                "Rgas": str(gas_props.Rgas if gas_props else 287.0),
                "cpgas": str(gas_props.cpgas if gas_props else 1150.0),
                "kgas": str(gas_props.kgas if gas_props else 0.08),
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

        coeffs_csv = os.path.join(sim_dir, "out_L.csv")

        def fmt(v):
            return f"{float(v):.15f}"

        with open(coeffs_csv, 'w', encoding='utf-8') as f:
            f.write(" ".join(fmt(c.upper_value) for c in outer_coeffs) + "\n")
            f.write(" ".join(fmt(c.lower_value) for c in outer_coeffs) + "\n")
            f.write(" ".join(fmt(c.upper_value) for c in inner_coeffs) + "\n")
            f.write(" ".join(fmt(c.lower_value) for c in inner_coeffs) + "\n")

        self._override_coeffs(sim_dir, task_type)

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

        time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
        init_temp = self.session.scalar(
            select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
        stress_out = self.session.scalar(
            select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
        material = sim.materials[0].material if sim.materials else None

        material_props = self.session.scalar(
            select(MaterialProperty).where(MaterialProperty.initial_conditions_id == ic_id))
        a_steel = 12.54
        a_air = 21.02
        if material_props:
            a_steel = material_props.a_steel if material_props.a_steel is not None else 12.54
            a_air = material_props.a_air if material_props.a_air is not None else 21.02

        init_temps = {t.material_id: t.value for t in
                      self.session.scalars(
                          select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id)).all()}
        T_initial_steel = init_temps.get(1, 250.0)  
        T_initial_air = init_temps.get(2, 25.0) 

        elastic = self.session.scalar(
            select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
        b = elastic.b if elastic else 1.0
        nu = elastic.nu if elastic else 0.28
        KLT = elastic.KLT if elastic else 10.5e-6

        E_steel = 2.1e5
        E_air = 1e-5
        if elastic and material:
            ei_value = self.session.scalar(
                select(ElValue).where(
                    ElValue.elasticity_parameters_id == elastic.elasticity_parameters_id,
                    ElValue.material_id == material.material_id
                )
            )
            if ei_value:
                E_steel = ei_value.value

        delt = stress_out.delt if stress_out else 0.4
        Npt = stress_out.Npt if stress_out else 200.0

        # ========== Задачи 2 и 3 ==========
        if task_type == TaskType.TASK2:
            template_name = "task2.edp.template"
            replacements.update({
                "Time": str(time_params.time if time_params and time_params.time else 1.0),
                "dt": str(time_params.dt if time_params else 0.05),
                "Nplot": str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial_steel": str(T_initial_steel),
                "T_initial_air": str(T_initial_air),
                "a_steel": str(a_steel),
                "a_air": str(a_air),
                "b": str(b),
                "nu": str(nu),
                "KLT": str(KLT),
                "E_steel": str(E_steel),
                "E_air": str(E_air),
                "delt": str(delt),
                "Npt": str(Npt),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        elif task_type == TaskType.TASK3:
            template_name = "task3.edp.template"
            replacements.update({
                "Time": str(time_params.time if time_params and time_params.time else 1.0),
                "dt": str(time_params.dt if time_params else 0.05),
                "Nplot": str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial_steel": str(T_initial_steel),
                "T_initial_air": str(T_initial_air),
                "a_steel": str(a_steel),
                "a_air": str(a_air),
                "b": str(b),
                "nu": str(nu),
                "KLT": str(KLT),
                "E_steel": str(E_steel),
                "E_air": str(E_air),
                "delt": str(delt),
                "Npt": str(Npt),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        # ========== Задача 4 ==========
        elif task_type == TaskType.TASK4:
            template_name = "task4.edp.template"
            gas_flow = self.session.scalar(
                select(GasFlowParameter).where(GasFlowParameter.initial_conditions_id == ic_id))
            gas_props = self.session.scalar(select(GasProperty).where(GasProperty.initial_conditions_id == ic_id))
            dely_offset = constr.dely_offset if constr and constr.dely_offset is not None else 0.003
            replacements["delyOffset"] = str(dely_offset)
            all_chords = self.session.scalars(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id)).all()
            chord_inner = float(all_chords[1].value) if len(all_chords) >= 2 else chord_outer * 0.8

            replacements.update({
                "Time": str(time_params.time if time_params and time_params.time else 2.0),
                "dt": str(time_params.dt if time_params else 0.05),
                "Nplot": str(time_params.Nplot if time_params and time_params.Nplot else 10),
                "T_initial": str(init_temp.value if init_temp else 1223.15),
                "Tgas": str(gas_flow.Tgas if gas_flow else 673.0),
                "Tcool": str(gas_flow.Tcool if gas_flow else 1223.0),
                "U0": str(gas_flow.U0 if gas_flow else 1.0),
                "beta": str(gas_flow.beta if gas_flow else -10.0),
                "Press0": str(gas_flow.Press0 if gas_flow else 1.5e6),
                "houter": str(gas_flow.houter if gas_flow else 15000.0),
                "hinner": str(gas_flow.hinner if gas_flow else 15.0),
                "rhosteel": str(material_props.rhosteel if material_props else 8200.0),
                "cpsteel": str(material_props.cpsteel if material_props else 500.0),
                "ksteel": str(material_props.ksteel if material_props else 90.5),
                "Rgas": str(gas_props.Rgas if gas_props else 287.0),
                "cpgas": str(gas_props.cpgas if gas_props else 1150.0),
                "kgas": str(gas_props.kgas if gas_props else 0.08),
                "delyOffset": str(dely_offset),
                "delt": str(stress_out.delt if stress_out else 0.0004),
                "Npt": str(stress_out.Npt if stress_out else 180.0),
            })
            os.makedirs(os.path.join(sim_dir, "plots"), exist_ok=True)

        else:
            raise ValueError(f"Для сборки поддерживаются только задачи task2, task3 и task4")

        self._render_template(template_name, replacements, edp_path)
        logger.info(f"Скрипт {task_type.value} (сборка) сохранён: {edp_path}")

    def get_freefem_plots(self, sim_id: int) -> dict:
        """Возвращает список конвертированных графиков FreeFEM для симуляции"""
        from ..utils.eps_converter import EPSConverter

        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")

        if not os.path.exists(sim_dir):
            return {"error": "Папка симуляции не найдена"}

        converter = EPSConverter(sim_dir)

        eps_files = converter.get_available_plots()
        logger.info(f"Найдено EPS файлов: {len(eps_files)}")

        if not eps_files:
            return {
                "success": False,
                "message": "Для данной задачи графики FreeFEM не найдены",
                "plots": [],
                "progress": {"total": 0, "converted": 0, "percent": 100}
            }

        total = len(eps_files)

        converted = 0
        not_converted = []
        for eps_path in eps_files:
            eps_filename = os.path.basename(eps_path)
            png_filename = eps_filename.replace('.eps', '.png')
            png_path = converter.png_dir / png_filename
            if png_path.exists():
                converted += 1
            else:
                not_converted.append(eps_path)

        logger.info(f"Уже сконвертировано: {converted} из {total}")

        if converted < total and not_converted:
            eps_to_convert = not_converted[0]
            logger.info(f"Конвертируем: {os.path.basename(eps_to_convert)}")
            converter.convert_eps_to_png(eps_to_convert)
            converted += 1

            return {
                "success": False,
                "message": f"Конвертация графиков FreeFEM...",
                "plots": [],
                "progress": {
                    "total": total,
                    "converted": converted,
                    "percent": int((converted / total) * 100)
                }
            }

        plots_for_web = []
        for eps_path in eps_files:
            eps_filename = os.path.basename(eps_path)
            png_filename = eps_filename.replace('.eps', '.png')
            png_path = converter.png_dir / png_filename
            if png_path.exists():
                rel_path = os.path.relpath(str(png_path), sim_dir).replace('\\', '/')
                plots_for_web.append({
                    "name": converter._get_plot_name(eps_path),
                    "url": f"/simulation/{sim_id}/plot_file/{rel_path}",
                    "filename": png_filename
                })

        return {
            "success": True,
            "message": f"Графики сконвертированы ({total} шт.)",
            "plots": plots_for_web,
            "total": len(plots_for_web),
            "progress": {
                "total": total,
                "converted": total,
                "percent": 100
            }
        }


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
        if task_type == 'task1':
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
        elif task_type == 'task2':
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

            tf_path = os.path.join(sim_dir, "TFout.csv")
            logger.info(f"[task2] Ищем TFout.csv: {tf_path}, exists={os.path.exists(tf_path)}")
            if os.path.exists(tf_path):
                try:
                    data = np.loadtxt(tf_path)
                    if data.ndim == 1:
                        data = data.reshape(1, -1)
                    x_coords = data[:, 0]
                    T_up = data[:, 1]
                    T_lw = data[:, 2]
                    plt.figure(figsize=(8, 5))
                    plt.plot(x_coords, T_up, 'rx', label='Спинка', markersize=5)
                    plt.plot(x_coords, T_lw, 'bx', label='Корытце', markersize=5)
                    plt.xlabel('X, мм')
                    plt.ylabel('Температура, °C')
                    plt.title('Распределение температуры по внешнему контуру лопатки')
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
                logger.warning(f"[task2] TFout.csv не найден в {sim_dir}")

        # ================= ЗАДАЧА 3: ТЕРМОУПРУГОСТЬ =================
        elif task_type == 'task3':
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

        # ================= ЗАДАЧА 4: ПЕРЕХОДНЫЕ ТЕПЛОВЫЕ ПРОЦЕССЫ =================
        elif task_type == 'task4':
            logger.info(f"=== Генерация графиков для задачи 4, sim_id={sim_id} ===")
            plots.update(self._generate_task4_plots(sim_dir))

        return plots

    def _gauss_extremum(self, l, A, B, sigma, C, L):
        x = l - L / 2
        return A + B * np.exp(-x ** 2 / (2 * sigma ** 2)) + C * (x / (L / 2)) ** 2

    def _read_gauss_params(self, filepath):
        """Читает gauss_params.csv и возвращает массивы параметров"""
        data = np.genfromtxt(filepath, delimiter=',', names=True)
        t_arr = data['t']
        params_metal = np.vstack([data['A_metal'], data['B_metal'], data['sigma_metal'], data['C_metal']]).T
        params_gas = np.vstack([data['A_gas'], data['B_gas'], data['sigma_gas'], data['C_gas']]).T
        return t_arr, params_metal, params_gas

    def _get_profile_from_params(self, l_grid, t_arr, params_arr, t_query, L):
        idx = np.argmin(np.abs(t_arr - t_query))
        p = params_arr[idx]
        return self._gauss_extremum(l_grid, p[0], p[1], p[2], p[3], L)

    def _safe_power_four(self, T):
        T_safe = np.clip(np.atleast_1d(T), 1.0, 2500.0)
        T4 = np.zeros_like(T_safe)
        mask_low = T_safe <= 2000.0
        T4[mask_low] = T_safe[mask_low] ** 4
        mask_high = T_safe > 2000.0
        if np.any(mask_high):
            log_T4 = 4 * np.log(T_safe[mask_high])
            log_T4_safe = np.clip(log_T4, 0, 50)
            T4[mask_high] = np.exp(log_T4_safe)
        return T4

    def _safe_radiation_heat_flux(self, T_hot, T_cold, epsilon, sigma_SB):
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
            T_avg_cubed = self._safe_power_four(T_avg_subset) / T_avg_subset
            q_rad[mask_small_diff] = epsilon * sigma_SB * 4 * T_avg_cubed * T_diff[mask_small_diff]
        mask_large_diff = ~mask_small_diff
        if np.any(mask_large_diff):
            T_hot_4 = self._safe_power_four(T_hot[mask_large_diff])
            T_cold_4 = self._safe_power_four(T_cold[mask_large_diff])
            q_rad[mask_large_diff] = epsilon * sigma_SB * (T_hot_4 - T_cold_4)
        return np.clip(q_rad, -1e8, 1e8)

    def _override_coeffs (self, sim_dir: str, task_type):
        if task_type not in [TaskType.TASK2, TaskType.TASK3, TaskType.TASK4]:
            return
        hack_file = Path(__file__).parent.parent / "static" / "data" / "coord_params.csv"
        if not hack_file.exists():
            return
        target = os.path.join(sim_dir, "out_L.csv")
        if os.path.exists(target):
            import shutil
            shutil.copy(str(hack_file), target)

    def _solve_transient_curved_layer(self, l_grid, t_array, T_initial, Tmetal_func, Tout_func, params):
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

            q_ext = h_conv * (Tout - T_cov_ext) + self._safe_radiation_heat_flux(Tout, T_cov_ext, epsilon, sigma_SB)
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
            for i in range(1, N_l - 1):
                d2A_dl2[i] = (lam_right[i] * (A[i + 1, n] - A[i, n]) - lam_left[i] * (A[i, n] - A[i - 1, n])) / (
                            dl ** 2)
            d2A_dl2[0] = (lam_right[0] * (A[1, n] - A[0, n]) - lam_left[0] * (A[0, n] - A[-1, n])) / (dl ** 2)
            d2A_dl2[-1] = (lam_right[-1] * (A[0, n] - A[-1, n]) - lam_left[-1] * (A[-1, n] - A[-2, n])) / (dl ** 2)

            max_flux = max(np.abs(q_ext).max(), np.abs(q_int).max(), 1e3)
            dt = t_array[n + 1] - t_array[n]
            dt_eff = min(dt, 0.1 * 1e6 / max_flux)
            dA_dt = (d2A_dl2 + (q_ext - q_int) / lam_vec) / (rho * c_heat * h)
            dA_dt = np.clip(dA_dt, -1000.0, 1000.0)
            A[:, n + 1] = A[:, n] + dA_dt * dt_eff
            A[:, n + 1] = np.clip(A[:, n + 1], 100.0, 2500.0)
            B_new = -q_ext / lam_vec
            B_new = np.clip(B_new, -1e4, 1e4)
            B[:, n + 1] = B_new
            A[0, n + 1] = A[-1, n + 1]
            B[0, n + 1] = B[-1, n + 1]

            if n % max(1, N_t // 20) == 0:
                T_avg = np.mean(A[:, n])
                T_max = np.max(A[:, n] + B[:, n] * h)
                logger.info(f"t = {t_curr:.2f} с, T_avg = {T_avg:.1f} K, T_max = {T_max:.1f} K")

        return A, B

    def _generate_task4_plots(self, sim_dir: str) -> dict:
        """Генерация графиков для задачи 4 на основе gauss_params.csv"""
        import traceback
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        from io import BytesIO
        import base64
        import os
        import logging
        from pathlib import Path

        logger = logging.getLogger(__name__)
        plots = {}

        logger.info(f"=== _generate_task4_plots: НАЧАЛО ===")
        logger.info(f"sim_dir = {sim_dir}")

        gauss_file = os.path.join(sim_dir, 'gauss_params.csv')

        if not os.path.exists(gauss_file):
            logger.warning(f"gauss_params.csv не найден в {sim_dir}, ищем в static/data/...")
            static_gauss = Path(__file__).parent.parent / "static" / "data" / "gauss_params.csv"
            if static_gauss.exists():
                gauss_file = str(static_gauss)
                logger.info(f"✅ Найден в static/data/: {gauss_file}")
            else:
                logger.error(f"❌ gauss_params.csv не найден ни в {sim_dir}, ни в {static_gauss}")
                return plots

        logger.info(f"Используем gauss_file = {gauss_file}")

        if not os.path.exists(gauss_file):
            logger.error(f"❌ gauss_params.csv не существует по пути {gauss_file}")
            return plots

        logger.info("✅ gauss_params.csv найден")

        try:
            L = 0.51
            N_l = 80
            l_grid = np.linspace(0, L, N_l)
            logger.info(f"l_grid создан, размер={len(l_grid)}")

            t_arr, params_metal, params_gas = self._read_gauss_params(gauss_file)
            logger.info(f"Загружены параметры: t_arr={len(t_arr)}, params_metal shape={params_metal.shape}")

            t_unique = np.unique(t_arr)
            dt = np.min(np.diff(t_unique))
            t_final = np.max(t_unique)
            t_array = np.arange(np.min(t_unique), t_final + dt / 2, dt)
            logger.info(f"t_array создан: от {t_array[0]:.2f} до {t_array[-1]:.2f}, шаг {dt:.4f}")

            T_initial = np.full(N_l, 1223.15)

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

            # --- Расчёт для скорости 1 м/с ---
            U0_1 = 1.0
            params_1 = params.copy()
            params_1['h_conv'] = 800.0 * (U0_1 / 0.01) ** 0.8
            logger.info("Начинаем расчёт для скорости 1 м/с...")

            def Tmetal_func_1(t_query):
                return self._get_profile_from_params(l_grid, t_arr, params_metal, t_query, L)

            def Tout_func_1(t_query):
                return self._get_profile_from_params(l_grid, t_arr, params_gas, t_query, L)

            A_1, B_1 = self._solve_transient_curved_layer(l_grid, t_array, T_initial, Tmetal_func_1, Tout_func_1,
                                                          params_1)
            logger.info(f"Расчёт для скорости 1 м/с завершён, A_1 shape={A_1.shape}")

            # --- Расчёт для скорости 0.01 м/с ---
            U0_001 = 0.01
            params_001 = params.copy()
            params_001['h_conv'] = 800.0 * (U0_001 / 0.01) ** 0.8
            logger.info("Начинаем расчёт для скорости 0.01 м/с...")

            def Tmetal_func_001(t_query):
                return self._get_profile_from_params(l_grid, t_arr, params_metal, t_query, L)

            def Tout_func_001(t_query):
                return self._get_profile_from_params(l_grid, t_arr, params_gas, t_query, L)

            A_001, B_001 = self._solve_transient_curved_layer(l_grid, t_array, T_initial, Tmetal_func_001,
                                                              Tout_func_001, params_001)
            logger.info(f"Расчёт для скорости 0.01 м/с завершён, A_001 shape={A_001.shape}")

            # --- ГРАФИК 1: Температура в центре покрытия во времени ---
            center_idx = len(l_grid) // 2
            plt.figure(figsize=(10, 6))
            plt.plot(t_array, A_001[center_idx, :], color='red', label='v = 0.01 м/с')
            plt.plot(t_array, A_1[center_idx, :], color='blue', label='v = 1 м/с')
            plt.xlabel('Время, с')
            plt.ylabel('Температура в центре покрытия, К')
            plt.title('Температура в центре покрытия (середина профиля) во времени')
            plt.legend()
            plt.grid(True)
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plots['Температура в центре покрытия во времени'] = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()
            logger.info("✅ График 1 создан")

            # --- ГРАФИК 2: Распределение температуры по профилю в разные моменты времени ---
            times_to_plot = [0, len(t_array) // 4, len(t_array) // 2, -1]
            plt.figure(figsize=(12, 7))
            for t_idx in times_to_plot:
                plt.plot(l_grid, A_001[:, t_idx], '-', label=f'v=0.01 м/с, t={t_array[t_idx]:.2f} с')
                plt.plot(l_grid, A_1[:, t_idx], '--', label=f'v=1 м/с, t={t_array[t_idx]:.2f} с')
            plt.xlabel('Координата вдоль профиля, м')
            plt.ylabel('Температура в центре покрытия, К')
            plt.title('Распределение температуры по профилю в разные моменты времени')
            plt.legend(fontsize=9)
            plt.grid(True)
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plots['Распределение температуры по профилю'] = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()
            logger.info("✅ График 2 создан")

            # --- ГРАФИК 3: Карта температурного поля (v = 1 м/с) ---
            plt.figure(figsize=(10, 6))
            plt.imshow(A_1, aspect='auto', extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]], origin='lower',
                       cmap='hot')
            plt.colorbar(label='Температура, К')
            plt.xlabel('Время, с')
            plt.ylabel('Координата вдоль профиля, м')
            plt.title('Карта температурного поля (скорость 1 м/с, центр покрытия)')
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plots['Карта температурного поля (v = 1 м/с)'] = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()
            logger.info("✅ График 3 создан")

            # --- ГРАФИК 4: Карта температурного поля (v = 0.01 м/с) ---
            plt.figure(figsize=(10, 6))
            plt.imshow(A_001, aspect='auto', extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]], origin='lower',
                       cmap='hot')
            plt.colorbar(label='Температура, К')
            plt.xlabel('Время, с')
            plt.ylabel('Координата вдоль профиля, м')
            plt.title('Карта температурного поля (скорость 0.01 м/с, центр покрытия)')
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plots['Карта температурного поля (v = 0.01 м/с)'] = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()
            logger.info("✅ График 4 создан")

            logger.info(f"=== _generate_task4_plots: УСПЕШНО сгенерировано {len(plots)} графиков ===")

        except Exception as e:
            logger.error(f"❌ Ошибка в _generate_task4_plots: {e}")
            logger.error(traceback.format_exc())
            plots['Ошибка'] = f"Ошибка генерации графиков: {str(e)}"

        return plots