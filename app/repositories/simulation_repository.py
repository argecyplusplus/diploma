from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models.simulation import (
    Simulation, SimulationTask, SimulationResult, SimulationMaterial,
    InitialCondition, TimeParameter, PotentialFlowParameter,
    BoundaryIdentifier, ConstructionParameter, InitialTemperature,
    ElasticityParameter, StressOutputParameter, BladeChord
)


class SimulationRepository:
    def __init__(self, session: Session):
        self.session = session

    # --- Simulations ---
    def get_all_simulations(self) -> List[Simulation]:
        return self.session.scalars(select(Simulation)).all()

    def get_by_id(self, sim_id: int) -> Optional[Simulation]:
        return self.session.get(Simulation, sim_id)

    def create(self, **kwargs) -> Simulation:
        sim = Simulation(**kwargs)
        self.session.add(sim)
        self.session.flush()
        return sim

    def add_tasks(self, sim_id: int, tasks_data: List[dict]):
        for t in tasks_data:
            self.session.add(SimulationTask(simulation_id=sim_id, task_value=1.0, description=t.get('description')))
        self.session.flush()

    def add_materials(self, sim_id: int, material_ids: List[int]):
        for mid in material_ids:
            self.session.add(SimulationMaterial(simulation_id=sim_id, material_id=mid))
        self.session.flush()

    def add_result(self, sim_id: int, file_type: str, file_path: str, desc: str = "") -> SimulationResult:
        res = SimulationResult(simulation_id=sim_id, file_type=file_type, file_path=file_path, description=desc)
        self.session.add(res)
        self.session.flush()
        return res

    # --- Initial Conditions ---
    def get_all_initial_conditions(self) -> List[InitialCondition]:
        return self.session.scalars(select(InitialCondition)).all()

    def create_initial_condition(self, data: dict) -> InitialCondition:
        ic = InitialCondition(name=data['name'])
        self.session.add(ic)
        self.session.flush()
        ic_id = ic.initial_conditions_id

        # Сохраняем вложенные параметры
        self.session.add(TimeParameter(initial_conditions_id=ic_id, **data['time_parameters']))
        self.session.add(PotentialFlowParameter(initial_conditions_id=ic_id, **data['potential_flow']))
        self.session.add(ConstructionParameter(initial_conditions_id=ic_id, **data['construction']))
        self.session.add(ElasticityParameter(initial_conditions_id=ic_id, **data['elasticity']))
        self.session.add(StressOutputParameter(initial_conditions_id=ic_id, **data['stress_output']))

        for b in data['boundaries']:
            self.session.add(BoundaryIdentifier(initial_conditions_id=ic_id, **b))
        for t in data['initial_temps']:
            self.session.add(InitialTemperature(initial_conditions_id=ic_id, **t))
        for c in data['chords']:
            self.session.add(BladeChord(initial_conditions_id=ic_id, **c))

        self.session.flush()
        return ic