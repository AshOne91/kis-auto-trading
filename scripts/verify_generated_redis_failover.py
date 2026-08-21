from __future__ import annotations

import argparse
import time
from pathlib import Path

from verify_generated_postgres_ha import (
    MAX_ATTEMPTS,
    RETRY_SECONDS,
    GeneratedEnvironment,
    _wait_for_application,
)

SESSION_ID = "cmVkaXMtZHJpbGw.redis-failover-validation"
SESSION_USER_ID = "redis-drill"
SESSION_KEY = f"kis_session:{{cmVkaXMtZHJpbGw}}:session:{SESSION_ID}"


def _workspace_from_arguments() -> Path:
    parser = argparse.ArgumentParser(
        description="Verify Redis Cluster primary failover in a generated HA workspace."
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Generated workspace from autoforge.ha.yaml (default: current directory).",
    )
    workspace = parser.parse_args().workspace.resolve()
    compose_file = workspace / "environment" / "compose.integration.yml"
    if not compose_file.is_file():
        raise RuntimeError(f"Generated Compose file is missing: {compose_file}")
    if "  redis-7000:\n" not in compose_file.read_text(encoding="utf-8"):
        raise RuntimeError(
            "Redis Cluster is required. Generate an HA workspace from "
            "autoforge.ha.yaml and pass it with --workspace."
        )
    return workspace


def _service_port(service: str) -> str:
    return service.removeprefix("redis-")


def _cluster_nodes(environment: GeneratedEnvironment, service: str) -> list[list[str]]:
    result = environment.run(
        "exec",
        "-T",
        service,
        "redis-cli",
        "-p",
        _service_port(service),
        "--raw",
        "cluster",
        "nodes",
    )
    return [line.split() for line in result.stdout.splitlines() if line.strip()]


def _wait_for_redis_topology(
    environment: GeneratedEnvironment,
    service: str,
    *,
    expected_replicas: int,
    expected_promoted_node_id: str | None = None,
) -> list[list[str]]:
    last_topology: object = None
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            info = environment.run(
                "exec",
                "-T",
                service,
                "redis-cli",
                "-p",
                _service_port(service),
                "--raw",
                "cluster",
                "info",
            )
            values = {
                line.split(":", 1)[0]: line.split(":", 1)[1]
                for line in info.stdout.splitlines()
                if ":" in line
            }
            nodes = _cluster_nodes(environment, service)
            connected = [
                node for node in nodes if len(node) >= 8 and node[7] == "connected"
            ]
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
            promoted = expected_promoted_node_id is None or any(
                node[0] == expected_promoted_node_id for node in masters
            )
            if (
                values.get("cluster_state") == "ok"
                and values.get("cluster_slots_assigned") == "16384"
                and len(masters) == 3
                and len(replicas) == expected_replicas
                and promoted
            ):
                return nodes
        except RuntimeError as error:
            last_error = error
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        f"Redis Cluster did not reach the expected topology: {last_topology!r}"
    ) from last_error


def _session_store_probe(
    environment: GeneratedEnvironment,
    *,
    create: bool,
) -> None:
    operation = "await store.create(session)" if create else ""
    source = f"""\
import asyncio
import os
from redis.asyncio.cluster import RedisCluster
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import _cluster_startup_nodes
from kis_auto_trading.infrastructure.session_store.redis import RedisSessionStore

async def main():
    client = RedisCluster.from_url(
        os.environ[\"REDIS_CLUSTER_URL\"],
        startup_nodes=_cluster_startup_nodes() or None,
        decode_responses=True,
        require_full_coverage=True,
        reinitialize_steps=1,
    )
    store = RedisSessionStore(client)
    session = SessionData(
        session_id=os.environ[\"SESSION_ID\"],
        user_id=os.environ[\"SESSION_USER_ID\"],
        data={{\"check\": \"redis-failover\"}},
    )
    {operation}
    assert await store.get(session.session_id) == session
    await client.aclose()

asyncio.run(main())
"""
    environment.run(
        "exec",
        "-T",
        "-e",
        f"SESSION_ID={SESSION_ID}",
        "-e",
        f"SESSION_USER_ID={SESSION_USER_ID}",
        "application",
        "python",
        "-c",
        source,
    )


def _primary_and_replica(
    environment: GeneratedEnvironment,
) -> tuple[str, str, str, str]:
    slot = int(
        environment.run(
            "exec",
            "-T",
            "redis-7000",
            "redis-cli",
            "-p",
            "7000",
            "--raw",
            "cluster",
            "keyslot",
            SESSION_KEY,
        ).stdout.strip()
    )
    nodes = _cluster_nodes(environment, "redis-7000")
    primary = next(
        (
            node
            for node in nodes
            if len(node) >= 9
            and "master" in node[2]
            and "fail" not in node[2]
            and any(
                int(start) <= slot <= int(end)
                for start, end in (
                    item.split("-", 1) for item in node[8:] if "-" in item
                )
            )
        ),
        None,
    )
    if primary is None:
        raise RuntimeError(f"No Redis primary owns session slot {slot}")
    replica = next(
        (
            node
            for node in nodes
            if len(node) >= 8
            and node[3] == primary[0]
            and ("slave" in node[2] or "replica" in node[2])
            and node[7] == "connected"
        ),
        None,
    )
    if replica is None:
        raise RuntimeError("No connected replica owns the session-key primary")
    primary_service = f"redis-{primary[1].split('@', 1)[0].rsplit(':', 1)[1]}"
    replica_service = f"redis-{replica[1].split('@', 1)[0].rsplit(':', 1)[1]}"
    return primary_service, primary[0], replica_service, replica[0]


def main(workspace: Path) -> None:
    environment = GeneratedEnvironment(workspace)
    environment.environment.setdefault(
        "RABBITMQ_ERLANG_COOKIE", "generated-redis-failover-test-cookie"
    )
    try:
        print(
            f"starting isolated Redis failover environment: {environment.project_name}"
        )
        environment.run("up", "--build", "--detach", "application")
        _wait_for_redis_topology(environment, "redis-7000", expected_replicas=3)
        application_container = _wait_for_application(environment)
        _session_store_probe(environment, create=True)

        primary_service, primary_id, replica_service, replica_id = _primary_and_replica(
            environment
        )
        management_service = (
            "redis-7001" if primary_service == "redis-7000" else "redis-7000"
        )
        environment.run("stop", primary_service)
        _wait_for_redis_topology(
            environment,
            management_service,
            expected_replicas=2,
            expected_promoted_node_id=replica_id,
        )
        _session_store_probe(environment, create=False)
        _wait_for_application(environment, expected_container=application_container)

        environment.run("up", "--detach", "--wait", primary_service)
        nodes = _wait_for_redis_topology(
            environment, management_service, expected_replicas=3
        )
        restored = next((node for node in nodes if node[0] == primary_id), None)
        if (
            restored is None
            or ("slave" not in restored[2] and "replica" not in restored[2])
            or "fail" in restored[2]
        ):
            raise RuntimeError(
                f"Stopped Redis node did not rejoin as a replica: {restored!r}"
            )
        print(
            "Generated Redis failover verified: "
            f"{primary_service} stopped -> {replica_service} promoted -> "
            f"{primary_service} rejoined; generated session read and application health remained available"
        )
    finally:
        environment.close()


if __name__ == "__main__":
    main(_workspace_from_arguments())
