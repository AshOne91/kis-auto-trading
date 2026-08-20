from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from uuid import uuid4

from verify_realtime_notification import SmokeConfiguration, verify

COMPOSE_FILES = (
    "environment/compose.integration.yml",
    "deploy/single-host/compose.override.yml",
)
APPLICATION_REPLICAS = 3
MAX_ATTEMPTS = 120
RETRY_SECONDS = 1.0


def _available_local_ports(count: int) -> tuple[int, ...]:
    sockets = [socket.socket() for _ in range(count)]
    try:
        for local_socket in sockets:
            local_socket.bind(("127.0.0.1", 0))
        return tuple(local_socket.getsockname()[1] for local_socket in sockets)
    finally:
        for local_socket in sockets:
            local_socket.close()


class SingleHostEnvironment:
    def __init__(self) -> None:
        self.project_name = f"generated-single-host-test-{uuid4().hex[:8]}"
        self._temporary_directory = TemporaryDirectory(prefix="kis-single-host-")
        (
            self.application_port,
            self.public_http_port,
            self.postgres_port,
            self.rabbitmq_amqp_port,
            self.rabbitmq_management_port,
            self.airflow_port,
        ) = _available_local_ports(6)
        self.command = (
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            *(
                argument
                for compose_file in COMPOSE_FILES
                for argument in ("-f", compose_file)
            ),
        )
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "LOCAL_BIND_ADDRESS": "127.0.0.1",
                "PUBLIC_BIND_ADDRESS": "127.0.0.1",
                "PUBLIC_HTTP_PORT": str(self.public_http_port),
                "LOG_ROOT": Path(self._temporary_directory.name).as_posix(),
                "POSTGRES_USER": "autoforge",
                "POSTGRES_PASSWORD": "change-me",
                "POSTGRES_REPLICATION_PASSWORD": "change-me-replication",
                "POSTGRES_PORT": str(self.postgres_port),
                "APPLICATION_PORT": str(self.application_port),
                "RABBITMQ_AMQP_PORT": str(self.rabbitmq_amqp_port),
                "RABBITMQ_MANAGEMENT_PORT": str(self.rabbitmq_management_port),
                "RABBITMQ_URL": "amqp://autoforge:change-me@rabbitmq:5672/",
                "DURABLE_JOB_API_TOKEN": "generated-single-host-test-token",
                "OPERATOR_API_TOKEN": "generated-single-host-operator-token",
                "KIS_API_URL": "https://example.invalid",
                "KIS_APP_KEY": "generated-single-host-test-key",
                "KIS_APP_SECRET": "generated-single-host-test-secret",
                "KIS_ACCOUNT_NUMBER": "00000000",
                "KIS_ACCOUNT_PRODUCT_CODE": "01",
                "KIS_ACCOUNT_ENVIRONMENT": "demo",
                "AIRFLOW_PORT": str(self.airflow_port),
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
            timeout=240,
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
            self._temporary_directory.cleanup()


def _application_containers(environment: SingleHostEnvironment) -> list[str]:
    result = environment.run("ps", "-q", "application")
    containers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(containers) != APPLICATION_REPLICAS:
        raise RuntimeError(
            f"Expected {APPLICATION_REPLICAS} application containers, got {containers!r}"
        )
    return containers


def _container_health(container: str) -> str:
    result = subprocess.run(
        ("docker", "inspect", "--format", "{{.State.Health.Status}}", container),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(f"Could not inspect application container {container}")
    return result.stdout.strip()


def _service_container(environment: SingleHostEnvironment, service: str) -> str:
    result = environment.run("ps", "-q", service)
    containers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(containers) != 1:
        raise RuntimeError(
            f"Expected one {service!r} container, got {containers!r}"
        )
    return containers[0]


def _wait_for_proxy_and_applications(environment: SingleHostEnvironment) -> list[str]:
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            containers = _application_containers(environment)
            unhealthy = [
                container
                for container in containers
                if _container_health(container) != "healthy"
            ]
            if unhealthy:
                raise RuntimeError(f"Application containers are unhealthy: {unhealthy!r}")
            with urlopen(
                f"http://127.0.0.1:{environment.public_http_port}/health", timeout=3
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"Nginx health returned {response.status}")
            return containers
        except (OSError, RuntimeError) as error:
            last_error = error if isinstance(error, RuntimeError) else RuntimeError(str(error))
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("Nginx and application replicas did not become healthy") from last_error


def _wait_for_service(environment: SingleHostEnvironment, service: str) -> str:
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            container = _service_container(environment, service)
            if _container_health(container) != "healthy":
                raise RuntimeError(f"{service!r} is unhealthy")
            return container
        except RuntimeError as error:
            last_error = error
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"{service!r} did not become healthy") from last_error


def _restart_container(container: str) -> None:
    result = subprocess.run(
        ("docker", "restart", container),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f"Could not restart container {container}: {result.stderr}")


def main() -> None:
    environment = SingleHostEnvironment()
    try:
        print(f"starting isolated single-host environment: {environment.project_name}")
        environment.run(
            "up",
            "--build",
            "--detach",
            "--wait",
            "--scale",
            f"application={APPLICATION_REPLICAS}",
            "nginx",
            "message-worker",
            "outbox-relay",
        )
        original_containers = _wait_for_proxy_and_applications(environment)
        smoke_configuration = SmokeConfiguration(
            project_name=environment.project_name,
            public_url=f"http://127.0.0.1:{environment.public_http_port}",
            shard_id="1",
            timeout_seconds=30.0,
            expected_application_replicas=APPLICATION_REPLICAS,
        )
        notification_id = asyncio.run(verify(smoke_configuration, via_outbox=True))

        restarted_relay = _service_container(environment, "outbox-relay")
        _restart_container(restarted_relay)
        if _wait_for_service(environment, "outbox-relay") != restarted_relay:
            raise RuntimeError("Restarted outbox relay was unexpectedly replaced")
        recovered_relay_notification_id = asyncio.run(
            verify(smoke_configuration, via_outbox=True)
        )

        restarted_worker = _service_container(environment, "message-worker")
        _restart_container(restarted_worker)
        if _wait_for_service(environment, "message-worker") != restarted_worker:
            raise RuntimeError("Restarted message worker was unexpectedly replaced")
        recovered_notification_id = asyncio.run(
            verify(smoke_configuration, via_outbox=True)
        )

        restarted_postgres = _service_container(environment, "postgres")
        _restart_container(restarted_postgres)
        if _wait_for_service(environment, "postgres") != restarted_postgres:
            raise RuntimeError("Restarted PostgreSQL was unexpectedly replaced")
        _wait_for_proxy_and_applications(environment)
        recovered_postgres_notification_id = asyncio.run(
            verify(smoke_configuration, via_outbox=True)
        )

        restarted_redis = _service_container(environment, "redis")
        _restart_container(restarted_redis)
        if _wait_for_service(environment, "redis") != restarted_redis:
            raise RuntimeError("Restarted Redis was unexpectedly replaced")
        _wait_for_proxy_and_applications(environment)
        recovered_redis_notification_id = asyncio.run(
            verify(smoke_configuration, via_outbox=True)
        )

        restarted_rabbitmq = _service_container(environment, "rabbitmq")
        _restart_container(restarted_rabbitmq)
        if _wait_for_service(environment, "rabbitmq") != restarted_rabbitmq:
            raise RuntimeError("Restarted RabbitMQ was unexpectedly replaced")
        _wait_for_service(environment, "outbox-relay")
        _wait_for_service(environment, "message-worker")
        recovered_rabbitmq_notification_id = asyncio.run(
            verify(smoke_configuration, via_outbox=True)
        )

        restarted_container = original_containers[0]
        _restart_container(restarted_container)
        recovered_containers = _wait_for_proxy_and_applications(environment)
        if restarted_container not in recovered_containers:
            raise RuntimeError("Restarted application container was unexpectedly replaced")

        print(
            "Generated single-host profile verified: "
            f"Nginx proxy healthy with {APPLICATION_REPLICAS} application replicas; "
            f"realtime notification {notification_id} was durable through the proxy; "
            f"outbox relay recovered realtime notification {recovered_relay_notification_id}; "
            f"message worker recovered realtime notification {recovered_notification_id}; "
            f"PostgreSQL recovered realtime notification {recovered_postgres_notification_id}; "
            f"Redis recovered realtime notification {recovered_redis_notification_id}; "
            f"RabbitMQ recovered realtime notification {recovered_rabbitmq_notification_id}; "
            "one application container restarted and recovered through the proxy"
        )
    finally:
        environment.close()


if __name__ == "__main__":
    main()
