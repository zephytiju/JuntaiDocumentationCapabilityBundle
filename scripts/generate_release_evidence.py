"""Generate bounded checksums, SPDX SBOM and in-toto release provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def created_at() -> str:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    release_version = project["version"]
    release_lock = json.loads((root / "release-lock.json").read_text())
    if release_lock["packageVersion"] != release_version:
        raise SystemExit("release lock and package versions differ")

    dist = Path(args.dist)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = [path for path in sorted(dist.iterdir()) if path.is_file()]
    if not artifacts:
        raise SystemExit("release distribution is empty")
    subjects = [
        {"name": path.name, "digest": {"sha256": digest(path)}, "byteLength": path.stat().st_size}
        for path in artifacts
    ]
    checksums = "".join(f"{item['digest']['sha256']}  {item['name']}\n" for item in subjects)
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8", newline="\n")

    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "juntai-documentation-capability-release",
        "documentNamespace": (
            f"https://github.com/{args.repository}/releases/{args.commit}/{args.run_id}"
        ),
        "creationInfo": {
            "created": created_at(),
            "creators": [f"Tool: JuntaiDocumentationCapabilityBundle-{release_version}"],
        },
        "packages": [
            {
                "name": item["name"],
                "SPDXID": f"SPDXRef-Package-{index}",
                "versionInfo": release_version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "checksums": [{"algorithm": "SHA256", "checksumValue": item["digest"]["sha256"]}],
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "LicenseRef-Proprietary",
                "copyrightText": "Copyright 2026 Juntai Team",
            }
            for index, item in enumerate(subjects, start=1)
        ],
    }
    (output / "release.spdx.json").write_bytes(canonical(sbom))
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": item["name"], "digest": item["digest"]} for item in subjects],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/zephytiju/JuntaiDocumentationCapabilityBundle/.github/workflows/release.yml@refs/heads/main",
                "externalParameters": {"version": release_version},
                "internalParameters": {},
                "resolvedDependencies": [
                    {
                        "uri": f"git+https://github.com/{args.repository}@{args.commit}",
                        "digest": {"gitCommit": args.commit},
                    },
                    {
                        "uri": "requirements-conformance.txt",
                        "digest": {"sha256": digest(root / "requirements-conformance.txt")},
                    },
                ],
            },
            "runDetails": {
                "builder": {"id": "https://github.com/actions/runner"},
                "metadata": {
                    "invocationId": f"https://github.com/{args.repository}/actions/runs/{args.run_id}",
                    "startedOn": created_at(),
                },
            },
        },
    }
    (output / "release.intoto.jsonl").write_bytes(canonical(provenance))
    manifest = {
        "schemaVersion": "capability.juntai.io/foundation-release/v1",
        "repository": args.repository,
        "sourceCommit": args.commit,
        "version": release_version,
        "fuseApiVersion": release_lock["contracts"]["fuseApi"].split("==")[1],
        "supportedFuseApiVersions": release_lock["contracts"]["supportedFuseApiVersions"],
        "dependencyLockSha256": digest(root / "requirements-conformance.txt"),
        "artifactSdkVersion": "1.0.2",
        "artifacts": subjects,
    }
    (output / "release-manifest.json").write_bytes(canonical(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
