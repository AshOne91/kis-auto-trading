from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4

import aio_pika
from aiormq.exceptions import AMQPConnectionError
from verify_generated_postgres_ha import (
    MAX_ATTEMPTS,
    RABBITMQ_AMQP_PORT,
    RETRY_SECONDS,
    GeneratedEnvironment,
    _workspace_from_arguments,
)

RABBITMQ_SERVICES = ("rabbitmq-0", "rabbitmq-1", "rabbitmq-2")
QUEUE_NAME = "autoforge.ha.recovery"


def _cluster_running_nodes(
    environment: GeneratedEnvironment, service: str
) -> list[str]:
    result = environment.run(
        "exec", "-T", service, "rabbitmqctl", "cluster_status", "--formatter", "json"
    )
    status = json.loads(result.stdout)
    running_nodes = status.get("running_nodes")
    if not isinstance(running_nodes, list) or not all(
        isinstance(node, str) for node in running_nodes
    ):
        raise RuntimeError(f"RabbitMQ cluster status was malformed: {status!r}")
    return running_nodes


def _wait_for_cluster(
    environment: GeneratedEnvironment, *, expected_nodes: int
) -> None:
    last_nodes: object = None
    for _ in range(MAX_ATTEMPTS):
        try:
            running_nodes = _cluster_running_nodes(environment, "rabbitmq-1")
            last_nodes = running_nodes
            environment.run(
                "exec", "-T", "rabbitmq", "sh", "-c", "nc -z 127.0.0.1 5672"
            )
            if len(running_nodes) == expected_nodes:
                return
        except (RuntimeError, json.JSONDecodeError):
            pass
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        f"RabbitMQ cluster did not reach {expected_nodes} running nodes: {last_nodes!r}"
    )


async def _publish_and_receive() -> None:
    connection = await aio_pika.connect_robust(
        f"amqp://autoforge:change-me@127.0.0.1:{RABBITMQ_AMQP_PORT}/"
    )
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={"x-queue-type": "quorum"},
        )
        body = uuid4().hex.encode()
        await channel.default_exchange.publish(aio_pika.Message(body=body), QUEUE_NAME)
        message = await queue.get(timeout=10)
        try:
            if message.body != body:
                raise RuntimeError("RabbitMQ quorum queue returned an unexpected body")
        finally:
            await message.ack()
    finally:
        await connection.close()


async def _wait_for_publish_and_receive() -> None:
    last_error: AMQPConnectionError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            await _publish_and_receive()
            return
        except AMQPConnectionError as error:
            last_error = error
        await asyncio.sleep(RETRY_SECONDS)
    raise RuntimeError("RabbitMQ HAProxy did not become AMQP-ready") from last_error


def main() -> None:
    workspace = _workspace_from_arguments()
    compose_file = workspace / "environment" / "compose.integration.yml"
    if "  rabbitmq-0:\n" not in compose_file.read_text(encoding="utf-8"):
        raise RuntimeError("RabbitMQ cluster is required in the generated HA workspace")

    environment = GeneratedEnvironment(workspace)
    try:
        print(f"starting isolated RabbitMQ HA environment: {environment.project_name}")
        environment.run("up", "--detach", "--wait", "rabbitmq")
        _wait_for_cluster(environment, expected_nodes=len(RABBITMQ_SERVICES))
        asyncio.run(_wait_for_publish_and_receive())

        environment.run("stop", "rabbitmq-0")
        _wait_for_cluster(environment, expected_nodes=len(RABBITMQ_SERVICES) - 1)
        asyncio.run(_wait_for_publish_and_receive())

        environment.run("up", "--detach", "--wait", "rabbitmq-0")
        _wait_for_cluster(environment, expected_nodes=len(RABBITMQ_SERVICES))
        print(
            "Generated RabbitMQ HA verified: rabbitmq-0 stopped, the quorum queue "
            "published and consumed through HAProxy with two nodes, then rabbitmq-0 rejoined"
        )
    finally:
        environment.close()


if __name__ == "__main__":
    main()
