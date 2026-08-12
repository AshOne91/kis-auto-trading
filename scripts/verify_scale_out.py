from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from uuid import uuid4

API_URLS = (
    "http://localhost:18001/health",
    "http://localhost:18002/health",
)
MAX_ATTEMPTS = 30
RETRY_SECONDS = 1.0
COMPOSE = ("docker", "compose", "-f", "compose.integration.yaml")
REDIS_SERVICES = {
    "172.29.0.10": "redis-node-1",
    "172.29.0.11": "redis-node-2",
    "172.29.0.12": "redis-node-3",
    "172.29.0.13": "redis-node-4",
    "172.29.0.14": "redis-node-5",
    "172.29.0.15": "redis-node-6",
}


@dataclass(frozen=True, slots=True)
class ClusterNodeInfo:
    node_id: str
    address: str
    flags: frozenset[str]
    master_id: str
    slots: tuple[str, ...]

    def owns(self, slot: int) -> bool:
        for item in self.slots:
            if item.startswith("["):
                continue
            start_text, separator, end_text = item.partition("-")
            start = int(start_text)
            end = int(end_text) if separator else start
            if start <= slot <= end:
                return True
        return False


def wait_for_health(url: str) -> dict[str, str]:
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError(f"Unexpected HTTP status: {response.status}")
                payload = json.loads(response.read().decode("utf-8"))
                if payload != {"status": "ok"}:
                    raise RuntimeError(f"Unexpected health response: {payload!r}")
                return payload
        except (OSError, RuntimeError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"API instance did not become healthy: {url}") from last_error


def post_json(url: str, payload: dict[str, str]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")
        return json.loads(response.read().decode("utf-8"))


def authenticated_json(
    method: str,
    url: str,
    access_token: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")
        return json.loads(response.read().decode("utf-8"))


def wait_for_post_json(
    url: str,
    payload: dict[str, str],
    attempts: int = 30,
) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return post_json(url, payload)
        except (OSError, RuntimeError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"POST did not recover after failover: {url}") from last_error


def durable_job_json(
    method: str,
    url: str,
    api_token: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status not in {200, 202}:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")
        return json.loads(response.read().decode("utf-8"))


def compose(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (*COMPOSE, *arguments),
        check=True,
        capture_output=True,
        text=True,
    )


def compose_with_input(
    input_text: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (*COMPOSE, *arguments),
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    )

def cluster_nodes(service: str = "redis-node-1") -> list[ClusterNodeInfo]:
    result = compose(
        "exec", "-T", service, "redis-cli", "--raw", "CLUSTER", "NODES"
    )
    nodes = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 8:
            continue
        nodes.append(
            ClusterNodeInfo(
                node_id=fields[0],
                address=fields[1].split("@", maxsplit=1)[0].split(":")[0],
                flags=frozenset(fields[2].split(",")),
                master_id=fields[3],
                slots=tuple(fields[8:]),
            )
        )
    return nodes


def cluster_slot(key: str) -> int:
    result = compose(
        "exec",
        "-T",
        "redis-node-1",
        "redis-cli",
        "--raw",
        "CLUSTER",
        "KEYSLOT",
        key,
    )
    return int(result.stdout.strip())


def cluster_failover_target(slot: int) -> tuple[str, str, str]:
    nodes = cluster_nodes()
    primary = next(
        node for node in nodes if "master" in node.flags and node.owns(slot)
    )
    replica = next(node for node in nodes if node.master_id == primary.node_id)
    return (
        REDIS_SERVICES[primary.address],
        REDIS_SERVICES[replica.address],
        replica.node_id,
    )


def wait_for_cluster_promotion(service: str, node_id: str) -> None:
    last_flags: frozenset[str] = frozenset()
    for _ in range(45):
        try:
            node = next(item for item in cluster_nodes(service) if item.node_id == node_id)
            last_flags = node.flags
            if "master" in node.flags and "fail" not in node.flags:
                return
        except (StopIteration, subprocess.CalledProcessError):
            pass
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(
        f"Redis Cluster replica was not promoted: {service}, flags={last_flags}"
    )


def profile_count(service: str, user_id: str) -> int:
    return int(
        account_scalar(
            service,
            f"SELECT count(*) FROM user_profiles WHERE user_id = '{user_id}'",
        )
    )


def account_scalar(service: str, statement: str) -> str:
    result = compose(
        "exec",
        "-T",
        service,
        "psql",
        "-U",
        "kis_test",
        "-d",
        "account",
        "-tAc",
        statement,
    )
    return result.stdout.strip()


def wait_for_rabbitmq() -> None:
    last_error: subprocess.CalledProcessError | None = None
    for _ in range(45):
        try:
            compose("exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping")
            return
        except subprocess.CalledProcessError as error:
            last_error = error
            time.sleep(RETRY_SECONDS)
    raise RuntimeError("RabbitMQ did not recover") from last_error


def latest_outbox_event(service: str, user_id: str) -> tuple[str, str] | None:
    value = account_scalar(
        service,
        "SELECT event_id || '|' || status FROM outbox_events "
        f"WHERE aggregate_id = '{user_id}' "
        "ORDER BY occurred_at DESC LIMIT 1",
    )
    if not value:
        return None
    event_id, separator, status = value.partition("|")
    if not separator:
        raise RuntimeError(f"Unexpected outbox row: {value!r}")
    return event_id, status


def processed_count(service: str, event_id: str) -> int:
    return int(
        account_scalar(
            service,
            "SELECT count(*) FROM processed_messages "
            f"WHERE event_id = '{event_id}'",
        )
    )


def rabbitmq_queue_messages(queue_name: str) -> int:
    result = compose(
        "exec",
        "-T",
        "rabbitmq",
        "rabbitmqctl",
        "list_queues",
        "name",
        "messages",
        "--formatter",
        "json",
    )
    queues = json.loads(result.stdout)
    for queue in queues:
        if queue["name"] == queue_name:
            return int(queue["messages"])
    raise RuntimeError(f"RabbitMQ queue was not declared: {queue_name}")


def wait_for_dead_letter(queue_name: str) -> None:
    for _ in range(30):
        if rabbitmq_queue_messages(queue_name) >= 1:
            return
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"Poison message did not reach DLQ: {queue_name}")


def wait_for_outbox_delivery(
    service: str,
    user_id: str,
    expected_event_id: str | None = None,
) -> str:
    last_state: tuple[str, str] | None = None
    for _ in range(90):
        last_state = latest_outbox_event(service, user_id)
        if last_state is not None:
            event_id, status = last_state
            if (
                status == "published"
                and processed_count(service, event_id) == 1
                and (expected_event_id is None or event_id == expected_event_id)
            ):
                return event_id
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"Outbox event was not delivered: {last_state!r}")


def verify_airflow_cancelled_job() -> None:
    api_token = os.environ.get("DURABLE_JOB_API_TOKEN")
    if not api_token:
        raise RuntimeError("DURABLE_JOB_API_TOKEN is required for Airflow validation")
    compose("stop", "durable-job-worker")
    try:
        run_key = f"scale-out-airflow-cancel-{uuid4()}"
        base_url = "http://localhost:18001/internal/jobs/news_collection"
        created = durable_job_json(
            "POST",
            base_url,
            api_token,
            {"run_key": run_key, "payload": {"symbols": ["CANCELLED"]}},
        )
        job_id = str(created["job_id"])
        cancelled = durable_job_json(
            "DELETE",
            f"{base_url}/{job_id}",
            api_token,
        )
        if cancelled.get("status") != "cancelled":
            raise RuntimeError(f"Durable Job was not cancelled: {cancelled!r}")
        dags = json.loads(
            compose(
                "exec", "-T", "airflow", "airflow", "dags", "list",
                "--output", "json",
            ).stdout
        )
        if not any(item.get("dag_id") == "durable_job_news_collection" for item in dags):
            raise RuntimeError("Generated durable-job Airflow DAG was not discovered")
        script = f"""
import runpy
namespace = runpy.run_path('/opt/airflow/dags/news_collection.py')
ti = type('TI', (), {{'xcom_pull': lambda self, task_ids: {job_id!r}}})()
try:
    namespace['wait_for_job'](ti)
except RuntimeError as error:
    assert str(error) == 'durable job cancelled'
    print('airflow_cancelled_wait=controlled_failure')
else:
    raise AssertionError('expected cancelled failure')
"""
        result = compose_with_input(script, "exec", "-T", "airflow", "python", "-")
        if "airflow_cancelled_wait=controlled_failure" not in result.stdout:
            raise RuntimeError(f"Airflow cancellation assertion missing: {result.stdout!r}")
        print("Airflow cancellation verified: DAG discovery + controlled wait failure")
    finally:
        compose("start", "durable-job-worker")

def verify_airflow_successful_job() -> None:
    api_token = os.environ.get("DURABLE_JOB_API_TOKEN")
    if not api_token:
        raise RuntimeError("DURABLE_JOB_API_TOKEN is required for Airflow validation")
    script = f"""
import json
import os
import runpy
from datetime import datetime, timezone

namespace = runpy.run_path('/opt/airflow/dags/news_collection.py')
job_globals = namespace['trigger_job'].__globals__
job_globals['JOB_TYPE'] = 'news_index'
job_globals['PAYLOAD_ENV'] = 'DURABLE_JOB_NEWS_INDEX_PAYLOAD_JSON'
os.environ['DURABLE_JOB_NEWS_INDEX_PAYLOAD_JSON'] = json.dumps({{
    'source_keys': ['missing-{uuid4()}'],
}})
dag_run = namespace['dag'].test(execution_date=datetime.now(timezone.utc))
if str(dag_run.state) != 'success':
    raise RuntimeError(f'Airflow DAG test did not succeed: {{dag_run.state!r}}')
print(f'airflow_dag_test=succeeded:{{dag_run.run_id}}')
"""
    result = compose_with_input(script, "exec", "-T", "airflow", "python", "-")
    if "airflow_dag_test=succeeded:" not in result.stdout:
        raise RuntimeError(f"Airflow DAG test assertion missing: {result.stdout!r}")
    print("Airflow success verified: DAG test trigger + worker completion + wait")

def main() -> None:
    results = {url: wait_for_health(url) for url in API_URLS}
    if len(results) != 2:
        raise RuntimeError("Two independent API instances are required")
    for url, payload in results.items():
        print(f"healthy: {url} -> {payload}")

    verify_airflow_cancelled_job()
    verify_airflow_successful_job()

    email = f"scale-out-{uuid4()}@example.com"
    password = "integration-test-password"
    signup = post_json(
        "http://localhost:18001/api/identity/signup",
        {"email": email, "password": password},
    )
    login = post_json(
        "http://localhost:18001/api/identity/login",
        {"email": email, "password": password},
    )
    validated = post_json(
        "http://localhost:18002/api/identity/session/validate",
        {"access_token": str(login["access_token"])},
    )
    if signup["user_id"] != login["user_id"]:
        raise RuntimeError("Signup and login resolved different users")
    if login["user_id"] != validated["user_id"]:
        raise RuntimeError("API 2 resolved a different Redis session user")
    if validated["shard_id"] not in {"1", "2"}:
        raise RuntimeError("Session contains an invalid account shard")
    print(
        "cross-instance session verified: "
        f"api-1 login -> api-2 validation, shard={validated['shard_id']}"
    )

    access_token = str(login["access_token"])
    profile_payload: dict[str, object] = {
        "investment_experience": "INTERMEDIATE",
        "risk_tolerance": "MODERATE",
        "investment_goal": "GROWTH",
        "monthly_budget": 1_000_000,
    }
    compose("stop", "rabbitmq")
    updated_profile = authenticated_json(
        "PUT",
        "http://localhost:18002/api/account/profile",
        access_token,
        profile_payload,
    )
    loaded_profile = authenticated_json(
        "GET",
        "http://localhost:18001/api/account/profile",
        access_token,
    )
    if updated_profile != loaded_profile:
        raise RuntimeError("API instances resolved different account profiles")
    expected_service = f"account-db-{validated['shard_id']}"
    other_service = (
        "account-db-2" if expected_service == "account-db-1" else "account-db-1"
    )
    user_id = str(login["user_id"])
    if profile_count(expected_service, user_id) != 1:
        raise RuntimeError("Profile was not stored in the selected account shard")
    if profile_count(other_service, user_id) != 0:
        raise RuntimeError("Profile leaked into the non-selected account shard")
    pending_event = latest_outbox_event(expected_service, user_id)
    if pending_event is None or pending_event[1] != "pending":
        raise RuntimeError(
            "Profile transaction did not leave a pending outbox event "
            f"while RabbitMQ was down: {pending_event!r}"
        )
    event_id = pending_event[0]
    if processed_count(expected_service, event_id) != 0:
        raise RuntimeError("Outbox event was processed while RabbitMQ was down")
    print(
        "cross-instance account shard verified: "
        f"api-2 write -> api-1 read, store={expected_service}"
    )
    print(
        "RabbitMQ outage write verified: profile + pending outbox committed, "
        f"event_id={event_id}"
    )

    compose("start", "rabbitmq")
    wait_for_rabbitmq()
    delivered_event_id = wait_for_outbox_delivery(
        expected_service, user_id, event_id
    )
    print(
        "RabbitMQ recovery verified: outbox published and worker processed, "
        f"event_id={delivered_event_id}"
    )

    account_scalar(
        expected_service,
        "UPDATE outbox_events SET status = 'pending', published_at = NULL, "
        "available_at = NOW() "
        f"WHERE event_id = '{event_id}' RETURNING event_id",
    )
    wait_for_outbox_delivery(expected_service, user_id, event_id)
    if processed_count(expected_service, event_id) != 1:
        raise RuntimeError("Duplicate event produced more than one inbox record")
    print(
        "duplicate delivery verified: repeated publish kept one inbox record, "
        f"event_id={event_id}"
    )

    poison_event_id = str(uuid4())
    shard_id = str(validated["shard_id"])
    account_scalar(
        expected_service,
        "INSERT INTO outbox_events ("
        "event_id, event_type, event_version, aggregate_id, routing_key, "
        "payload, status, attempts, available_at, occurred_at"
        ") VALUES ("
        f"'{poison_event_id}', 'account.profile.unsupported', 1, '{user_id}', "
        "'account.profile.unsupported', "
        f"'{{\"shard_id\":\"{shard_id}\"}}'::jsonb, "
        "'pending', 0, NOW(), NOW()"
        ") RETURNING event_id",
    )
    wait_for_dead_letter("kis.profile.events.dead-letter")
    if processed_count(expected_service, poison_event_id) != 0:
        raise RuntimeError("Poison event was incorrectly claimed as processed")
    compose(
        "exec",
        "-T",
        "rabbitmq",
        "rabbitmqctl",
        "purge_queue",
        "kis.profile.events.dead-letter",
    )
    print(
        "dead-letter verified: unsupported event rejected without inbox claim, "
        f"event_id={poison_event_id}"
    )

    routing_tag = access_token.partition(".")[0]
    session_key = f"kis_session:{{{routing_tag}}}:session:{access_token}"
    user_key = f"kis_session:{{{routing_tag}}}:user-sessions"
    session_slot = cluster_slot(session_key)
    if cluster_slot(user_key) != session_slot:
        raise RuntimeError("Session keys do not share one Redis Cluster slot")
    primary_service, replica_service, replica_id = cluster_failover_target(
        session_slot
    )
    compose("exec", "-T", primary_service, "redis-cli", "WAIT", "1", "5000")
    compose("stop", primary_service)
    wait_for_cluster_promotion(replica_service, replica_id)
    recovered = wait_for_post_json(
        "http://localhost:18002/api/identity/session/validate",
        {"access_token": str(login["access_token"])},
    )
    if recovered != validated:
        raise RuntimeError("Replicated session changed during Redis failover")
    second_login = wait_for_post_json(
        "http://localhost:18001/api/identity/login",
        {"email": email, "password": password},
    )
    wait_for_post_json(
        "http://localhost:18002/api/identity/session/validate",
        {"access_token": str(second_login["access_token"])},
    )
    print(
        "Redis Cluster failover verified: "
        f"slot={session_slot}, {primary_service} stopped -> "
        f"{replica_service} promoted, old read + new write passed"
    )


if __name__ == "__main__":
    main()
