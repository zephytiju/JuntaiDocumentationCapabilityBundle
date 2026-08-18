# Releasing

Version `1.0.0` publishes two installable packages from the same reviewed
commit:

- Python distribution `juntai-documentation-capability` with the
  `juntai-capability` CLI and `juntai.documentation` library.
- npm tarball `@zephytiju/juntai-documentation-viewer` with the standard
  service-free Console viewer components and TypeScript contracts.

The canonical initial publication channel is the signed `v1.0.0` GitHub
release in `zephytiju/JuntaiDocumentationCapabilityBundle`. Release CI rebuilds
from the tag, reruns all conformance tests, records SHA-256 checksums, an SPDX
SBOM and in-toto/SLSA provenance, and creates GitHub build attestations. Release
assets are never rebuilt in place; corrections require a new semantic version.

Capability payload publication is separate from foundation package release.
Backend producers inject `juntai-artifact-client==1.0.2`; payload bytes go
directly from that SDK to OCI and only generic metadata goes to Artifact
Registry. Browser and CLI code never receive OCI or Registry credentials.
