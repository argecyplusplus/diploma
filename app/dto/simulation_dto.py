from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class TaskRequest(BaseModel):
    task_id: int  # 1, 2, 3
    description: Optional[str] = None

class SimulationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    blade_id: int
    assembly_id: Optional[int] = None
    material_ids: List[int] = Field(..., min_length=1)
    initial_conditions_id: int
    tasks: List[TaskRequest] = []

class TimeParamRequest(BaseModel):
    time: float; dt: float; nbT: float; Nplot: float
class PotentialFlowRequest(BaseModel):
    beta: float; B: float
class BoundaryIdRequest(BaseModel):
    name: str; value: float
class ConstructionParamRequest(BaseModel):
    NC: int; NSp: int; NSm: int; NSpn: int; NSpm: int
class InitialTempRequest(BaseModel):
    material_id: int; value: float
class ElasticityParamRequest(BaseModel):
    b: float; nu: float; KLT: float
class StressOutParamRequest(BaseModel):
    coef: float; delt: float; Npt: float
class BladeChordRequest(BaseModel):
    name: str; value: float

class InitialConditionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    time_parameters: TimeParamRequest
    potential_flow: PotentialFlowRequest
    boundaries: List[BoundaryIdRequest] = []
    construction: ConstructionParamRequest
    initial_temps: List[InitialTempRequest] = []
    elasticity: ElasticityParamRequest
    stress_output: StressOutParamRequest
    chords: List[BladeChordRequest] = []
    model_config = ConfigDict(from_attributes=True)

class SimulationResponse(BaseModel):
    simulation_id: int; name: str; status: str = "created"
    model_config = ConfigDict(from_attributes=True)