from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, delete as sql_delete

from ..models.simulation import (
    Simulation, SimulationTask, SimulationResult, SimulationMaterial,
    InitialCondition, TimeParameter, BladeChord, PotentialFlowParameter,
    BoundaryIdentifier, ElasticityParameter, ConstructionParameter,
    InitialTemperature, StressOutputParameter
)


class InitialConditionRepository:
    """
    Репозиторий для управления начальными условиями (InitialConditions)
    и их сложной структурой параметров (время, границы, температура и т.д.)
    """

    def __init__(self, session: Session):
        self.session = session

    # --- Базовые операции ---
    def create(self, name: str) -> InitialCondition:
        condition = InitialCondition(name=name)
        self.session.add(condition)
        self.session.flush()
        return condition

    def get_by_id(self, condition_id: int) -> Optional[InitialCondition]:
        return self.session.get(InitialCondition, condition_id)

    def delete(self, condition: InitialCondition):
        self.session.delete(condition)

    # --- Управление параметрами времени ---
    def add_time_parameters(self, condition_id: int, time: float, dt: float, nbT: float, Nplot: float) -> TimeParameter:
        params = TimeParameter(
            initial_conditions_id=condition_id,
            time=time, dt=dt, nbT=nbT, Nplot=Nplot
        )
        self.session.add(params)
        self.session.flush()
        return params

    # --- Управление геометрией (хорда) ---
    def add_blade_chord(self, condition_id: int, name: str, value: float) -> BladeChord:
        chord = BladeChord(initial_conditions_id=condition_id, name=name, value=value)
        self.session.add(chord)
        self.session.flush()
        return chord

    # --- Управление газодинамикой (потенциальный поток) ---
    def add_flow_parameters(self, condition_id: int, beta: float, B: float) -> PotentialFlowParameter:
        params = PotentialFlowParameter(initial_conditions_id=condition_id, beta=beta, B=B)
        self.session.add(params)
        self.session.flush()
        return params

    # --- Управление границами (Boundary Identifiers) ---
    def add_boundary_identifier(self, condition_id: int, name: str, value: float) -> BoundaryIdentifier:
        identifier = BoundaryIdentifier(initial_conditions_id=condition_id, name=name, value=value)
        self.session.add(identifier)
        self.session.flush()
        return identifier

    def bulk_add_boundaries(self, condition_id: int, boundaries: List[Dict]) -> List[BoundaryIdentifier]:
        """Массовое добавление граничных условий"""
        instances = [
            BoundaryIdentifier(initial_conditions_id=condition_id, **b)
            for b in boundaries
        ]
        self.session.add_all(instances)
        self.session.flush()
        return instances

    # --- Управление упругостью ---
    def add_elasticity_parameters(self, condition_id: int, b: float, nu: float, KLT: float) -> ElasticityParameter:
        params = ElasticityParameter(initial_conditions_id=condition_id, b=b, nu=nu, KLT=KLT)
        self.session.add(params)
        self.session.flush()
        return params

    # --- Управление конструктивными параметрами ---
    def add_construction_parameters(self, condition_id: int, NC: int, NSp: int, NSm: int, NSpn: int,
                                    NSpm: int) -> ConstructionParameter:
        params = ConstructionParameter(
            initial_conditions_id=condition_id,
            NC=NC, NSp=NSp, NSm=NSm, NSpn=NSpn, NSpm=NSpm
        )
        self.session.add(params)
        self.session.flush()
        return params

    # --- Управление температурой ---
    def add_initial_temperature(self, condition_id: int, material_id: int, value: float) -> InitialTemperature:
        temp = InitialTemperature(initial_conditions_id=condition_id, material_id=material_id, value=value)
        self.session.add(temp)
        self.session.flush()
        return temp

    # --- Управление выводом напряжений ---
    def add_stress_output_parameters(self, condition_id: int, coef: float, delt: float,
                                     Npt: float) -> StressOutputParameter:
        params = StressOutputParameter(initial_conditions_id=condition_id, coef=coef, delt=delt, Npt=Npt)
        self.session.add(params)
        self.session.flush()
        return params


class SimulationRepository:
    """Репозиторий для управления симуляциями и связанными объектами"""

    def __init__(self, session: Session):
        self.session = session

    # --- Базовые операции ---
    def create(self, name: str, blade_assembly_id: int, blade_id: int, initial_conditions_id: int) -> Simulation:
        simulation = Simulation(
            name=name,
            blade_assembly_id=blade_assembly_id,
            blade_id=blade_id,
            initial_conditions_id=initial_conditions_id
        )
        self.session.add(simulation)
        self.session.flush()
        return simulation

    def get_by_id(self, simulation_id: int) -> Optional[Simulation]:
        return self.session.get(Simulation, simulation_id)

    def get_all(self) -> List[Simulation]:
        return self.session.scalars(select(Simulation)).all()

    def delete(self, simulation: Simulation):
        self.session.delete(simulation)

    # --- Управление задачами (Tasks) ---
    def add_task(self, simulation_id: int, task_value: float, description: Optional[str] = None) -> SimulationTask:
        task = SimulationTask(
            simulation_id=simulation_id,
            task_value=task_value,
            description=description
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get_tasks(self, simulation_id: int) -> List[SimulationTask]:
        return self.session.scalars(
            select(SimulationTask).where(SimulationTask.simulation_id == simulation_id)
        ).all()

    # --- Управление результатами (Results) ---
    def add_result(self, simulation_id: int, file_type: str, file_path: str,
                   description: Optional[str] = None) -> SimulationResult:
        result = SimulationResult(
            simulation_id=simulation_id,
            file_type=file_type,
            file_path=file_path,
            description=description
        )
        self.session.add(result)
        self.session.flush()
        return result

    def get_results(self, simulation_id: int) -> List[SimulationResult]:
        return self.session.scalars(
            select(SimulationResult).where(SimulationResult.simulation_id == simulation_id)
        ).all()

    # --- Управление материалами симуляции ---
    def add_material(self, simulation_id: int, material_id: int) -> SimulationMaterial:
        # Проверка на дубликаты (опционально, но полезно)
        exists = self.session.scalar(
            select(SimulationMaterial).where(
                SimulationMaterial.simulation_id == simulation_id,
                SimulationMaterial.material_id == material_id
            )
        )
        if exists:
            return exists

        link = SimulationMaterial(simulation_id=simulation_id, material_id=material_id)
        self.session.add(link)
        self.session.flush()
        return link

    def get_materials(self, simulation_id: int) -> List[SimulationMaterial]:
        return self.session.scalars(
            select(SimulationMaterial).where(SimulationMaterial.simulation_id == simulation_id)
        ).all()