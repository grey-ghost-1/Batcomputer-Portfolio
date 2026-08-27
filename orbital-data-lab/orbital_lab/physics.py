import math

from .schemas import ComparisonMetrics, IntegrationResult, Sample, SimulationRequest, SimulationResult

Vector = tuple[float, float]
State = tuple[float, float, float, float]


def add(left: Vector, right: Vector) -> Vector:
    return left[0] + right[0], left[1] + right[1]


def scale(vector: Vector, factor: float) -> Vector:
    return vector[0] * factor, vector[1] * factor


def norm(vector: Vector) -> float:
    return math.hypot(*vector)


def acceleration(position: Vector, mu: float) -> Vector:
    radius = norm(position)
    factor = -mu / radius**3
    return scale(position, factor)


def specific_energy(position: Vector, velocity: Vector, mu: float) -> float:
    return 0.5 * norm(velocity) ** 2 - mu / norm(position)


def derivative(state: State, mu: float) -> State:
    ax, ay = acceleration((state[0], state[1]), mu)
    return state[2], state[3], ax, ay


def state_add(state: State, delta: State, factor: float) -> State:
    return tuple(state[index] + factor * delta[index] for index in range(4))  # type: ignore[return-value]


def rk4_step(state: State, dt: float, mu: float) -> State:
    k1 = derivative(state, mu)
    k2 = derivative(state_add(state, k1, dt / 2), mu)
    k3 = derivative(state_add(state, k2, dt / 2), mu)
    k4 = derivative(state_add(state, k3, dt), mu)
    return tuple(
        state[index] + dt * (k1[index] + 2 * k2[index] + 2 * k3[index] + k4[index]) / 6
        for index in range(4)
    )  # type: ignore[return-value]


def verlet_step(state: State, dt: float, mu: float) -> State:
    position = state[0], state[1]
    velocity = state[2], state[3]
    initial_acceleration = acceleration(position, mu)
    next_position = add(add(position, scale(velocity, dt)), scale(initial_acceleration, 0.5 * dt**2))
    next_acceleration = acceleration(next_position, mu)
    next_velocity = add(velocity, scale(add(initial_acceleration, next_acceleration), 0.5 * dt))
    return next_position[0], next_position[1], next_velocity[0], next_velocity[1]


def integrate(request: SimulationRequest, integrator: str) -> IntegrationResult:
    state: State = (*request.initial_position, *request.initial_velocity)
    initial_energy = specific_energy(request.initial_position, request.initial_velocity, request.gravitational_parameter)
    samples: list[Sample] = []
    elapsed = 0.0
    stepper = rk4_step if integrator == "rk4" else verlet_step
    while True:
        position = state[0], state[1]
        velocity = state[2], state[3]
        energy = specific_energy(position, velocity, request.gravitational_parameter)
        samples.append(
            Sample(
                time_seconds=elapsed,
                position=position,
                velocity=velocity,
                specific_energy=energy,
            )
        )
        if elapsed >= request.duration_seconds:
            break
        dt = min(request.step_seconds, request.duration_seconds - elapsed)
        state = stepper(state, dt, request.gravitational_parameter)
        elapsed += dt
    drift = max(abs(sample.specific_energy - initial_energy) for sample in samples) / abs(initial_energy)
    return IntegrationResult(
        integrator=integrator,
        samples=samples,
        max_relative_energy_drift=drift,
    )


def simulate(request: SimulationRequest) -> SimulationResult:
    runs = {name: integrate(request, name) for name in request.integrators}
    position_delta = velocity_delta = None
    if len(runs) == 2:
        first, second = runs.values()
        position_delta = norm(
            (
                first.samples[-1].position[0] - second.samples[-1].position[0],
                first.samples[-1].position[1] - second.samples[-1].position[1],
            )
        )
        velocity_delta = norm(
            (
                first.samples[-1].velocity[0] - second.samples[-1].velocity[0],
                first.samples[-1].velocity[1] - second.samples[-1].velocity[1],
            )
        )
    return SimulationResult(
        scenario=request,
        runs=runs,
        comparison=ComparisonMetrics(
            final_position_delta_m=position_delta,
            final_velocity_delta_mps=velocity_delta,
        ),
    )
