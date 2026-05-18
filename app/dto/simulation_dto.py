from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

class TaskType(str, Enum):
    GAS_DYNAMICS = "gas_dynamics"
    THERMAL = "thermal"
    THERMAL_STRESS = "thermal_stress"

class SimulationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    blade_id: Optional[int] = None
    assembly_id: Optional[int] = None
    material_ids: List[int] = Field(..., min_length=1)
    initial_conditions_id: int
    task_type: TaskType

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
class EiValueRequest(BaseModel):
    material_id: int
    value: float

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
    ei_values: List[EiValueRequest] = []   #
    model_config = ConfigDict(from_attributes=True)

class SimulationResponse(BaseModel):
    simulation_id: int; name: str; status: str = "created"
    model_config = ConfigDict(from_attributes=True)