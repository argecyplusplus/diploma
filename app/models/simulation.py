import datetime
from sqlalchemy import Column, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from base import Base


# Вспомогательная функция для генерации даты в нужном формате
def get_current_time():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# --------------------------------------------------------------------------
# Таблица 14: Simulations (Моделирование)
# --------------------------------------------------------------------------
class Simulation(Base):
    __tablename__ = 'simulations'

    # Первичный ключ
    simulation_id = Column(Integer, primary_key=True, autoincrement=True)
    # Наименование моделирования
    name = Column(Text, nullable=False)

    # Внешние ключи
    blade_assembly_id = Column(
        Integer,
        ForeignKey('blade_assemblies.blade_assembly_id', ondelete="CASCADE"),
        nullable=False
    )
    blade_id = Column(
        Integer,
        ForeignKey('blades.blade_id', ondelete="CASCADE"),
        nullable=False
    )
    # Ссылка на начальные условия (класс InitialCondition будет создан в следующем шаге)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )

    # Отношения (Relationships)
    assembly = relationship("BladeAssembly", back_populates="simulations")
    blade = relationship("Blade", back_populates="simulations")
    initial_conditions = relationship("InitialCondition", back_populates="simulations", cascade="all, delete-orphan")


    # Связи с дочерними таблицами (задачи и результаты)
    tasks = relationship("SimulationTask", back_populates="simulation", cascade="all, delete-orphan")
    results = relationship("SimulationResult", back_populates="simulation", cascade="all, delete-orphan")
    materials = relationship("SimulationMaterial", back_populates="simulation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Simulation(id={self.simulation_id}, name='{self.name}')>"


# --------------------------------------------------------------------------
# Таблица 13: Simulation_tasks (Задачи симуляции)
# --------------------------------------------------------------------------
class SimulationTask(Base):
    __tablename__ = 'simulation_tasks'

    # Первичный ключ
    simulation_task_id = Column(Integer, primary_key=True, autoincrement=True)

    # Внешний ключ на Моделирование
    simulation_id = Column(
        Integer,
        ForeignKey('simulations.simulation_id', ondelete="CASCADE"),
        nullable=False
    )

    # Значение параметра задачи (REAL -> Float)
    task_value = Column(Float, nullable=False)
    # Описание (может быть пустым)
    description = Column(Text, nullable=True)

    # Обратная связь
    simulation = relationship("Simulation", back_populates="tasks")

    def __repr__(self):
        return f"<SimulationTask(id={self.simulation_task_id}, value={self.task_value})>"


# --------------------------------------------------------------------------
# Таблица 12: Simulation_results (Результаты симуляции)
# --------------------------------------------------------------------------
class SimulationResult(Base):
    __tablename__ = 'simulation_results'

    # Первичный ключ
    result_id = Column(Integer, primary_key=True, autoincrement=True)

    # Внешний ключ на Моделирование
    simulation_id = Column(
        Integer,
        ForeignKey('simulations.simulation_id', ondelete="CASCADE"),
        nullable=False
    )

    # Тип файла (например, .csv, .vtk)
    file_type = Column(Text, nullable=False)
    # Путь к файлу
    file_path = Column(Text, nullable=False)
    # Описание результата
    description = Column(Text, nullable=True)
    # Дата создания (TEXT, формат YYYY-MM-DD HH:MM:SS)
    created_at = Column(Text, nullable=False, default=get_current_time)

    # Обратная связь
    simulation = relationship("Simulation", back_populates="results")

    def __repr__(self):
        return f"<SimulationResult(id={self.result_id}, type='{self.file_type}')>"


# --------------------------------------------------------------------------
# Таблица 15: Simulation_materials (Материалы моделирования)
# --------------------------------------------------------------------------
class SimulationMaterial(Base):
    __tablename__ = 'simulation_materials'

    # Первичный ключ (так как это Association Object с доп. полем created_at)
    simulation_materials_id = Column(Integer, primary_key=True, autoincrement=True)

    # Внешний ключ на Моделирование (CASCADE: если симуляция удалена, связь тоже удаляется)
    simulation_id = Column(
        Integer,
        ForeignKey('simulations.simulation_id', ondelete="CASCADE"),
        nullable=False
    )

    # Внешний ключ на Материал (RESTRICT: если материал используется, его нельзя удалить)
    material_id = Column(
        Integer,
        ForeignKey('materials.material_id', ondelete="RESTRICT"),
        nullable=False
    )

    # Дата добавления (TEXT, nullable=True)
    created_at = Column(Text, nullable=True, default=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Обратные связи
    simulation = relationship("Simulation", back_populates="materials")
    material = relationship("Material", back_populates="simulation_materials")

    def __repr__(self):
        return f"<SimulationMaterial(sim_id={self.simulation_id}, mat_id={self.material_id})>"


# --------------------------------------------------------------------------
# Таблица 16: Time_parameters (Временные параметры)
# --------------------------------------------------------------------------
class TimeParameter(Base):
    __tablename__ = 'time_parameters'

    time_parameters_id = Column(Integer, primary_key=True, autoincrement=True)

    # Связь с Initial_conditions (CASCADE)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )

    time = Column(Float, nullable=False)
    dt = Column(Float, nullable=False)
    nbT = Column(Float, nullable=False)
    Nplot = Column(Float, nullable=False)

    # Обратная связь
    initial_conditions = relationship("InitialCondition", back_populates="time_parameters")

    def __repr__(self):
        return f"<TimeParameter(id={self.time_parameters_id}, time={self.time})>"


# --------------------------------------------------------------------------
# Таблица 17: Blade_chord (Хорда лопатки)
# --------------------------------------------------------------------------
class BladeChord(Base):
    __tablename__ = 'blade_chord'

    blade_chord_id = Column(Integer, primary_key=True, autoincrement=True)

    # Связь с Initial_conditions (CASCADE)
    initial_conditions_id = Column(
        Integer,
        ForeignKey('initial_conditions.initial_conditions_id', ondelete="CASCADE"),
        nullable=False
    )

    name = Column(Text, nullable=False)
    value = Column(Float, nullable=False)

    # Обратная связь
    initial_conditions = relationship("InitialCondition", back_populates="blade_chord")

    def __repr__(self):
        return f"<BladeChord(id={self.blade_chord_id}, name='{self.name}')>"


# --------------------------------------------------------------------------
# Обновлённая таблица 18: Initial_conditions (Начальные условия)
# Добавлены новые relationship для каскадного удаления зависимых параметров
# --------------------------------------------------------------------------
class InitialCondition(Base):
    __tablename__ = 'initial_conditions'

    initial_conditions_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

    # Каскадные связи с таблицами параметров
    time_parameters = relationship("TimeParameter", back_populates="initial_conditions", cascade="all, delete-orphan")
    blade_chords = relationship("BladeChord", back_populates="initial_conditions", cascade="all, delete-orphan")
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

    # Обратная связь с Simulation (добавьте в класс Simulation, если ещё не добавили)
    # simulations = relationship("Simulation", back_populates="initial_conditions")

    def __repr__(self):
        return f"<InitialCondition(id={self.initial_conditions_id}, name='{self.name}')>"


# --------------------------------------------------------------------------
# Таблица 19: Potential_flow_parameters (Параметры потенциального потока)
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Таблица 20: Boundary_identifiers (Идентификаторы границ)
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Таблица 21: Elasticity_parameters (Параметры упругости)
# --------------------------------------------------------------------------
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

# --------------------------------------------------------------------------
# Таблица 22: Construction_parameters (Параметры для построения)
# --------------------------------------------------------------------------
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

    initial_conditions = relationship("InitialCondition", back_populates="construction_parameters")

    def __repr__(self):
        return f"<ConstructionParameter(id={self.construction_parameters_id}, NC={self.NC})>"


# --------------------------------------------------------------------------
# Таблица 23: Initial_temperature (Начальная температура)
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Таблица 24: Stress_output_parameters (Параметры вывода напряжений)
# --------------------------------------------------------------------------
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