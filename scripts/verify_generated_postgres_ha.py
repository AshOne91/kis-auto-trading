from __future__ import annotations

import json
import os
import subprocess
import time
from uuid import uuid4

COMPOSE_FILE = "environment/compose.integration.yml"
PORT_BASE = 59300
POSTGRES_PORT = PORT_BASE + 10
MAX_ATTEMPTS = 120
RETRY_SECONDS = 1.0
PATRONI_SERVICES = ("postgres-ha-0", "postgres-ha-1", "postgres-ha-2")


class GeneratedEnvironment:
    def __init__(self) -> None:
        self.project_name = f"generated-postgres-ha-test-{uuid4().hex[:8]}"
        self.command = (
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "-f",
            COMPOSE_FILE,
        )
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "LOCAL_BIND_ADDRESS": "127.0.0.1",
                "POSTGRES_USER": "autoforge",
                "POSTGRES_PASSWORD": "change-me",
                "POSTGRES_REPLICATION_PASSWORD": "change-me-replication",
                "POSTGRES_PORT": str(POSTGRES_PORT),
                "RABBITMQ_URL": "amqp://autoforge:change-me@rabbitmq:5672/",
                "DURABLE_JOB_API_TOKEN": "generated-postgres-ha-test-token",
            }
        )

    def run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            (*self.command, *arguments),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.environment,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(
                f"Compose command failed: {arguments!r}\n{result.stdout}\n{result.stderr}"
            )
        return result

    def close(self) -> None:
        try:
            self.run("down", "--volumes", "--remove-orphans")
        except RuntimeError as error:
            print(f"isolated Compose cleanup failed for {self.project_name}: {error}")


def _cluster(environment: GeneratedEnvironment) -> dict[str, object]:
    last_error: RuntimeError | None = None
    for service in PATRONI_SERVICES:
        try:
            result = environment.run(
                "exec", "-T", service, "curl", "-fsS", "http://localhost:8008/cluster"
            )
            return json.loads(result.stdout)
        except RuntimeError as error:
            last_error = error
    raise RuntimeError("No Patroni member responded to the cluster query") from last_error


def _leader_and_streaming_replicas(
    environment: GeneratedEnvironment,
    *,
    expected_members: int,
    expected_streaming_replicas: int,
) -> tuple[str, int]:
    last_members: object = None
    for _ in range(MAX_ATTEMPTS):
        try:
            members = _cluster(environment).get("members", [])
            leaders = [member for member in members if member.get("role") == "leader"]
            streaming = [
                member
                for member in members
                if member.get("state") == "streaming"
                and member.get("role") in {"replica", "sync_standby"}
            ]
            last_members = members
            if (
                len(members) == expected_members
                and len(leaders) == 1
                and len(streaming) == expected_streaming_replicas
            ):
                return str(leaders[0]["host"]), len(streaming)
        except RuntimeError:
            pass
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        "Patroni cluster did not reach the expected topology: "
        f"members={last_members!r}"
    )


def _wait_for_writer(environment: GeneratedEnvironment) -> None:
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        for service in PATRONI_SERVICES:
            try:
                result = environment.run(
                    "exec",
                    "-T",
                    "-e",
                    "PGPASSWORD=change-me",
                    "-e",
                    "PGCONNECT_TIMEOUT=3",
                    service,
                    "psql",
                    "-h",
                    "postgres",
                    "-U",
                    "autoforge",
                    "-d",
                    "identity",
                    "-At",
                    "-c",
                    "SELECT current_user || ':' || pg_is_in_recovery()",
                )
                if result.stdout.strip() == "autoforge:false":
                    return
            except RuntimeError as error:
                last_error = error
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("HAProxy did not reach a writable PostgreSQL leader") from last_error


def main() -> None:
    environment = GeneratedEnvironment()
    try:
        print(f"starting isolated PostgreSQL HA environment: {environment.project_name}")
        environment.run("up", "--build", "--detach", "migrate")
        environment.run("wait", "migrate")
        original_leader, replicas = _leader_and_streaming_replicas(
            environment, expected_members=3, expected_streaming_replicas=2
        )
        if replicas != 2:
            raise RuntimeError(f"Expected two streaming replicas, got {replicas}")
        _wait_for_writer(environment)

        environment.run("stop", original_leader)
        promoted_leader, replicas = _leader_and_streaming_replicas(
            environment, expected_members=2, expected_streaming_replicas=1
        )
        if promoted_leader == original_leader or replicas != 1:
            raise RuntimeError(
                "PostgreSQL leader did not fail over to one remaining streaming replica"
            )
        _wait_for_writer(environment)

        environment.run("up", "--detach", "--wait", original_leader)
        restored_leader, replicas = _leader_and_streaming_replicas(
            environment, expected_members=3, expected_streaming_replicas=2
        )
        if restored_leader != promoted_leader or replicas != 2:
            raise RuntimeError("Stopped PostgreSQL node did not rejoin as a replica")
        print(
            "Generated PostgreSQL HA verified: "
            f"{original_leader} stopped -> {promoted_leader} promoted -> "
            f"{original_leader} rejoined"
        )
    finally:
        environment.close()


if __name__ == "__main__":
    main()
