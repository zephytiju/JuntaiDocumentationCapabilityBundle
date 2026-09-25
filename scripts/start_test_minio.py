"""Run the unchanged official MinIO binary in an isolated, disposable CI container."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

RELEASE = "RELEASE.2025-04-22T22-12-26Z"
# These binaries match the original official image's /usr/bin/minio byte-for-byte:
# quay.io/minio/minio@sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e
ARTIFACTS = {
    "amd64": (118849720, "53e2a2cb16c5366ea6fbbc479c19ddb4c6a0948273e752f740fb1fbf27bb817c"),
    "arm64": (113115320, "6c2f3142c94240206123177f4ba1e360daa5d1e0a4962e90757ef4f92c3ab57c"),
}
BASE_IMAGE = (
    "python:3.12-slim-bookworm@sha256:"
    "32e2c347413bae52d567e2cc3eef31cd617a83dcac51644caadc0bbac131395a"
)
LABEL = "documentation.test-fixture=minio"


class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("MinIO artifact redirect must use HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_binary(destination: Path, architecture: str) -> None:
    size, expected = ARTIFACTS[architecture]
    url = (
        f"https://github.com/minio/minio/releases/download/{RELEASE}/"
        f"minio.linux-{architecture}.{RELEASE}"
    )
    digest, count = hashlib.sha256(), 0
    opener = urllib.request.build_opener(HTTPSOnlyRedirect())
    try:
        with opener.open(url, timeout=60) as response, destination.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > size:
                    raise ValueError("MinIO artifact exceeds pinned byte length")
                digest.update(chunk)
                output.write(chunk)
        if count != size or digest.hexdigest() != expected:
            raise ValueError("MinIO artifact does not match pinned SHA256 and length")
        destination.chmod(0o555)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def wait_ready(endpoint: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint + "/minio/health/ready", timeout=2) as r:
                if r.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError("Pinned MinIO fixture did not become ready")


def remove_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=True)


def stop() -> None:
    name = os.environ.get("NOUS_TEST_S3_CONTAINER")
    directory = os.environ.get("NOUS_TEST_S3_BINARY_DIRECTORY")
    if not name:
        return
    label = subprocess.check_output(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "documentation.test-fixture"}}',
            name,
        ],
        text=True,
    ).strip()
    if not name.startswith("documentation-ci-minio-") or label != "minio":
        raise ValueError("Refusing cleanup of an unrelated container")
    remove_container(name)
    if directory:
        path = Path(directory)
        if path.name != name:
            raise ValueError("Refusing cleanup of an unrelated binary directory")
        shutil.rmtree(path)


def main() -> None:
    destination = Path(os.environ["GITHUB_ENV"])
    architecture = subprocess.check_output(
        ["docker", "info", "--format", "{{.Architecture}}"], text=True
    ).strip()
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(architecture, architecture)
    if architecture not in ARTIFACTS:
        raise ValueError("Unsupported MinIO test platform")
    name = "documentation-ci-minio-" + uuid4().hex[:12]
    directory = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / name
    directory.mkdir(mode=0o700)
    identity, credential = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
    container_attempted = False
    try:
        download_binary(directory / "minio", architecture)
        with tempfile.NamedTemporaryFile(mode="w") as environment:
            environment.write(f"MINIO_ROOT_USER={identity}\nMINIO_ROOT_PASSWORD={credential}\n")
            environment.flush()
            container_attempted = True
            started = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--label",
                    LABEL,
                    "--label",
                    "codex.task=t100340",
                    "--env-file",
                    environment.name,
                    "--user",
                    "10001:10001",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--memory=512m",
                    "--cpus=1",
                    "--tmpfs",
                    "/data:rw,noexec,nosuid,size=256m,uid=10001,gid=10001",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=16m,uid=10001,gid=10001",
                    "--mount",
                    f"type=bind,src={directory / 'minio'},dst=/opt/minio,readonly",
                    "-p",
                    "127.0.0.1::9000",
                    "--entrypoint",
                    "/opt/minio",
                    BASE_IMAGE,
                    "server",
                    "/data",
                    "--address",
                    ":9000",
                ],
                capture_output=True,
                text=True,
            )
            if started.returncode:
                detail = started.stderr.replace(identity, "<redacted>").replace(
                    credential, "<redacted>"
                )
                raise RuntimeError(
                    f"Pinned MinIO fixture failed ({started.returncode}): {detail[:2000]}"
                )
        ports = json.loads(
            subprocess.check_output(
                ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", name],
                text=True,
            )
        )
        endpoint = f"http://127.0.0.1:{ports['9000/tcp'][0]['HostPort']}"
        wait_ready(endpoint)
        # GitHub treats these as workflow commands, not displayed credential values.
        print(f"::add-mask::{identity}")
        print(f"::add-mask::{credential}")
        with destination.open("a") as output:
            output.write(
                f"NOUS_TEST_S3_ENDPOINT={endpoint}\n"
                f"NOUS_TEST_S3_IDENTITY={identity}\nNOUS_TEST_S3_CREDENTIAL={credential}\n"
                f"NOUS_TEST_S3_CONTAINER={name}\nNOUS_TEST_S3_BINARY_DIRECTORY={directory}\n"
            )
    except BaseException:
        if container_attempted:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        shutil.rmtree(directory)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    if parser.parse_args().stop:
        stop()
    else:
        main()
