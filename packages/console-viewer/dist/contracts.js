function record(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Expected an object.");
    return value;
}
function text(value, name) {
    if (typeof value !== "string" || value.length === 0)
        throw new Error(`Missing ${name}.`);
    return value;
}
function digest(value, name) {
    const result = text(value, name);
    if (!/^sha256:[0-9a-f]{64}$/.test(result))
        throw new Error(`Invalid ${name}.`);
    return result;
}
export function parseCatalogIndex(value) {
    const root = record(value);
    if (root.schemaVersion !== "1" || !Array.isArray(root.records))
        throw new Error("Incompatible documentation catalog.");
    const indexDigest = digest(root.indexDigest, "indexDigest");
    const signature = record(root.signature);
    if (digest(signature.signedDigest, "signature.signedDigest") !== indexDigest) {
        throw new Error("Catalog signature does not bind the index digest.");
    }
    const records = root.records.map((item) => {
        const candidate = record(item);
        const pin = record(candidate.pin);
        const coordinate = record(pin.coordinate);
        const visibility = text(candidate.visibility, "visibility");
        const lifecycle = text(candidate.lifecycle, "lifecycle");
        if (!["public", "internal", "tenant", "restricted"].includes(visibility))
            throw new Error("Invalid visibility.");
        if (!["preview", "release", "deprecated", "revoked"].includes(lifecycle))
            throw new Error("Invalid lifecycle.");
        if (!Array.isArray(candidate.locales) || !Array.isArray(candidate.taskClasses))
            throw new Error("Invalid catalog facets.");
        if (coordinate.schemaMajor !== 1)
            throw new Error("Unsupported documentation schema major.");
        return {
            title: text(candidate.title, "title"),
            summary: typeof candidate.summary === "string" ? candidate.summary : "",
            ownerKey: text(candidate.ownerKey, "ownerKey"),
            visibility: visibility,
            lifecycle: lifecycle,
            locales: candidate.locales.map((entry) => text(entry, "locale")),
            taskClasses: candidate.taskClasses.map((entry) => text(entry, "taskClass")),
            compatibility: record(candidate.compatibility),
            routeKey: text(candidate.routeKey, "routeKey"),
            pin: { coordinate: {
                    ownerKey: text(coordinate.ownerKey, "coordinate.ownerKey"),
                    bundleId: text(coordinate.bundleId, "coordinate.bundleId"),
                    version: text(coordinate.version, "coordinate.version"),
                    digest: digest(coordinate.digest, "coordinate.digest"),
                    schemaMajor: 1,
                } },
        };
    });
    return {
        schemaVersion: "1",
        records,
        indexDigest,
        signature: {
            algorithm: text(signature.algorithm, "signature.algorithm"),
            keyId: text(signature.keyId, "signature.keyId"),
            signedDigest: indexDigest,
            value: text(signature.value, "signature.value"),
        },
    };
}
export function parseHumanProjection(value) {
    const root = record(value);
    if (root.layoutProfile !== "juntai.documentation.standard/v1" || !Array.isArray(root.pages)) {
        throw new Error("Incompatible human documentation projection.");
    }
    const lifecycle = text(root.lifecycle, "lifecycle");
    if (!["preview", "release", "deprecated", "revoked"].includes(lifecycle))
        throw new Error("Invalid lifecycle.");
    const search = record(root.searchIndex);
    if (search.path !== "search-index.json")
        throw new Error("Invalid search index path.");
    const pages = root.pages.map((item) => {
        const page = record(item);
        if (!Array.isArray(page.exactReferences))
            throw new Error("Invalid exact references.");
        return {
            unitId: text(page.unitId, "unitId"),
            kind: text(page.kind, "kind"),
            path: text(page.path, "path"),
            title: text(page.title, "title"),
            contentDigest: digest(page.contentDigest, "contentDigest"),
            exactReferences: page.exactReferences.map(record),
        };
    });
    return {
        bundleDigest: digest(root.bundleDigest, "bundleDigest"),
        layoutProfile: "juntai.documentation.standard/v1",
        scope: text(root.scope, "scope"),
        locale: text(root.locale, "locale"),
        pages,
        searchIndex: { path: "search-index.json", digest: digest(search.digest, "searchIndex.digest") },
        lifecycle: lifecycle,
        provenance: record(root.provenance),
        projectionDigest: digest(root.projectionDigest, "projectionDigest"),
    };
}
export function parseSearchIndex(value) {
    if (!Array.isArray(value))
        throw new Error("Invalid documentation search index.");
    return value.map((item) => {
        const entry = record(item);
        return { unitId: text(entry.unitId, "unitId"), title: text(entry.title, "title"), path: text(entry.path, "path") };
    });
}
//# sourceMappingURL=contracts.js.map