from typing import Literal

from pydantic import BaseModel, Field, model_validator

Vector = tuple[float, float]


class SimulationRequest(BaseModel):
    central_body: str = Field(default="Earth", min_length=1, max_length=80)
    gravitational_parameter: float = Field(default=3.986004418e14, ge=1e6, le=2e15)
    initial_position: Vector = (7_000_000.0, 0.0)
    initial_velocity: Vector = (0.0, 7546.053290107542)
    duration_seconds: float = Field(default=5828.516637686015, gt=0, le=2_592_000)
    step_seconds: float = Field(default=10.0, gt=0, le=3600)
    integrators: tuple[Literal["rk4", "velocity_verlet"], ...] = ("rk4", "velocity_verlet")

    @model_validator(mode="after")
    def bounded_scenario(self) -> "SimulationRequest":
        radius = sum(component * component for component in self.initial_position) ** 0.5
        speed = sum(component * component for component in self.initial_velocity) ** 0.5
        if not 1_000 <= radius <= 1e10:
            raise ValueError("initial radius must be between 1 km and 10 million km")
        if speed > 1e7:
            raise ValueError("initial speed must not exceed 10,000 km/s")
        if self.duration_seconds / self.step_seconds > 20_000:
            raise ValueError("scenario must not exceed 20,000 integration steps")
        if len(set(self.integrators)) != len(self.integrators) or not self.integrators:
            raise ValueError("select one or two unique integrators")
        return self


class Sample(BaseModel):
    time_seconds: float
    position: Vector
    velocity: Vector
    specific_energy: float


class IntegrationResult(BaseModel):
    integrator: str
    samples: list[Sample]
    max_relative_energy_drift: float


class ComparisonMetrics(BaseModel):
    final_position_delta_m: float | None
    final_velocity_delta_mps: float | None


class SimulationResult(BaseModel):
    scenario: SimulationRequest
    runs: dict[str, IntegrationResult]
    comparison: ComparisonMetrics


class SavedScenario(BaseModel):
    scenario_id: str
    created: bool
    share_path: str
    request: SimulationRequest
    result: SimulationResult
    lineage: dict[str, str | int]
