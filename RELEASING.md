# Releasing

Version `2.0.0` publishes two installable packages from the same reviewed
commit:

- Python distribution `juntai-documentation-capability` with the
  `juntai-capability` CLI and `juntai.documentation` library.
- npm tarball `@zephytiju/juntai-documentation-viewer` with the standard
  Console module, standard viewer pages, and TypeScript contracts.

The canonical publication channel is the immutable `v2.0.0` GitHub
release in `zephytiju/JuntaiDocumentationCapabilityBundle`. Release CI rebuilds
from the tag, reruns all conformance tests, records SHA-256 checksums, an SPDX
SBOM and in-toto/SLSA provenance, and creates GitHub build attestations. Release
assets are never rebuilt in place; corrections require a new semantic version.

The Console package pins `@zephytiju/console-sdk==2.1.0`,
`@zephytiju/juntai-design-system==0.1.0`, and the aggregate
`@zephytiju/juntai-typescript-sdk==3.0.0`. It is released as a signed GitHub
asset from this existing workflow; creating a new npm namespace is outside the
foundation release path.

Capability payload publication is separate from foundation package release.
Backend producers inject `juntai-artifact-client==1.0.2`; payload bytes go
directly from that SDK to OCI and only generic metadata goes to Artifact
Registry. Browser and CLI code never receive OCI or Registry credentials.
