from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

COMPOSE_FILE = "environment/compose.integration.yml"
PORT_BASE = 59300
POSTGRES_PORT = PORT_BASE + 10
APPLICATION_PORT = PORT_BASE
RABBITMQ_AMQP_PORT = PORT_BASE + 30
RABBITMQ_MANAGEMENT_PORT = PORT_BASE + 31
AIRFLOW_PORT = PORT_BASE + 40
MAX_ATTEMPTS = 120
RETRY_SECONDS = 1.0
PATRONI_SERVICES = ("postgres-ha-0", "postgres-ha-1", "postgres-ha-2")
REDIS_SERVICES = tuple(f"redis-{port}" for port in range(7000, 7006))


class GeneratedEnvironment:
    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = (workspace or Path.cwd()).resolve()
        self.project_name = f"generated-postgres-ha-test-{uuid4().hex[:8]}"
        self.command = (
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "-f",
            str(self.workspace / COMPOSE_FILE),
        )
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "LOCAL_BIND_ADDRESS": "127.0.0.1",
                "POSTGRES_USER": "autoforge",
                "POSTGRES_PASSWORD": "change-me",
                "POSTGRES_REPLICATION_PASSWORD": "change-me-replication",
                "POSTGRES_PORT": str(POSTGRES_PORT),
                "APPLICATION_PORT": str(APPLICATION_PORT),
                "RABBITMQ_AMQP_PORT": str(RABBITMQ_AMQP_PORT),
                "RABBITMQ_MANAGEMENT_PORT": str(RABBITMQ_MANAGEMENT_PORT),
                "AIRFLOW_PORT": str(AIRFLOW_PORT),
                "AIRFLOW_FERNET_KEY": "bKR1MqFKfzQI29QbP21gQU6WkpYwIMVuZZt8Hq74gvs=",
                "RABBITMQ_URL": "amqp://autoforge:change-me@rabbitmq:5672/",
                "RABBITMQ_ERLANG_COOKIE": "generated-postgres-ha-test-cookie",
                "DURABLE_JOB_API_TOKEN": "generated-postgres-ha-test-token",
                "OPERATOR_API_TOKEN": "generated-postgres-ha-operator-token",
                "KIS_API_URL": "https://example.invalid",
                "KIS_APP_KEY": "generated-postgres-ha-test-key",
                "KIS_APP_SECRET": "generated-postgres-ha-test-secret",
                "KIS_ACCOUNT_NUMBER": "00000000",
                "KIS_ACCOUNT_PRODUCT_CODE": "01",
                "KIS_ACCOUNT_ENVIRONMENT": "demo",
            }
        )
        self.rag_network_name = self.environment.get(
            "RAG_NETWORK_NAME", "kis_auto_trading-rag"
        )
        self.environment["RAG_NETWORK_NAME"] = self.rag_network_name
        inspected = subprocess.run(
            ("docker", "network", "inspect", self.rag_network_name),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._owns_rag_network = inspected.returncode != 0
        if self._owns_rag_network:
            created = subprocess.run(
                ("docker", "network", "create", self.rag_network_name),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if created.returncode:
                raise RuntimeError(
                    f"Could not create RAG network {self.rag_network_name!r}: "
                    f"{created.stderr.strip()}"
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
        finally:
            if self._owns_rag_network:
                removed = subprocess.run(
                    ("docker", "network", "rm", self.rag_network_name),
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if removed.returncode:
                    print(
                        f"isolated RAG network cleanup failed for "
                        f"{self.rag_network_name}: {removed.stderr.strip()}"
                    )


def _workspace_from_arguments(
    *,
    description: str = "Verify PostgreSQL and Redis HA recovery in a generated HA workspace.",
) -> Path:
    parser = argparse.ArgumentParser(
        description=description
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Generated workspace from autoforge.ha.yaml (default: current directory).",
    )
    workspace = parser.parse_args().workspace.resolve()
    compose_file = workspace / COMPOSE_FILE
    if not compose_file.is_file():
        raise RuntimeError(f"Generated Compose file is missing: {compose_file}")
    compose_source = compose_file.read_text(encoding="utf-8")
    if "  postgres-ha-0:\n" not in compose_source or "  redis-7000:\n" not in compose_source:
        raise RuntimeError(
            "PostgreSQL and Redis HA are required. Generate a workspace from "
            "autoforge.ha.yaml and pass it with --workspace."
        )
    return workspace


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


def _wait_for_leaderless_replicas(environment: GeneratedEnvironment) -> None:
    last_members: object = None
    for _ in range(MAX_ATTEMPTS):
        try:
            members = _cluster(environment).get("members", [])
            leaders = [member for member in members if member.get("role") == "leader"]
            replicas = [
                member
                for member in members
                if member.get("role") == "replica" and member.get("state") == "running"
            ]
            last_members = members
            if len(members) == 3 and not leaders and len(replicas) == 3:
                return
        except RuntimeError:
            pass
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        "Patroni did not reach the expected leaderless replica state: "
        f"members={last_members!r}"
    )


def _member_name(environment: GeneratedEnvironment, service: str) -> str:
    members = _cluster(environment).get("members", [])
    member = next((item for item in members if item.get("host") == service), None)
    name = member.get("name") if isinstance(member, dict) else None
    if not isinstance(name, str) or not name:
        raise RuntimeError(f"Patroni member name was missing for {service}")
    return name


def _promote_explicit_candidate(
    environment: GeneratedEnvironment, candidate_service: str
) -> str:
    candidate_name = _member_name(environment, candidate_service)
    environment.run(
        "exec",
        "-T",
        candidate_service,
        "curl",
        "-fsS",
        "-X",
        "POST",
        "-H",
        "Content-Type: application/json",
        "-d",
        json.dumps({"candidate": candidate_name}),
        "http://localhost:8008/failover",
    )
    return candidate_name


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


def _wait_for_redis_cluster(environment: GeneratedEnvironment) -> None:
    last_topology: object = None
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            info = environment.run(
                "exec",
                "-T",
                REDIS_SERVICES[0],
                "redis-cli",
                "-p",
                "7000",
                "--raw",
                "cluster",
                "info",
            )
            values = {
                line.split(":", 1)[0]: line.split(":", 1)[1]
                for line in info.stdout.splitlines()
                if ":" in line
            }
            nodes_result = environment.run(
                "exec",
                "-T",
                REDIS_SERVICES[0],
                "redis-cli",
                "-p",
                "7000",
                "--raw",
                "cluster",
                "nodes",
            )
            nodes = [line.split() for line in nodes_result.stdout.splitlines()]
            connected = [node for node in nodes if len(node) >= 8 and node[7] == "connected"]
            masters = [
                node
                for node in connected
                if "master" in node[2] and "fail" not in node[2]
            ]
            replicas = [
                node
                for node in connected
                if ("slave" in node[2] or "replica" in node[2])
                and "fail" not in node[2]
            ]
            last_topology = values, nodes
            if (
                values.get("cluster_state") == "ok"
                and values.get("cluster_slots_assigned") == "16384"
                and len(masters) == 3
                and len(replicas) == 3
            ):
                return
        except RuntimeError as error:
            last_error = error
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        "Redis Cluster did not restore its expected topology after restart: "
        f"{last_topology!r}"
    ) from last_error


def _application_container(environment: GeneratedEnvironment) -> str:
    result = environment.run("ps", "-q", "application")
    containers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(containers) != 1:
        raise RuntimeError(f"Expected one application container, got {containers!r}")
    return containers[0]


def _wait_for_application(
    environment: GeneratedEnvironment,
    *,
    expected_container: str | None = None,
) -> str:
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            container = _application_container(environment)
            if expected_container and container != expected_container:
                raise RuntimeError(
                    "Application container was recreated during recovery"
                )
            health = subprocess.run(
                (
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    container,
                ),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if health.returncode or health.stdout.strip() != "healthy":
                raise RuntimeError(
                    f"Application container health is {health.stdout.strip()!r}"
                )
            with urlopen(
                f"http://127.0.0.1:{APPLICATION_PORT}/health", timeout=3
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"Application health returned {response.status}")
            return container
        except (RuntimeError, OSError) as error:
            last_error = (
                error if isinstance(error, RuntimeError) else RuntimeError(str(error))
            )
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("Generated application did not become healthy") from last_error


def main(workspace: Path) -> None:
    environment = GeneratedEnvironment(workspace)
    try:
        print(f"starting isolated PostgreSQL HA environment: {environment.project_name}")
        environment.run("up", "--build", "--detach", "application")
        _wait_for_redis_cluster(environment)
        application_container = _wait_for_application(environment)

        environment.run("restart", *REDIS_SERVICES)
        _wait_for_redis_cluster(environment)
        environment.run("rm", "-sf", "redis-cluster-init")
        environment.run("up", "--detach", "redis-cluster-init")
        environment.run("wait", "redis-cluster-init")
        _wait_for_application(environment, expected_container=application_container)

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
        _wait_for_application(environment, expected_container=application_container)

        environment.run("up", "--detach", "--wait", original_leader)
        restored_leader, replicas = _leader_and_streaming_replicas(
            environment, expected_members=3, expected_streaming_replicas=2
        )
        if restored_leader != promoted_leader or replicas != 2:
            raise RuntimeError("Stopped PostgreSQL node did not rejoin as a replica")

        candidate_service = "postgres-ha-0"
        environment.run("down")
        environment.run("up", "--detach", *PATRONI_SERVICES)
        _wait_for_leaderless_replicas(environment)
        candidate_name = _promote_explicit_candidate(environment, candidate_service)
        recovered_leader, replicas = _leader_and_streaming_replicas(
            environment, expected_members=3, expected_streaming_replicas=2
        )
        if recovered_leader != candidate_service or replicas != 2:
            raise RuntimeError(
                "Explicit Patroni failover did not promote the selected candidate"
            )
        environment.run("up", "--detach", "application")
        _wait_for_writer(environment)
        _wait_for_application(environment)
        print(
            "Generated PostgreSQL HA verified: "
            f"{original_leader} stopped -> {promoted_leader} promoted -> "
            f"{original_leader} rejoined; application dependency stack restart "
            "restored Redis topology and application health; explicit candidate "
            f"{candidate_name} recovered the leaderless cluster"
        )
    finally:
        environment.close()


if __name__ == "__main__":
    main(_workspace_from_arguments())
