from __future__ import annotations

import subprocess
import time
from pathlib import Path

from verify_generated_postgres_ha import (
    MAX_ATTEMPTS,
    RETRY_SECONDS,
    GeneratedEnvironment,
    _workspace_from_arguments,
)

WORKER_SERVICE = "durable-job-worker"
EXPECTED_REPLICAS = 2


def _worker_containers(
    environment: GeneratedEnvironment, *, expected: int
) -> list[str]:
    result = environment.run("ps", "--quiet", WORKER_SERVICE)
    containers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(containers) != expected:
        raise RuntimeError(
            f"Expected {expected} running Durable Job Workers, got {containers!r}"
        )
    return containers


def _health_status(environment: GeneratedEnvironment, container: str) -> str:
    result = subprocess.run(
        ("docker", "inspect", "--format", "{{.State.Health.Status}}", container),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment.environment,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(
            f"Could not inspect Worker {container}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _wait_for_workers(
    environment: GeneratedEnvironment, *, expected: int
) -> list[str]:
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            containers = _worker_containers(environment, expected=expected)
            statuses = [_health_status(environment, container) for container in containers]
            if all(status == "healthy" for status in statuses):
                return containers
            last_error = RuntimeError(
                f"Worker health is {dict(zip(containers, statuses, strict=True))!r}"
            )
        except RuntimeError as error:
            last_error = error
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        f"Generated Durable Job Worker replicas did not reach healthy state: {last_error}"
    ) from last_error


def _stop_worker(environment: GeneratedEnvironment, container: str) -> None:
    result = subprocess.run(
        ("docker", "stop", container),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment.environment,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f"Could not stop Worker {container}: {result.stderr.strip()}")


def _enable_generated_worker_replicas(
    environment: GeneratedEnvironment, workspace: Path
) -> None:
    override = workspace / "deploy" / "single-host" / "compose.override.yml"
    source = override.read_text(encoding="utf-8")
    expected = "  durable-job-worker:\n    deploy:\n      replicas: 2\n"
    if expected not in source:
        raise RuntimeError(
            "The generated HA workspace must configure two Durable Job Worker replicas"
        )
    environment.command = (*environment.command, "-f", str(override))


def main() -> None:
    workspace = _workspace_from_arguments(
        description="Verify Durable Job Worker replica recovery in a generated HA workspace."
    )
    environment = GeneratedEnvironment(workspace)
    try:
        _enable_generated_worker_replicas(environment, workspace)
        print(
            f"starting isolated Durable Job Worker HA environment: {environment.project_name}"
        )
        environment.run("up", "--build", "--detach", "--wait", WORKER_SERVICE)
        workers = _wait_for_workers(environment, expected=EXPECTED_REPLICAS)
        stopped_worker, surviving_worker = workers

        _stop_worker(environment, stopped_worker)
        surviving = _wait_for_workers(environment, expected=1)
        if surviving != [surviving_worker]:
            raise RuntimeError("The surviving Durable Job Worker was unexpectedly recreated")

        environment.run("up", "--detach", "--wait", WORKER_SERVICE)
        _wait_for_workers(environment, expected=EXPECTED_REPLICAS)
        print(
            "Generated Durable Job Worker HA verified: one of two healthy workers "
            "stopped, the other stayed healthy, then the stopped worker rejoined"
        )
    finally:
        environment.close()


if __name__ == "__main__":
    main()
