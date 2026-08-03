from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

API_URLS = (
    "http://localhost:18001/health",
    "http://localhost:18002/health",
)
MAX_ATTEMPTS = 30
RETRY_SECONDS = 1.0
COMPOSE = ("docker", "compose", "-f", "compose.integration.yaml")


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


def compose(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (*COMPOSE, *arguments),
        check=True,
        capture_output=True,
        text=True,
    )


def wait_for_replica_promotion() -> str:
    last_master = "unknown"
    for _ in range(30):
        result = compose(
            "exec",
            "-T",
            "sentinel-1",
            "redis-cli",
            "-p",
            "26379",
            "--raw",
            "SENTINEL",
            "get-master-addr-by-name",
            "kis-session",
        )
        values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(values) >= 2:
            last_master = f"{values[0]}:{values[1]}"
            if values[0] == "172.28.0.11":
                return last_master
        time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"Redis replica was not promoted; master={last_master}")


def profile_count(service: str, user_id: str) -> int:
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
        f"SELECT count(*) FROM user_profiles WHERE user_id = '{user_id}'",
    )
    return int(result.stdout.strip())


def main() -> None:
    results = {url: wait_for_health(url) for url in API_URLS}
    if len(results) != 2:
        raise RuntimeError("Two independent API instances are required")
    for url, payload in results.items():
        print(f"healthy: {url} -> {payload}")

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
    print(
        "cross-instance account shard verified: "
        f"api-2 write -> api-1 read, store={expected_service}"
    )

    compose("exec", "-T", "redis-primary", "redis-cli", "WAIT", "1", "5000")
    compose("stop", "redis-primary")
    promoted_master = wait_for_replica_promotion()
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
        "Redis Sentinel failover verified: "
        f"redis-primary stopped -> {promoted_master}, old read + new write passed"
    )


if __name__ == "__main__":
    main()
