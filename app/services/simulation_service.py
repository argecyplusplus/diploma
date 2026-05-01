import os
import subprocess
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

    def create_simulation(self, data: SimulationCreateRequest) -> int:
        # Проверка: ровно один из id должен быть указан
        if (data.blade_id is None and data.assembly_id is None) or \
                (data.blade_id is not None and data.assembly_id is not None):
            raise ValueError("Должна быть указана либо лопатка, либо объединение, но не оба")

        sim_data = data.model_dump(exclude={'tasks', 'material_ids'})
        # Удаляем None-значения, чтобы не передавать их в create
        sim_data = {k: v for k, v in sim_data.items() if v is not None}
        # Если выбрано объединение, поле blade_assembly_id называется не assembly_id
        if 'assembly_id' in sim_data:
            sim_data['blade_assembly_id'] = sim_data.pop('assembly_id')
        # Если выбрана лопатка, blade_id будет передан как есть

        sim = self.repo.create(**sim_data)
        sim_id = sim.simulation_id

        self.repo.add_materials(sim_id, data.material_ids)
        self.repo.add_tasks(sim_id, [t.model_dump() for t in data.tasks])

        # 📁 Создаём папку для конкретного расчёта
        sim_dir = os.path.join(self.upload_dir, f"sim_{sim_id}")
        os.makedirs(sim_dir, exist_ok=True)

        try:
            edp_path = os.path.join(sim_dir, "blade_sim.edp")
            self._generate_freefem_code(sim_id, sim_dir, edp_path)

            logger.info(f"🚀 Запуск FreeFEM++ для симуляции {sim_id}...")
            result = self._run_freefem(edp_path, sim_dir)

            # 💾 Сохраняем логи консоли
            log_path = os.path.join(sim_dir, "console.log")
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(result.get('stdout', '') + '\n--- ERROR OUTPUT ---\n' + result.get('stderr', ''))
            self.repo.add_result(sim_id, "log", log_path, "FreeFEM++ console output")

            if result['success']:
                sim.status = "completed"
                # FreeFEM++ в скрипте сохраняет result.vtk. Проверяем и регистрируем.
                vtk_path = os.path.join(sim_dir, "result.vtk")
                if os.path.exists(vtk_path):
                    self.repo.add_result(sim_id, "vtk", vtk_path, "Mesh & Field data")
            else:
                sim.status = "failed"
                logger.error(f"❌ Симуляция {sim_id} завершилась с ошибкой: {result.get('error')}")

            self.session.add(sim)
            self.session.commit()

        except Exception as e:
            logger.error(f"💥 Ошибка при создании симуляции {sim_id}: {e}")
            self.session.rollback()
            raise e

        return sim_id

    def get_simulations_list(self):
        return self.repo.get_all_simulations()

    # ========================================================================
    # 🔧 Внутренние методы генерации и запуска
    # ========================================================================

    def _generate_freefem_code(self, sim_id: int, sim_dir: str, edp_path: str):
        sim = self.session.get(Simulation, sim_id)
        ic_id = sim.initial_conditions_id

        # 1. Загружаем параметры начальных условий
        const_params = self.session.scalar(
            select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        flow_params = self.session.scalar(
            select(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))
        time_params = self.session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
        boundary = self.session.scalar(
            select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))
        chord = self.session.scalar(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id))

        # 2. Плотность первого материала
        first_mat_id = sim.materials[0].material_id if sim.materials else None
        material = self.session.get(Material, first_mat_id)
        rho = material.density if material else 1.0

        # 3. Коэффициенты Лежандра (аппроксимация должна быть выполнена заранее)
        approx = self.session.scalar(select(Approximation).where(Approximation.blade_id == sim.blade_id).order_by(
            Approximation.approximation_id.desc()))
        if not approx:
            raise ValueError(
                "Для выбранной лопатки не выполнена аппроксимация. Запустите аппроксимацию перед моделированием.")

        coeffs = self.session.scalars(
            select(LegendreCoefficient).where(LegendreCoefficient.approximation_id == approx.approximation_id).order_by(
                LegendreCoefficient.legendre_coefficients_id)).all()
        if len(coeffs) < 10:
            raise ValueError("Недостаточно коэффициентов Лежандра (ожидается 10).")

        coeffs_up = ", ".join(f"{c.upper_value:.10e}" for c in coeffs)
        coeffs_low = ", ".join(f"{c.lower_value:.10e}" for c in coeffs)

        # 4. Генерация скрипта FreeFEM++
        script = f"""
int S1 = {boundary.value if boundary else 100};
real Chord1 = {chord.value if chord else 1.0}; 
real RC = 3. * Chord1;

border C(t=0, 2*pi){{x=Chord1/2. + RC*cos(t); y=RC*sin(t);}}

real beta = {flow_params.beta if flow_params else 0.0}; 
real B = {flow_params.B if flow_params else 1.0};
real rho = {rho}; 

load "iovtk"
real[int] coeffsUp(10) = [{coeffs_up}];
real[int] coeffsLow(10) = [{coeffs_low}];

func real Lezh(real[int] L,real t){{
    real[int] y(10);
    y(0)=1.; y(1)=t; y(2)=(3.*t^2-1.)/2.; y(3)=(5.*t^3-3.*t)/2.; 
    y(4)=(35.*t^4-30.*t^2+3.)/8.; y(5)=(63.*t^5-70.*t^3+15.*t)/8.;
    y(6)=231./16.*t^6-315./16.*t^4+105./16.*t^2-5./16.; 
    y(7)=429./16.*t^7-693./16.*t^5+315./16.*t^3-35./16.*t;
    y(8)=6435./128.*t^8-3003./32.*t^6+3465./64.*t^4-315./32.*t^2+35./128.;
    y(9)=12155./128.*t^9-6435./32.*t^7+9009./64.*t^5-1155./32.*t^3+315./128.*t;
    return L'*y;
}}

border Splus(t=0., 1.){{x=Chord1*t; y=Chord1*Lezh(coeffsUp,t); label=S1;}}
border Sminus(t=1., 0.){{x=Chord1*t; y=Chord1*Lezh(coeffsLow,t); label=S1;}}
border Spm(t=0,1.){{x=0;y=Chord1*Lezh(coeffsLow,0)+t*Chord1*(Lezh(coeffsUp,0)-Lezh(coeffsLow,0)); label=S1;}}
border Smp(t=1.,0.){{x=Chord1;y=Chord1*Lezh(coeffsLow,1)+t*Chord1*(Lezh(coeffsUp,1)-Lezh(coeffsLow,1)); label=S1;}}

real xblade=Chord1*0.25, yblade=Chord1*(Lezh(coeffsUp,0.5)+Lezh(coeffsLow,0.5))/2;
mesh Th = buildmesh(C({const_params.NC})+Splus({const_params.NSp})+Spm({const_params.NSpm})+Sminus({const_params.NSm})+Smp({const_params.NSpm}));

fespace Vh(Th, P2);
Vh psi, w, vx, vy, p;
real cost = cos(beta*pi/180.), sint=sin(beta*pi/180.);

solve potential(psi, w)
  = int2d(Th)(dx(psi)*dx(w)+dy(psi)*dy(w))
  + on(C, psi = cost*y-sint*x) 
  + on(S1, psi=0);
vx=dx(psi); vy=dy(psi);
p = 1-rho/(2*B)*(vx^2+vy^2);

real dt = {time_params.dt if time_params else 0.1}, nbT = {time_params.nbT if time_params else 100};
border D(t=0, 2.){{x=0.5+t*cost; y=+t*sint;}}
mesh Sh = buildmesh(C({const_params.NC}) + Splus(-{const_params.NSp}) + Spm(-{const_params.NSpm}) + Sminus(-{const_params.NSm}) + Smp(-{const_params.NSpm}) + D({const_params.NSpn}));
fespace Wh(Sh, P1); Wh vv;
fespace W0(Sh, P0); W0 k = 0.01*(region == 2) + 0.1*(region == 1);
W0 u1 = dy(psi)*(region == 2), u2 = -dx(psi)*(region == 2);
Wh v = 400*(region == 1), vold;
Sh = change(Sh,flabel = (label == C && [u1,u2]'*N <0) ? 10 : label);

int i;
problem thermic(v, vv, init=i, solver=LU)
  = int2d(Sh)(v*vv/dt + k*(dx(v)*dx(vv) + dy(v)*dy(vv)) + 10*(u1*dx(v) + u2*dy(v))*vv)
  - int2d(Sh)(vold*vv/dt) + on(10, v= 0);

for(i = 0; i < nbT; i++) {{ vold[]= v[]; thermic; }}

// 💾 Сохраняем результат в VTK для визуализации
savevtk("result.vtk", Th, p, "pressure");
cout << "Simulation completed successfully." << endl;
"""
        with open(edp_path, 'w', encoding='utf-8') as f:
            f.write(script)
        logger.info(f"📝 Скрипт FreeFEM++ сохранён: {edp_path}")

    def _run_freefem(self, edp_path: str, work_dir: str) -> dict:
        # 🌍 Путь к исполняемому файлу FreeFEM++ (берётся из .env или системный PATH)
        ff_path = os.getenv("FREEFEM_PATH", "FreeFem++")

        # 🖥️ Формируем команду: -nw = no window (тихий режим для сервера)
        cmd = [ff_path, edp_path, "-nw"]

        env = os.environ.copy()
        env['PWD'] = work_dir  # FreeFEM иногда использует CWD для относительных путей

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # ⏱️ Максимум 10 минут на расчёт
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