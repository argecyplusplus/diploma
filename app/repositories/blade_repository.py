from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, delete as sql_delete

# Импорт моделей из слоя данных
from ..models.blade import (
    Blade, BladeAssembly, BladeAssemblyMember,
    ProfileCoordinate, Approximation, ApproximationParameter,
    LegendreCoefficient, TransformedCoordinate
)


class BladeRepository:
    """Репозиторий для управления сущностью Лопатка (Blade)"""
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, blade_id: int) -> Optional[Blade]:
        return self.session.get(Blade, blade_id)

    def get_all(self) -> List[Blade]:
        return self.session.scalars(select(Blade)).all()

    def get_by_name(self, name: str) -> Optional[Blade]:
        return self.session.scalar(select(Blade).where(Blade.name == name))

    def create(self, name: str) -> Blade:
        new_blade = Blade(name=name)
        self.session.add(new_blade)
        self.session.flush()  # Получаем ID без коммита транзакции
        return new_blade

    def update(self, blade: Blade) -> Blade:
        self.session.merge(blade)
        return blade

    def delete(self, blade: Blade):
        self.session.delete(blade)


class BladeAssemblyRepository:
    """Репозиторий для управления сборками лопаток (BladeAssembly)"""
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, assembly_id: int) -> Optional[BladeAssembly]:
        return self.session.get(BladeAssembly, assembly_id)

    def get_all(self) -> List[BladeAssembly]:
        return self.session.scalars(select(BladeAssembly)).all()

    def create(self, name: str) -> BladeAssembly:
        new_assembly = BladeAssembly(name=name)
        self.session.add(new_assembly)
        self.session.flush()
        return new_assembly

    def add_member(self, assembly_id: int, blade_id: int, description: Optional[str] = None) -> BladeAssemblyMember:
        member = BladeAssemblyMember(
            blade_assembly_id=assembly_id,
            blade_id=blade_id,
            description=description
        )
        self.session.add(member)
        self.session.flush()
        return member

    def delete(self, assembly: BladeAssembly):
        self.session.delete(assembly)

    def delete_members(self, assembly_id: int, blade_ids: List[int]):
        self.session.execute(
            sql_delete(BladeAssemblyMember).where(
                BladeAssemblyMember.blade_assembly_id == assembly_id,
                BladeAssemblyMember.blade_id.in_(blade_ids)
            )
        )
        self.session.flush()


class ProfileCoordinateRepository:
    """Репозиторий для работы с геометрией профилей лопаток"""
    def __init__(self, session: Session):
        self.session = session

    def get_by_blade(self, blade_id: int) -> List[ProfileCoordinate]:
        return self.session.scalars(
            select(ProfileCoordinate).where(ProfileCoordinate.blade_id == blade_id)
        ).all()

    def get_by_type(self, blade_id: int, profile_type: str) -> List[ProfileCoordinate]:
        return self.session.scalars(
            select(ProfileCoordinate).where(
                ProfileCoordinate.blade_id == blade_id,
                ProfileCoordinate.profile_type == profile_type
            )
        ).all()

    def create(self, blade_id: int, profile_type: str, x: float, y: float) -> ProfileCoordinate:
        coord = ProfileCoordinate(
            blade_id=blade_id, profile_type=profile_type,
            x=x, y=y
        )
        self.session.add(coord)
        self.session.flush()
        return coord

    def bulk_create(self, coordinates_data: List[Dict]) -> List[ProfileCoordinate]:
        """Массовое добавление точек профиля из списка словарей"""
        instances = [ProfileCoordinate(**data) for data in coordinates_data]
        self.session.add_all(instances)
        self.session.flush()
        return instances

    def delete_by_blade(self, blade_id: int):
        self.session.execute(
            sql_delete(ProfileCoordinate).where(ProfileCoordinate.blade_id == blade_id)
        )


class ApproximationRepository:
    """Репозиторий для управления математической аппроксимацией профилей"""
    def __init__(self, session: Session):
        self.session = session

    def get_by_blade(self, blade_id: int) -> List[Approximation]:
        return self.session.scalars(
            select(Approximation).where(Approximation.blade_id == blade_id)
        ).all()

    def create(self, blade_id: int, approx_type: Optional[str] = None) -> Approximation:
        approx = Approximation(blade_id=blade_id, type=approx_type)
        self.session.add(approx)
        self.session.flush()
        return approx

    def get_parameters(self, approx_id: int) -> Optional[ApproximationParameter]:
        return self.session.scalar(
            select(ApproximationParameter).where(ApproximationParameter.approximation_id == approx_id)
        )

    def create_parameters(self, approx_id: int, profile_type: str, max_val: float, x_max: float, r_sq: float) -> ApproximationParameter:
        params = ApproximationParameter(
            approximation_id=approx_id, profile_type=profile_type,
            max_profile_value=max_val, x_coordinate_max=x_max, r_squared=r_sq
        )
        self.session.add(params)
        self.session.flush()
        return params

    def get_legendre_coefficients(self, approx_id: int) -> List[LegendreCoefficient]:
        return self.session.scalars(
            select(LegendreCoefficient).where(LegendreCoefficient.approximation_id == approx_id)
        ).all()

    def create_legendre_coefficients(self, approx_id: int, coeffs_data: List[Dict]) -> List[LegendreCoefficient]:
        """Массовое добавление коэффициентов Лежандра"""
        instances = [LegendreCoefficient(approximation_id=approx_id, **data) for data in coeffs_data]
        self.session.add_all(instances)
        self.session.flush()
        return instances

    def get_transformed_coords(self, approx_id: int) -> List[TransformedCoordinate]:
        return self.session.scalars(
            select(TransformedCoordinate).where(TransformedCoordinate.approximation_id == approx_id)
        ).all()

    def delete(self, approx: Approximation):
        self.session.delete(approx)