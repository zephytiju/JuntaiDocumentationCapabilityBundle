# Juntai Documentation Capability Bundle

`juntai-documentation-capability` is the service-free foundation for producing
immutable human documentation and MCP Resources/Prompts from one reviewed,
versioned source graph. It validates exact production MCP descriptors from `juntai-fuse-api`
2.0.0 and 2.1.0 (no other exporter versions) and never defines or registers MCP Tools.

The repository contains:

- versioned manifest, content-graph, catalog, feedback, evidence and tool-outcome schemas;
- a deterministic resolver, validator, packager and offline renderer;
- a pure catalog compiler/selector and framework-neutral capability loader;
- the `juntai.documentation.standard/v1` Console module with catalog, bundle,
  and application-version pages;
- an injected `juntai-artifact-client==1.0.2` publication adapter; and
- privacy-safe, advisory feedback hooks with fail-closed evidence dereference.

It contains no domain documentation, workflow meaning, safety or approval
semantics, service runtime, registry, editor, content proxy, telemetry fallback,
private-database fallback, or automatically mutating feedback path.

## Install and use

```bash
python -m pip install 'https://github.com/zephytiju/JuntaiDocumentationCapabilityBundle/releases/download/v2.1.0/juntai_documentation_capability-2.1.0-py3-none-any.whl'

juntai-capability resolve \
  --manifest documentation/manifest.yaml \
  --lock capability.lock
juntai-capability validate --lock capability.lock
juntai-capability build --lock capability.lock --out dist/capability
juntai-capability catalog compile \
  --records publications \
  --signature catalog-signature.json \
  --out dist/catalog.json
```

`resolve` is the only stage that reads producer sources. `validate` and `build`
operate from exact locked inputs and are offline. A second clean build produces
byte-identical JSON and tar artifacts.

## Development

```bash
python -m pip install --require-hashes -r requirements-conformance.txt
python -m pip install --no-deps -e .
pytest -q
ruff check .
ruff format --check .
python -m build
npm ci --prefix packages/console-viewer --ignore-scripts
npm run verify --prefix packages/console-viewer
```

The M4 fixture under `fixtures/valid/minimal` is deliberately generic. It is a
contract example, not domain content.

## Package map

The required logical packages are explicit under `packages/`. The Python
distribution keeps one install/version boundary and maps those packages to
small modules under `juntai.documentation`: core schemas and validation,
CLI, human and MCP renderers, framework-neutral loader, static catalog
compiler, and feedback hooks. `packages/console-viewer` is the independently
installable browser package. `release-lock.json` pins the exact M4 foundation
contracts consumed by this release.
## Meridian capability publication (Python 3.12+)

Install the `meridian` extra to publish with a deployment-owned Meridian
`ResourceStore`. The deployment supplies storage configuration, credentials,
schema migration, and runtime lifecycle. Documentation constructs none of them.

```python
from juntai.documentation import publish_bundle_meridian, load_capability_set_meridian

publication = publish_bundle_meridian(
    build.output, resource_store=store, actor="build/my-application"
)
capabilities = load_capability_set_meridian(
    resource_store=store,
    pin=publication["pin"],
    runtime_build_id=runtime_build_id,
    runtime_openapi_digest=openapi_digest,
    runtime_mcp_descriptor_digest=mcp_descriptor_digest,
)
```

Publication commits the complete deterministic build archive, human projection,
MCP projection, and provenance as four immutable artifacts, then checks every
exact reference and reads back its bytes. Failure returns no publication result;
retrying identical bytes uses ResourceStore's immutable identity semantics.
There is no cross-artifact transaction or automatic deletion of partial results.

The opaque `artifactRef` uses discriminator
`capability.juntai.io/meridian-artifact-reference/v1`, a public `StoredResourceRef`
in `resource`, and `digest`. Coordinate and reference digests are SHA-256 of the
stored payload. They are not OCI manifest digests or Registry identifiers.
The bundle payload media type is `application/vnd.juntai.capability-build.v1+tar`.
It contains the nine standard build output files and is limited to 64 MiB.
Loading rejects changed metadata or bytes, non-published resources, unsafe or
incomplete archives, and mismatched build/runtime lineage. Directory consumers
also verify the complete archive digest. Legacy Artifact SDK publication and
references retain their existing API; older consumers must upgrade before using
Meridian references. Python 3.11 supports the legacy API only.

### Exact HTTP capabilities (v2)

`build_openapi_bundle(openapi_bytes, metadata=...)` builds the separate
`capability.juntai.io/openapi-bundle/v2` contract. It preserves the original
OpenAPI 3.1.0 bytes, including whitespace. Metadata binds `ownerKey`, `bundleId`,
`version`, `producerBuildId`, `serviceId`, `source`, `units`, and `selections`.
`source` contains the HTTPS repository, full source commit, release artifact
SHA-256 and descriptor path within that artifact. The caller verifies the release
signature before building; these fields bind provenance but do not authenticate it.

Each selection contains `operationId`, `approvalPolicyUnitId` (nullable for reads),
and `idempotency` (`read` for GET, `keyed` or `none` for mutations). Mutation tools
require a nonempty approval reference to an included `policy` or `safety` unit.
Units contain `unitId`, `kind`, and nonempty `content`; supported kinds are
`document`, `workflow`, `evaluation`, `policy`, and `safety`.

`compile_openapi_tools` derives exact method/path/operation and input/output schema
pins. The HTTP argument envelope contains `pathParameters`, optional `query`, and
optional `body`. Only scalar path/query parameters, JSON bodies, and one successful
JSON response are supported. Local component schema references are resolved into
self-contained schemas, including recursive definitions. Duplicate operation IDs,
remote/unresolved references, unsupported serialization, and ambiguous responses
fail closed. Host authentication is outside model-controlled arguments.

`publish_openapi_bundle_meridian` publishes one deterministic archive containing
`bundle.json` and unchanged `openapi.json`, requires object and metadata commit,
and reads the exact object back before returning its v2 pin. The coordinate uses
`schemaMajor: 2`; the pin binds service, source, manifest, and OpenAPI digests.
`load_openapi_bundle_meridian` independently recompiles the tools on read.
`validate_openapi_bindings` lets Delivery consumers recheck the complete binding
without storage access, reconstructing the archive digest from its exact inputs.
No v1 MCP descriptor or projection is fabricated. Existing v1 APIs remain strict.

Tests include unchanged Lattice 0.7.0 bytes. Their synthetic source commit and
signing context are explicitly offline fixtures, not release or live admission
evidence. Required real-storage CI publishes and reloads the same document through
a fresh Meridian runtime.
