import os
import subprocess
import threading
import traceback
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..repositories.simulation_repository import SimulationRepository
from ..dto.simulation_dto import SimulationCreateRequest, InitialConditionCreateRequest, TaskType
from ..models.simulation import (
    Simulation, InitialCondition, ConstructionParameter, PotentialFlowParameter,
    BoundaryIdentifier, BladeChord, TimeParameter, InitialTemperature,
    ElasticityParameter, StressOutputParameter
)
from ..models.blade import Approximation, LegendreCoefficient, BladeAssembly
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

    def create_simulation(self, data: SimulationCreateRequest):
        if data.task_type == TaskType.GAS_DYNAMICS:
            if data.assembly_id is not None or data.blade_id is None:
                raise ValueError(
                    "Для газодинамики необходимо указать конкретную лопатку (blade_id), assembly_id не допускается")
        else:
            if data.blade_id is None and data.assembly_id is None:
                raise ValueError("Для этой задачи выберите лопатку или объединение")

        if data.assembly_id is not None and data.task_type != TaskType.GAS_DYNAMICS:
            assembly = self.session.get(BladeAssembly, data.assembly_id)
            if not assembly or not assembly.members:
                raise ValueError("Объединение не содержит лопаток")
            created_ids = []
            for member in assembly.members:
                blade = member.blade
                if not blade:
                    continue
                single_data = data.model_copy(deep=True)
                single_data.assembly_id = None
                single_data.blade_id = blade.blade_id
                sim_id = self._create_single_simulation(single_data)
                created_ids.append(sim_id)

            if not created_ids:
                raise ValueError("Не удалось создать симуляции")
            return created_ids[0]

        else:
            return self._create_single_simulation(data)

    def _create_single_simulation(self, data: SimulationCreateRequest) -> int:
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
        except Exception as e:
            logger.error(traceback.format_exc())
            sim.status = 'failed'
            sim.error_message = f"Ошибка генерации .edp: {str(e)}"
            self.session.commit()
            return sim_id

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
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            sim = session.get(Simulation, sim_id)
            if not sim:
                return
            sim.status = "running"
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

                # Сохраняем CSV-файлы для задачи 3 (тепло+напряжения)
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

        # --- Коэффициенты Лежандра ---
        approx = self.session.scalar(
            select(Approximation).where(Approximation.blade_id == sim.blade_id)
            .order_by(Approximation.approximation_id.desc()))
        if not approx:
            raise ValueError("Для выбранной лопатки не выполнена аппроксимация.")
        coeffs = self.session.scalars(
            select(LegendreCoefficient).where(LegendreCoefficient.approximation_id == approx.approximation_id)
            .order_by(LegendreCoefficient.legendre_coefficients_id)).all()
        if len(coeffs) < 10:
            raise ValueError("Недостаточно коэффициентов Лежандра (ожидается 10).")

        coeffs_csv = os.path.join(sim_dir, "out_L_blade.csv")
        with open(coeffs_csv, 'w', encoding='utf-8') as f:
            upper_vals = [f"{c.upper_value:.15e}" for c in coeffs]
            lower_vals = [f"{c.lower_value:.15e}" for c in coeffs]
            f.write(" ".join(upper_vals) + "\n")
            f.write(" ".join(lower_vals) + "\n")

        # --- Загрузка общих параметров начальных условий ---
        chord = self.session.scalar(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id))
        constr = self.session.scalar(
            select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        boundary = self.session.scalar(
            select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))
        flow = self.session.scalar(
            select(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))

        # Базовые замены
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

        # --- Выбор шаблона и дополнительные параметры ---
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

        elif task_type == TaskType.THERMAL_STRESS:
            template_name = "thermal_stress.edp.template"
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
            replacements.update({
                "dt": str(time_params.dt if time_params else 0.05),
                "nbT": str(time_params.nbT if time_params else 25),
                "T_initial": str(init_temp.value if init_temp else 250),
                "a_steel": "12.54",
                "a_air": "21.02",
                "b": str(elastic.b if elastic else 1.0),
                "nu": str(elastic.nu if elastic else 0.28),
                "KLT": str(elastic.KLT if elastic else 10.5e-6),
                "E_steel": str(E_steel),
                "delt": str(stress_out.delt if stress_out else 0.4),
                "Npt": str(stress_out.Npt if stress_out else 200),
            })

        else:
            raise ValueError(f"Неподдерживаемый тип задачи: {task_type}")

        template_path = Path(__file__).parent.parent / "templates" / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Шаблон {template_name} не найден в templates/")
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        script = template
        for key, val in replacements.items():
            script = script.replace(f"{{{{{key}}}}}", str(val))

        with open(edp_path, 'w', encoding='utf-8') as f:
            f.write(script)

        logger.info(f"Скрипт {task_type.value} сохранён: {edp_path}")

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
        """Удаляет симуляцию из БД и её папку с файлами"""
        sim = self.session.get(Simulation, sim_id)
        if not sim:
            raise ValueError("Симуляция не найдена")
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        if os.path.exists(sim_dir):
            import shutil
            shutil.rmtree(sim_dir)
        self.session.delete(sim)

    def delete_failed_simulations(self) -> int:
        """Удаляет все симуляции со статусом 'failed'"""
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
        """Генерирует графики в зависимости от типа задачи и возвращает словарь с читаемыми названиями"""
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        from numpy.linalg import eig
        from PIL import Image
        import glob

        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        sim = self.session.get(Simulation, sim_id)
        if not sim:
            return {"error": "Симуляция не найдена"}

        task_type = sim.task_type  # 'gas_dynamics', 'thermal_field', 'thermal_stress'
        plots = {}

        # ---- Вспомогательные функции для задачи 3 ----
        def mizes2(tensor):
            eig_vals, _ = eig(tensor)
            miz = np.sqrt(((eig_vals[0] - eig_vals[1])**2)/2)
            return np.hstack((eig_vals, miz))

        def calc_eigMiz(data_select):
            eigMiz = np.zeros((np.shape(data_select)[0], 3))
            for i in range(np.shape(data_select)[0]):
                T_mat = np.array([[data_select[i, 0], data_select[i, 1]],
                                  [data_select[i, 1], data_select[i, 2]]])
                eigMiz[i] = mizes2(T_mat)
            return eigMiz

        # ========== ЗАДАЧА 1: ГАЗОДИНАМИКА + ТЕПЛО ==========
        if task_type == 'gas_dynamics':
            # Конвертируем все plot_*.eps в PNG с осмысленными ключами
            eps_files = sorted(glob.glob(os.path.join(sim_dir, "plot_*.eps")))
            titles = {
                'plot_1': 'Сетка',
                'plot_2': 'Функция тока ψ',
                'plot_3': 'Поле скорости',
                'plot_4': 'Давление p',
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

            # Финальное температурное поле (temp_final.eps)
            temp_final = os.path.join(sim_dir, "temp_final.eps")
            if os.path.exists(temp_final):
                try:
                    img = Image.open(temp_final)
                    png_file = temp_final.replace('.eps', '.png')
                    img.save(png_file, 'PNG')
                    with open(png_file, 'rb') as f:
                        plots['Температурное поле (финальное)'] = base64.b64encode(f.read()).decode('utf-8')
                except Exception as e:
                    logger.warning(f"Не удалось конвертировать temp_final.eps: {e}")

            # Создание GIF из temp_*.eps
            temp_eps = sorted(glob.glob(os.path.join(sim_dir, "temp_*.eps")))
            # отфильтруем temp_final (он не идёт в анимацию)
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
                    logger.info(f"GIF анимация создана: {gif_path}")

        # ========== ЗАДАЧА 2: ТЕПЛОВОЕ ПОЛЕ (без напряжений) ==========
        elif task_type == 'thermal_field':
            eps_files = sorted(glob.glob(os.path.join(sim_dir, "plot_*.eps")))
            if eps_files:
                # Первый файл — сетка
                first = eps_files[0]
                try:
                    img = Image.open(first)
                    png_file = first.replace('.eps', '.png')
                    img.save(png_file, 'PNG')
                    with open(png_file, 'rb') as f:
                        plots['Сетка'] = base64.b64encode(f.read()).decode('utf-8')
                except Exception as e:
                    logger.warning(f"Не удалось конвертировать сетку: {e}")

                # Остальные — кадры температуры
                frame_num = 1
                for eps in eps_files[1:]:
                    try:
                        img = Image.open(eps)
                        png_file = eps.replace('.eps', '.png')
                        img.save(png_file, 'PNG')
                        with open(png_file, 'rb') as f:
                            plots[f'Температурное поле (кадр {frame_num})'] = base64.b64encode(f.read()).decode('utf-8')
                        frame_num += 1
                    except Exception as e:
                        logger.warning(f"Не удалось конвертировать {eps}: {e}")

        # ========== ЗАДАЧА 3: ТЕРМОУПРУГОСТЬ ==========
        elif task_type == 'thermal_stress':
            # 1. Профиль лопатки (Profout.csv)
            prof_path = os.path.join(sim_dir, "Profout.csv")
            if os.path.exists(prof_path):
                data = np.loadtxt(prof_path)
                plt.figure(figsize=(8, 5))
                plt.plot(data[:,0], data[:,1], 'b-', label='Спинка')
                plt.plot(data[:,0], data[:,2], 'b-', label='Корытце')
                plt.plot(data[:,3], data[:,4], 'r-', label='Спинка смещ.')
                plt.plot(data[:,3], data[:,5], 'r-', label='Корытце смещ.')
                plt.xlabel('X, мм')
                plt.ylabel('Y, мм')
                plt.title('Профиль лопатки')
                plt.legend()
                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=100)
                buf.seek(0)
                plots['Профиль лопатки'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()

            # 2. Данные из TEpsout.csv (деформации и температура)
            eps_path = os.path.join(sim_dir, "TEpsout.csv")
            if os.path.exists(eps_path):
                data = np.loadtxt(eps_path)
                x_coords = data[:, 0]

                # Деформация Мизеса
                data_up = data[:, 3:6]
                eps_up = calc_eigMiz(data_up)[:, 2] * 100
                data_lw = data[:, 8:11]
                eps_lw = calc_eigMiz(data_lw)[:, 2] * 100

                plt.figure(figsize=(8,5))
                plt.plot(x_coords, eps_up, 'ro-', label='Спинка')
                plt.plot(x_coords, eps_lw, 'bo-', label='Корытце')
                plt.xlabel('X, мм')
                plt.ylabel('Деформация, %')
                plt.title('Эквивалентная деформация Мизеса')
                plt.legend()
                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=100)
                buf.seek(0)
                plots['Деформация Мизеса'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()

                # Температура на поверхности
                plt.figure(figsize=(8,5))
                plt.plot(x_coords, data[:,2], 'r-', label='Спинка')
                plt.plot(x_coords, data[:,7], 'b-', label='Корытце')
                plt.xlabel('X, мм')
                plt.ylabel('Температура, °C')
                plt.title('Распределение температуры по поверхности лопатки')
                plt.legend()
                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=100)
                buf.seek(0)
                plots['Температура (поверхность)'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()

            # 3. Данные из TSout.csv (напряжения)
            stress_path = os.path.join(sim_dir, "TSout.csv")
            if os.path.exists(stress_path):
                data = np.loadtxt(stress_path)
                x_coords = data[:, 0]
                data_up = data[:, 3:6]
                sig_up = calc_eigMiz(data_up)[:, 2]
                data_lw = data[:, 8:11]
                sig_lw = calc_eigMiz(data_lw)[:, 2]

                plt.figure(figsize=(8,5))
                plt.plot(x_coords, sig_up, 'ro-', label='Спинка')
                plt.plot(x_coords, sig_lw, 'bo-', label='Корытце')
                plt.xlabel('X, мм')
                plt.ylabel('Напряжение, МПа')
                plt.title('Эквивалентное напряжение Мизеса')
                plt.legend()
                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=100)
                buf.seek(0)
                plots['Напряжение Мизеса'] = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()

            # 4. Конвертируем оставшиеся EPS (Sig1, Sig2, Sig12)
            eps_remaining = glob.glob(os.path.join(sim_dir, "*.eps"))
            for eps in eps_remaining:
                base = os.path.basename(eps).replace('.eps', '')
                if base.startswith('plot_') or base.startswith('temp_'):
                    continue
                try:
                    img = Image.open(eps)
                    png_file = eps.replace('.eps', '.png')
                    img.save(png_file, 'PNG')
                    with open(png_file, 'rb') as f:
                        if 'sig1' in base.lower():
                            name = 'Напряжение σ₁'
                        elif 'sig2' in base.lower():
                            name = 'Напряжение σ₂'
                        elif 'sig12' in base.lower():
                            name = 'Напряжение σ₁₂'
                        else:
                            name = base
                        plots[name] = base64.b64encode(f.read()).decode('utf-8')
                except Exception as e:
                    logger.warning(f"Не удалось конвертировать {eps}: {e}")

        return plots