"""Infrastructure tests — Redis connectivity check.

This test is designed to be CI-friendly: if Redis is not reachable on
localhost:6379, the test is skipped rather than failing.

To run Redis locally:
    docker compose up -d
Then re-run:
    pytest tests/test_infra.py -v
"""
import socket
import pytest

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_CONNECT_TIMEOUT = 2  # seconds


def _redis_reachable() -> bool:
    """Return True if a TCP connection to Redis can be established."""
    try:
        with socket.create_connection(
            (REDIS_HOST, REDIS_PORT), timeout=REDIS_CONNECT_TIMEOUT
        ):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


@pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis not reachable on localhost:6379 — run `docker compose up -d` first",
)
def test_redis_connection():
    """TCP connection to Redis on localhost:6379 succeeds and receives PONG."""
    # Use raw socket protocol to send PING and verify PONG response
    # (avoids redis-py dependency which is only added in Phase 2)
    with socket.create_connection((REDIS_HOST, REDIS_PORT), timeout=REDIS_CONNECT_TIMEOUT) as sock:
        # Redis inline command format: PING\r\n
        sock.sendall(b"PING\r\n")
        response = sock.recv(128)
    # Redis replies with "+PONG\r\n"
    assert b"PONG" in response, f"Expected PONG, got: {response!r}"


def test_redis_docker_compose_file_exists():
    """docker-compose.yml exists and contains the redis service definition."""
    import pathlib
    compose_path = pathlib.Path(__file__).parent.parent / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at project root"
    content = compose_path.read_text(encoding="utf-8")
    assert "redis" in content, "docker-compose.yml must define a redis service"
    assert "6379" in content, "docker-compose.yml must expose port 6379"
    assert "redis:7" in content, "docker-compose.yml must use redis:7-alpine image"
