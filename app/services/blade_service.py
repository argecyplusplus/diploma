from typing import List, Optional
from sqlalchemy.orm import Session
from ..repositories.blade_repository import (
    BladeRepository, BladeAssemblyRepository, ProfileCoordinateRepository
)
from ..dto.blade_dto import (
    BladeCreateRequest, BladeUpdateRequest, BladeResponse,
    ProfileCoordinateRequest, ProfileCoordinateResponse,
    BladeAssemblyCreateRequest, BladeAssemblyUpdateRequest,
    BladeAssemblyResponse, BladeAssemblyMemberResponse
)


class BladeService:
    def __init__(self, session: Session):
        self.blade_repo = BladeRepository(session)
        self.assembly_repo = BladeAssemblyRepository(session)
        self.coord_repo = ProfileCoordinateRepository(session)

    # --- CRUD Лопаток ---
    def create_blade(self, data: BladeCreateRequest) -> BladeResponse:
        blade = self.blade_repo.create(name=data.name)
        return BladeResponse.model_validate(blade)

    def get_blade(self, blade_id: int) -> Optional[BladeResponse]:
        blade = self.blade_repo.get_by_id(blade_id)
        return BladeResponse.model_validate(blade) if blade else None

    def get_all_blades(self) -> List[BladeResponse]:
        return [BladeResponse.model_validate(b) for b in self.blade_repo.get_all()]

    def update_blade(self, blade_id: int, data: BladeUpdateRequest) -> BladeResponse:
        blade = self.blade_repo.get_by_id(blade_id)
        if not blade: raise ValueError("Blade not found")
        blade.name = data.name
        return BladeResponse.model_validate(self.blade_repo.update(blade))

    def delete_blade(self, blade_id: int):
        blade = self.blade_repo.get_by_id(blade_id)
        if not blade: raise ValueError("Blade not found")
        self.blade_repo.delete(blade)

    # --- CRUD Координат ---
    def get_coordinates(self, blade_id: int) -> List[ProfileCoordinateResponse]:
        coords = self.coord_repo.get_by_blade(blade_id)
        return [ProfileCoordinateResponse.model_validate(c) for c in coords]

    def add_coordinate(self, blade_id: int, data: ProfileCoordinateRequest) -> ProfileCoordinateResponse:
        p_type = data.profile_type.lower()
        if p_type not in ('upper', 'lower'):
            raise ValueError("profile_type must be 'upper' or 'lower'")

        coord = self.coord_repo.create(
            blade_id=blade_id, profile_type=p_type,
            profile_name=data.profile_name, x=data.x, y=data.y
        )
        return ProfileCoordinateResponse.model_validate(coord)

    def bulk_add_coordinates(self, blade_id: int, coords: List[ProfileCoordinateRequest]) -> List[
        ProfileCoordinateResponse]:
        # Преобразуем DTO в формат, ожидаемый репозиторием
        data_list = [
            {
                "blade_id": blade_id,
                "profile_type": c.profile_type.lower(),
                "profile_name": c.profile_name,
                "x": c.x,
                "y": c.y
            } for c in coords
        ]
        saved = self.coord_repo.bulk_create(data_list)
        return [ProfileCoordinateResponse.model_validate(c) for c in saved]

    def clear_coordinates(self, blade_id: int):
        self.coord_repo.delete_by_blade(blade_id)

    # --- CRUD Объединений (Сборок) ---
    def create_assembly(self, data: BladeAssemblyCreateRequest) -> BladeAssemblyResponse:
        assembly = self.assembly_repo.create(name=data.name)
        for bid in data.blade_ids:
            self.assembly_repo.add_member(assembly.blade_assembly_id, bid)
        return BladeAssemblyResponse.model_validate(assembly)

    def get_all_assemblies(self) -> List[BladeAssemblyResponse]:
        return [BladeAssemblyResponse.model_validate(a) for a in self.assembly_repo.get_all()]

    def get_assembly_members(self, assembly_id: int) -> List[BladeAssemblyMemberResponse]:
        assembly = self.assembly_repo.get_by_id(assembly_id)
        if not assembly: return []
        return [BladeAssemblyMemberResponse.model_validate(m) for m in assembly.members]

    def update_assembly(self, assembly_id: int, data: BladeAssemblyUpdateRequest) -> BladeAssemblyResponse:
        assembly = self.assembly_repo.get_by_id(assembly_id)
        if not assembly: raise ValueError("Assembly not found")

        if data.name:
            assembly.name = data.name

        if data.add_blade_ids:
            for bid in data.add_blade_ids:
                self.assembly_repo.add_member(assembly_id, bid)

        if data.remove_blade_ids:
            # Удаляем связи из сборки
            self.assembly_repo.delete_members(assembly_id, data.remove_blade_ids)

        return BladeAssemblyResponse.model_validate(assembly)

    def delete_assembly(self, assembly_id: int):
        assembly = self.assembly_repo.get_by_id(assembly_id)
        if not assembly: raise ValueError("Assembly not found")
        self.assembly_repo.delete(assembly)