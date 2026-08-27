import csv
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .schemas import SavedScenario, SimulationRequest, SimulationResult

SCHEMA_VERSION = 1
ALGORITHM_VERSION = "two-body-1"


class ScenarioStore:
    def __init__(self, path: Path):
        self.path = path
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    lineage_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    @staticmethod
    def scenario_id(request: SimulationRequest) -> str:
        canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:20]

    def save(self, request: SimulationRequest, result: SimulationResult) -> SavedScenario:
        scenario_id = self.scenario_id(request)
        lineage: dict[str, str | int] = {
            "schema_version": SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "input_sha256": hashlib.sha256(
                request.model_dump_json().encode()
            ).hexdigest(),
            "central_body": request.central_body,
        }
        created_at = datetime.now(UTC).isoformat()
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO scenarios
                (scenario_id, request_json, result_json, lineage_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    scenario_id,
                    request.model_dump_json(),
                    result.model_dump_json(),
                    json.dumps(lineage, sort_keys=True),
                    created_at,
                ),
            )
            created = cursor.rowcount == 1
            connection.commit()
        saved = self.get(scenario_id)
        return saved.model_copy(update={"created": created})

    def get(self, scenario_id: str) -> SavedScenario:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM scenarios WHERE scenario_id = ?", (scenario_id,)
            ).fetchone()
        if row is None:
            raise KeyError(scenario_id)
        return SavedScenario(
            scenario_id=scenario_id,
            created=False,
            share_path=f"/scenarios/{scenario_id}",
            request=SimulationRequest.model_validate_json(row["request_json"]),
            result=SimulationResult.model_validate_json(row["result_json"]),
            lineage=json.loads(row["lineage_json"]),
        )

    def export_csv(self, scenario_id: str) -> str:
        saved = self.get(scenario_id)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            ["scenario_id", "integrator", "time_seconds", "x_m", "y_m", "vx_mps", "vy_mps", "specific_energy"]
        )
        for name, run in saved.result.runs.items():
            for sample in run.samples:
                writer.writerow(
                    [
                        scenario_id,
                        name,
                        sample.time_seconds,
                        *sample.position,
                        *sample.velocity,
                        sample.specific_energy,
                    ]
                )
        return output.getvalue()
