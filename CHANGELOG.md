# Changelog

## 2.0.1 — 2026-09-06

- Accept genuine FuseAPI 2.1.0 descriptors while retaining exact 2.0.0 compatibility and all digest, schema, profile, Tool and OpenAPI linkage checks.
- Exercise both released exporters without version overrides and verify real OpenAPI/MCP inputs through byte-identical bundle builds.
- Publish a hash-pinned conformance dependency lock, clean-wheel consumer evidence, and release metadata derived from the actual package version.

## 2.0.0 — 2026-08-29

- Publish a deterministic `ConsoleModule` for the signed documentation catalog, exact immutable bundle, and application-version documentation pages.
- Route public catalog entries through the shared viewer and restricted entries through provider `routeKey` values carrying only stable scalar identifiers.
- Consume Application Metadata only through the aggregate TypeScript SDK 3.0.0 and require the stable `unitId` association field.
- Keep all browser delivery paths same-origin and reject Registry, OCI, Meridian, storage, credential, callback, and client authority leakage.

## 1.0.0 — 2026-08-18

- Initial service-free documentation capability bundle schemas, library and CLI.
- Exact `juntai-fuse-api==2.0.0` MCP descriptor conformance.
- Deterministic human and MCP projections, catalog selection and loader.
- Console viewer components and advisory privacy-safe feedback hooks.
- Injected `juntai-artifact-client==1.0.2` direct OCI publication path.
