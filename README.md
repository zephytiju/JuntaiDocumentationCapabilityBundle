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
python -m pip install 'https://github.com/zephytiju/JuntaiDocumentationCapabilityBundle/releases/download/v2.0.1/juntai_documentation_capability-2.0.1-py3-none-any.whl'

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
