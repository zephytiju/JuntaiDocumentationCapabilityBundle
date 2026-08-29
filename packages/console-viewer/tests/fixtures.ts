export const routeBundleDigest = `sha256:${"1".repeat(64)}`;
export const contentGraphDigest = `sha256:${"2".repeat(64)}`;
export const indexDigest = `sha256:${"3".repeat(64)}`;
export const contentDigest = `sha256:${"4".repeat(64)}`;
export const projectionDigest = `sha256:${"5".repeat(64)}`;
export const searchDigest = `sha256:${"6".repeat(64)}`;

export function catalog(visibility: "public" | "restricted" = "public") {
  return {
    schemaVersion: "1",
    records: [{
      title: "Example documentation",
      summary: "Exact released documentation.",
      ownerKey: "example-owner",
      visibility,
      lifecycle: "release",
      locales: ["en"],
      taskClasses: ["operator"],
      compatibility: { console: "^1" },
      routeKey: "example.documentation",
      pin: {
        coordinate: {
          ownerKey: "example-owner",
          bundleId: "example.bundle",
          version: "1.0.0",
          artifactRef: { artifact_id: "artifact", version_id: "v1", manifest_digest: routeBundleDigest },
          digest: routeBundleDigest,
          schemaMajor: 1,
        },
        producerBuildId: "build-1",
        openapiDigest: contentDigest,
        mcpDescriptorDigest: contentDigest,
        contentGraphDigest,
        humanProjectionDigest: projectionDigest,
        mcpProjectionDigest: projectionDigest,
      },
    }],
    indexDigest,
    signature: { algorithm: "fixture", keyId: "fixture-key", signedDigest: indexDigest, value: "signed" },
  };
}

export const projection = {
  bundleDigest: contentGraphDigest,
  layoutProfile: "juntai.documentation.standard/v1",
  scope: "service",
  locale: "en",
  pages: [{
    unitId: "overview",
    kind: "guide",
    path: "pages/overview.html",
    title: "Overview",
    contentDigest,
    exactReferences: [{ kind: "schema", schemaId: "example", digest: contentDigest }],
  }],
  searchIndex: { path: "search-index.json", digest: searchDigest },
  lifecycle: "release",
  provenance: { sourceCommit: "commit" },
  projectionDigest,
};

export const search = [{ unitId: "overview", title: "Overview", path: "pages/overview.html" }];

export const applicationId = `app_${"a".repeat(32)}`;
export const applicationVersionId = `appv_${"b".repeat(32)}`;

export function applicationLinks() {
  return { items: [{
    application_id: applicationId,
    application_version_id: applicationVersionId,
    artifact: { artifact_id: "artifact", version_id: "v1", digest: routeBundleDigest },
    bundle_digest: routeBundleDigest,
    contribution_key: "example.bundle",
    lifecycle: "release",
    owner_domain: "example-owner",
    promotable: true,
    purpose: "RELEASE",
    route_key: "example.documentation",
    test_fleet_only: false,
    unit_id: "overview",
  }] };
}
