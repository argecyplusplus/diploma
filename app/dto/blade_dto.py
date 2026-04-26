from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

# --- Blade DTOs ---
class BladeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Название лопатки")

class BladeUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class BladeResponse(BaseModel):
    blade_id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

# --- Coordinate DTOs ---
# В новой БД верхний/нижний профиль хранится в одной таблице с полем profile_type
class ProfileCoordinateRequest(BaseModel):
    profile_type: str = Field(..., description="'upper' или 'lower'")
    profile_name: str = Field(..., min_length=1)
    x: float
    y: float

class ProfileCoordinateResponse(BaseModel):
    profile_coordinates_id: int
    blade_id: int
    profile_type: str
    profile_name: str
    x: float
    y: float
    model_config = ConfigDict(from_attributes=True)

# --- Assembly/Merge DTOs ---
class BladeAssemblyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Общее наименование сборки")
    blade_ids: List[int] = Field(..., min_items=1, description="ID лопаток для включения")

class BladeAssemblyUpdateRequest(BaseModel):
    name: Optional[str] = None
    add_blade_ids: Optional[List[int]] = None
    remove_blade_ids: Optional[List[int]] = None

class BladeAssemblyResponse(BaseModel):
    blade_assembly_id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

class BladeAssemblyMemberResponse(BaseModel):
    blade_assembly_members_id: int
    blade_id: int
    description: Optional[str]
    model_config = ConfigDict(from_attributes=True)