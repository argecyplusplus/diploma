from sqlalchemy import Column, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


# --------------------------------------------------------------------------
# Таблица 4: Blade_assemblies (Объединения лопаток)
# --------------------------------------------------------------------------
class BladeAssembly(Base):
    __tablename__ = 'blade_assemblies'

    blade_assembly_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

    members = relationship("BladeAssemblyMember", back_populates="assembly", cascade="all, delete-orphan")
    simulations = relationship("Simulation", back_populates="assembly", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BladeAssembly(id={self.blade_assembly_id}, name='{self.name}')>"


# --------------------------------------------------------------------------
# Таблица 5: Blades (Лопатки)
# --------------------------------------------------------------------------
class Blade(Base):
    __tablename__ = 'blades'

    blade_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

    assemblies = relationship("BladeAssemblyMember", back_populates="blade", cascade="all, delete-orphan")
    profiles = relationship("ProfileCoordinate", back_populates="blade", cascade="all, delete-orphan")
    approximations = relationship("Approximation", back_populates="blade", cascade="all, delete-orphan")
    simulations = relationship("Simulation", back_populates="blade", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Blade(id={self.blade_id}, name='{self.name}')>"


# --------------------------------------------------------------------------
# Таблица 6: Blade_assembly_members (Компоненты сборок)
# --------------------------------------------------------------------------
class BladeAssemblyMember(Base):
    __tablename__ = 'blade_assembly_members'

    blade_assembly_members_id = Column(Integer, primary_key=True, autoincrement=True)
    blade_assembly_id = Column(Integer, ForeignKey('blade_assemblies.blade_assembly_id', ondelete="CASCADE"), nullable=False)
    blade_id = Column(Integer, ForeignKey('blades.blade_id', ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=True)

    assembly = relationship("BladeAssembly", back_populates="members")
    blade = relationship("Blade", back_populates="assemblies")

    def __repr__(self):
        return f"<BladeAssemblyMember(assembly_id={self.blade_assembly_id}, blade_id={self.blade_id})>"


# --------------------------------------------------------------------------
# Таблица 7: Profile_coordinates (Координаты профиля)
# --------------------------------------------------------------------------
class ProfileCoordinate(Base):
    __tablename__ = 'profile_coordinates'

    profile_coordinates_id = Column(Integer, primary_key=True, autoincrement=True)
    blade_id = Column(Integer, ForeignKey('blades.blade_id', ondelete="CASCADE"), nullable=False)
    profile_type = Column(Text, nullable=False)
    profile_name = Column(Text, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)

    blade = relationship("Blade", back_populates="profiles")

    def __repr__(self):
        return f"<ProfileCoordinate(id={self.profile_coordinates_id}, profile='{self.profile_name}')>"


# --------------------------------------------------------------------------
# Таблица 8: Approximations (Аппроксимация)
# --------------------------------------------------------------------------
class Approximation(Base):
    __tablename__ = 'approximations'

    approximation_id = Column(Integer, primary_key=True, autoincrement=True)
    blade_id = Column(Integer, ForeignKey('blades.blade_id', ondelete="CASCADE"), nullable=False)
    type = Column(Text, nullable=True)

    # Обратные связи с дочерними таблицами параметров
    blade = relationship("Blade", back_populates="approximations")
    parameters = relationship("ApproximationParameter", back_populates="approximation", cascade="all, delete-orphan")
    legendre_coefficients = relationship("LegendreCoefficient", back_populates="approximation", cascade="all, delete-orphan")
    transformed_coordinates = relationship("TransformedCoordinate", back_populates="approximation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Approximation(id={self.approximation_id}, type='{self.type}')>"


# --------------------------------------------------------------------------
# Таблица 9: Approximation_parameters (Параметры аппроксимации)
# --------------------------------------------------------------------------
class ApproximationParameter(Base):
    __tablename__ = 'approximation_parameters'

    approximation_parameters_id = Column(Integer, primary_key=True, autoincrement=True)
    approximation_id = Column(Integer, ForeignKey('approximations.approximation_id', ondelete="CASCADE"), nullable=False)
    profile_type = Column(Text, nullable=False)
    max_profile_value = Column(Float, nullable=False)
    x_coordinate_max = Column(Float, nullable=False)
    r_squared = Column(Float, nullable=False)

    approximation = relationship("Approximation", back_populates="parameters")

    def __repr__(self):
        return f"<ApproximationParameter(id={self.approximation_parameters_id}, R²={self.r_squared})>"


# --------------------------------------------------------------------------
# Таблица 10: Legendre_coefficients (Коэффициенты Лежандра)
# --------------------------------------------------------------------------
class LegendreCoefficient(Base):
    __tablename__ = 'legendre_coefficients'

    legendre_coefficients_id = Column(Integer, primary_key=True, autoincrement=True)
    approximation_id = Column(Integer, ForeignKey('approximations.approximation_id', ondelete="CASCADE"), nullable=False)
    upper_value = Column(Float, nullable=False)
    lower_value = Column(Float, nullable=False)

    approximation = relationship("Approximation", back_populates="legendre_coefficients")

    def __repr__(self):
        return f"<LegendreCoefficient(id={self.legendre_coefficients_id}, upper={self.upper_value}, lower={self.lower_value})>"


# --------------------------------------------------------------------------
# Таблица 11: Transformed_coordinates (Преобразованные координаты)
# --------------------------------------------------------------------------
class TransformedCoordinate(Base):
    __tablename__ = 'transformed_coordinates'

    transformed_coordinates_id = Column(Integer, primary_key=True, autoincrement=True)
    approximation_id = Column(Integer, ForeignKey('approximations.approximation_id', ondelete="CASCADE"), nullable=False)
    profile_type = Column(Text, nullable=False)
    x_transformed = Column(Float, nullable=False)
    y_transformed = Column(Float, nullable=False)

    approximation = relationship("Approximation", back_populates="transformed_coordinates")

    def __repr__(self):
        return f"<TransformedCoordinate(id={self.transformed_coordinates_id}, type='{self.profile_type}')>"