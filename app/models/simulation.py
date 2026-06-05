import datetime
from sqlalchemy import Column, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


# Вспомогательная функция для генерации даты в нужном формате
def get_current_time():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# Таблица 14: Simulations (Моделирование)
class Simulation(Base):
    __tablename__ = 'simulations'

    simulation_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="created")  # created, queued, running, completed, failed
    progress = Column(Integer, nullable=False, default=0)  # 0..100, опционально
    error_message = Column(Text, nullable=True)
    task_type = Column(Text, nullable=False, default="task1")

    blade_assembly_id = Column(
        Integer,
        ForeignKey('blade_assemblies.blade_assembly_id', ondelete="CASCADE"),
        nullable=True
    )
    blade_id = Column(
        Integer,
        ForeignKey('blades.blade_id', ondelete="CASCADE"),
        nullable=True
    )
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )

    assembly = relationship("BladeAssembly", back_populates="simulations")
    blade = relationship("Blade", back_populates="simulations")
    initial_conditions = relationship("InitialCondition", back_populates="simulations")

    tasks = relationship("SimulationTask", back_populates="simulation", cascade="all, delete-orphan")
    results = relationship("SimulationResult", back_populates="simulation", cascade="all, delete-orphan")
    materials = relationship("SimulationMaterial", back_populates="simulation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Simulation(id={self.simulation_id}, name='{self.name}')>"


# Таблица 13: Simulation_tasks (Задачи симуляции)
class SimulationTask(Base):
    __tablename__ = 'simulation_tasks'

    simulation_task_id = Column(Integer, primary_key=True, autoincrement=True)

    simulation_id = Column(
        Integer,
        ForeignKey('simulations.simulation_id', ondelete="CASCADE"),
        nullable=False
    )

    task_value = Column(Float, nullable=False)
    description = Column(Text, nullable=True)

    simulation = relationship("Simulation", back_populates="tasks")

    def __repr__(self):
        return f"<SimulationTask(id={self.simulation_task_id}, value={self.task_value})>"


# Таблица 12: Simulation_results (Результаты симуляции)
class SimulationResult(Base):
    __tablename__ = 'simulation_results'

    result_id = Column(Integer, primary_key=True, autoincrement=True)

    simulation_id = Column(
        Integer,
        ForeignKey('simulations.simulation_id', ondelete="CASCADE"),
        nullable=False
    )

    file_type = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False, default=get_current_time)

    simulation = relationship("Simulation", back_populates="results")

    def __repr__(self):
        return f"<SimulationResult(id={self.result_id}, type='{self.file_type}')>"


# Таблица 15: Simulation_materials (Материалы моделирования)
class SimulationMaterial(Base):
    __tablename__ = 'simulation_materials'

    simulation_materials_id = Column(Integer, primary_key=True, autoincrement=True)

    simulation_id = Column(
        Integer,
        ForeignKey('simulations.simulation_id', ondelete="CASCADE"),
        nullable=False
    )

    material_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="RESTRICT"),
        nullable=False
    )

    created_at = Column(Text, nullable=True, default=get_current_time)

    simulation = relationship("Simulation", back_populates="materials")
    material = relationship("Material", back_populates="simulation_materials")

    def __repr__(self):
        return f"<SimulationMaterial(sim_id={self.simulation_id}, mat_id={self.material_id})>"


# Таблица 16: Time_parameters (Временные параметры)
class TimeParameter(Base):
    __tablename__ = 'time_parameters'

    time_parameters_id = Column(Integer, primary_key=True, autoincrement=True)

    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )

    time = Column(Float, nullable=False)
    dt = Column(Float, nullable=False)
    nbT = Column(Float, nullable=False)
    Nplot = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="time_parameters")

    def __repr__(self):
        return f"<TimeParameter(id={self.time_parameters_id}, time={self.time})>"


# Таблица 17: Blade_chord (Хорда лопатки)
class BladeChord(Base):
    __tablename__ = 'blade_chord'

    blade_chord_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    name = Column(Text, nullable=False)
    value = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="blade_chords")

    def __repr__(self):
        return f"<BladeChord(id={self.blade_chord_id}, name='{self.name}')>"


# Таблица 18: Initial_conditions (Начальные условия)
class InitialCondition(Base):
    __tablename__ = 'initial_conditions'

    initial_conditions_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

    simulations = relationship("Simulation", back_populates="initial_conditions")

    blade_chords = relationship("BladeChord", back_populates="initial_conditions", cascade="all, delete-orphan")

    time_parameters = relationship("TimeParameter", back_populates="initial_conditions", cascade="all, delete-orphan")
    potential_flow_parameters = relationship("PotentialFlowParameter", back_populates="initial_conditions",
                                             cascade="all, delete-orphan")
    boundary_identifiers = relationship("BoundaryIdentifier", back_populates="initial_conditions",
                                        cascade="all, delete-orphan")
    elasticity_parameters = relationship("ElasticityParameter", back_populates="initial_conditions",
                                         cascade="all, delete-orphan")
    construction_parameters = relationship("ConstructionParameter", back_populates="initial_conditions",
                                           cascade="all, delete-orphan")
    initial_temperatures = relationship("InitialTemperature", back_populates="initial_conditions",
                                        cascade="all, delete-orphan")
    stress_output_parameters = relationship("StressOutputParameter", back_populates="initial_conditions",
                                            cascade="all, delete-orphan")

    # Новые связи для задачи 4
    gas_flow_parameters = relationship("GasFlowParameter", back_populates="initial_conditions",
                                       cascade="all, delete-orphan", uselist=False)
    material_properties = relationship("MaterialProperty", back_populates="initial_conditions",
                                      cascade="all, delete-orphan", uselist=False)
    gas_properties = relationship("GasProperty", back_populates="initial_conditions",
                                 cascade="all, delete-orphan", uselist=False)

    def __repr__(self):
        return f"<InitialCondition(id={self.initial_conditions_id}, name='{self.name}')>"


# Таблица 19: Potential_flow_parameters (Параметры потенциального потока)
class PotentialFlowParameter(Base):
    __tablename__ = 'potential_flow_parameters'

    potential_flow_parameters_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    beta = Column(Float, nullable=False)
    B = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="potential_flow_parameters")

    def __repr__(self):
        return f"<PotentialFlowParameter(id={self.potential_flow_parameters_id}, beta={self.beta})>"


# Таблица 20: Boundary_identifiers (Идентификаторы границ)
class BoundaryIdentifier(Base):
    __tablename__ = 'boundary_identifiers'

    boundary_identifiers_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    name = Column(Text, nullable=False)
    value = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="boundary_identifiers")

    def __repr__(self):
        return f"<BoundaryIdentifier(id={self.boundary_identifiers_id}, name='{self.name}')>"


# Таблица 21: Elasticity_parameters (Параметры упругости)
class ElasticityParameter(Base):
    __tablename__ = 'elasticity_parameters'

    elasticity_parameters_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    b = Column(Float, nullable=False)
    nu = Column(Float, nullable=False)
    KLT = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="elasticity_parameters")
    el_values = relationship("ElValue", back_populates="elasticity_parameters", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ElasticityParameter(id={self.elasticity_parameters_id}, nu={self.nu})>"


# Таблица 22: Construction_parameters (Параметры для построения)
class ConstructionParameter(Base):
    __tablename__ = 'construction_parameters'

    construction_parameters_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    NC = Column(Integer, nullable=False)
    NSp = Column(Integer, nullable=False)
    NSm = Column(Integer, nullable=False)
    NSpn = Column(Integer, nullable=False)
    NSpm = Column(Integer, nullable=False)
    dely_offset = Column(Float, nullable=True, default=0.003)

    initial_conditions = relationship("InitialCondition", back_populates="construction_parameters")

    def __repr__(self):
        return f"<ConstructionParameter(id={self.construction_parameters_id}, NC={self.NC})>"


# Таблица 23: Initial_temperature (Начальная температура)
class InitialTemperature(Base):
    __tablename__ = 'initial_temperature'

    initial_temperature_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    material_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="CASCADE"),
        nullable=False
    )
    value = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="initial_temperatures")
    material = relationship("Material", back_populates="initial_temperatures")

    def __repr__(self):
        return f"<InitialTemperature(id={self.initial_temperature_id}, value={self.value})>"


# Таблица 24: Stress_output_parameters (Параметры вывода напряжений)
class StressOutputParameter(Base):
    __tablename__ = 'stress_output_parameters'

    stress_output_parameters_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    coef = Column(Float, nullable=False)
    delt = Column(Float, nullable=False)
    Npt = Column(Float, nullable=False)

    initial_conditions = relationship("InitialCondition", back_populates="stress_output_parameters")

    def __repr__(self):
        return f"<StressOutputParameter(id={self.stress_output_parameters_id}, coef={self.coef})>"


# Таблица 29: Gas_flow_parameters
class GasFlowParameter(Base):
    __tablename__ = 'gas_flow_parameters'

    gas_flow_parameters_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    Tgas = Column(Float, nullable=False, default=673.0, comment="Температура газа, °C")
    Tcool = Column(Float, nullable=False, default=1223.0, comment="Температура охладителя, °C")
    U0 = Column(Float, nullable=False, default=1.0, comment="Скорость потока, м/с")
    beta = Column(Float, nullable=False, default=-10.0, comment="Угол атаки, градусы")
    Press0 = Column(Float, nullable=False, default=1.5e6, comment="Давление на входе, Па")
    houter = Column(Float, nullable=False, default=15000.0, comment="Коэф. теплоотдачи внешней поверхности, Вт/(м²·K)")
    hinner = Column(Float, nullable=False, default=15.0, comment="Коэф. теплоотдачи внутренней поверхности, Вт/(м²·K)")

    initial_conditions = relationship("InitialCondition", back_populates="gas_flow_parameters")

    def __repr__(self):
        return f"<GasFlowParameter(id={self.gas_flow_parameters_id})>"


# Таблица 30: Material_properties
class MaterialProperty(Base):
    __tablename__ = 'material_properties'

    material_properties_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    rhosteel = Column(Float, nullable=False, default=8200.0, comment="Плотность, кг/м³")
    cpsteel = Column(Float, nullable=False, default=500.0, comment="Удельная теплоемкость, Дж/(кг·К)")
    ksteel = Column(Float, nullable=False, default=90.5, comment="Теплопроводность, Вт/(м·К)")
    a_steel = Column(Float, nullable=True)
    a_air = Column(Float, nullable=True)

    initial_conditions = relationship("InitialCondition", back_populates="material_properties")

    def __repr__(self):
        return f"<MaterialProperty(id={self.material_properties_id})>"


# Таблица 31: Gas_properties 
class GasProperty(Base):
    __tablename__ = 'gas_properties'

    gas_properties_id = Column(Integer, primary_key=True, autoincrement=True)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )
    Rgas = Column(Float, nullable=False, default=287.0, comment="Газовая постоянная, Дж/(кг·К)")
    cpgas = Column(Float, nullable=False, default=1150.0, comment="Удельная теплоемкость газа, Дж/(кг·К)")
    kgas = Column(Float, nullable=False, default=0.08, comment="Теплопроводность газа, Вт/(м·К)")

    initial_conditions = relationship("InitialCondition", back_populates="gas_properties")

    def __repr__(self):
        return f"<GasProperty(id={self.gas_properties_id})>"