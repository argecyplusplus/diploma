from sqlalchemy import Column, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from base import Base


# --------------------------------------------------------------------------
# Таблица 25: Materials (Материалы)
# --------------------------------------------------------------------------
class Material(Base):
    __tablename__ = 'materials'

    material_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    density = Column(Float, nullable=False)
    hardness = Column(Float, nullable=True)
    thermal_conductivity = Column(Float, nullable=False)
    heat_capacity = Column(Float, nullable=False)
    melting_point = Column(Float, nullable=True)
    thermal_expansion_coef = Column(Float, nullable=False)

    # Отношения к зависимым таблицам
    alloy_compositions_as_alloy = relationship(
        "AlloyComposition", foreign_keys="[AlloyComposition.alloy_id]",
        back_populates="alloy", cascade="all, delete-orphan"
    )
    alloy_compositions_as_component = relationship(
        "AlloyComposition", foreign_keys="[AlloyComposition.component_material_id]",
        back_populates="component_material"
    )
    chemical_elements = relationship("ChemicalElement", back_populates="material", cascade="all, delete-orphan")
    el_values = relationship("ElValue", back_populates="material", cascade="all, delete-orphan")

    # Связи с модулем симуляций (будут активированы после добавления back_populates в simulation.py)
    simulation_materials = relationship("SimulationMaterial", back_populates="material")
    initial_temperatures = relationship("InitialTemperature", back_populates="material")

    def __repr__(self):
        return f"<Material(id={self.material_id}, name='{self.name}', type='{self.type}')>"


# --------------------------------------------------------------------------
# Таблица 26: Alloy_compositions (Состав сплавов)
# --------------------------------------------------------------------------
class AlloyComposition(Base):
    __tablename__ = 'alloy_compositions'

    alloy_composition_id = Column(Integer, primary_key=True, autoincrement=True)

    # Два внешних ключа на одну и ту же таблицу materials
    alloy_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="CASCADE"),
        nullable=False
    )
    component_material_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="RESTRICT"),
        nullable=False
    )
    mass_fraction = Column(Float, nullable=False)

    # Явное указание foreign_keys необходимо, т.к. обе связи ведут к Material
    alloy = relationship("Material", foreign_keys=[alloy_id], back_populates="alloy_compositions_as_alloy")
    component_material = relationship("Material", foreign_keys=[component_material_id],
                                      back_populates="alloy_compositions_as_component")

    def __repr__(self):
        return f"<AlloyComposition(alloy_id={self.alloy_id}, component_id={self.component_material_id})>"


# --------------------------------------------------------------------------
# Таблица 27: Chemical_elements (Химические элементы)
# --------------------------------------------------------------------------
class ChemicalElement(Base):
    __tablename__ = 'chemical_elements'

    chemical_element_id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    material_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="CASCADE"),
        nullable=False
    )

    material = relationship("Material", back_populates="chemical_elements")

    def __repr__(self):
        return f"<ChemicalElement(id={self.chemical_element_id}, symbol='{self.symbol}')>"


# --------------------------------------------------------------------------
# Таблица 28: El_values (Значения упругости)
# --------------------------------------------------------------------------
class ElValue(Base):
    __tablename__ = 'el_values'

    el_values_id = Column(Integer, primary_key=True, autoincrement=True)
    elasticity_parameters_id = Column(
        Integer,
        ForeignKey('elasticity_parameters.elasticity_parameters_id', ondelete="CASCADE"),
        nullable=False
    )
    material_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="CASCADE"),
        nullable=False
    )
    value = Column(Float, nullable=False)

    elasticity_parameters = relationship("ElasticityParameter", back_populates="el_values")
    material = relationship("Material", back_populates="el_values")

    def __repr__(self):
        return f"<ElValue(id={self.el_values_id}, value={self.value})>"