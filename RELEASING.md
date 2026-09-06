# Releasing

Version `2.0.1` publishes two installable packages from the same reviewed
commit:

- Python distribution `juntai-documentation-capability` with the
  `juntai-capability` CLI and `juntai.documentation` library.
- npm tarball `@zephytiju/juntai-documentation-viewer` with the standard
  Console module, standard viewer pages, and TypeScript contracts.

The canonical publication channel is the immutable `v2.0.1` GitHub
release in `zephytiju/JuntaiDocumentationCapabilityBundle`. Release CI rebuilds
from the tag, reruns all conformance tests, records SHA-256 checksums, an SPDX
SBOM and in-toto/SLSA provenance, and creates GitHub build attestations. Release
assets are never rebuilt in place; corrections require a new semantic version.

The 2.0.1 correction consumes exact FuseAPI 2.1.0 and retains descriptor
compatibility with 2.0.0. CI exercises both installed exporters without a
version override on Python 3.11–3.13. Other exporter versions fail closed.
`requirements-conformance.txt` locks release/conformance dependencies by version
and SHA-256. Update it with:

```bash
uv pip compile pyproject.toml --extra test --extra artifact --extra fuseapi \
  --universal --python-version 3.11 --generate-hashes --no-annotate \
  -o requirements-conformance.txt
```

Release CI installs the built wheel into a clean environment and runs
`scripts/verify_fuseapi_consumer.py`. Its evidence archive includes genuine
OpenAPI/MCP exporter outputs, the exact content lock, byte-identical bundle
builds, and their digests. This verifies the bundle consumer; downstream
RuntimeCore and Generator must publish their own compatible exact pins.

The Console package pins `@zephytiju/console-sdk==2.1.0`,
`@zephytiju/juntai-design-system==0.1.0`, and the aggregate
`@zephytiju/juntai-typescript-sdk==3.0.0`. It is released as a signed GitHub
asset from this existing workflow; creating a new npm namespace is outside the
foundation release path.

Capability payload publication is separate from foundation package release.
Backend producers inject `juntai-artifact-client==1.0.2`; payload bytes go
directly from that SDK to OCI and only generic metadata goes to Artifact
Registry. Browser and CLI code never receive OCI or Registry credentials.
