export type DocumentationVisibility = "public" | "internal" | "tenant" | "restricted";
export type DocumentationLifecycle = "preview" | "release" | "deprecated" | "revoked";
export interface CatalogRecord {
    readonly title: string;
    readonly summary: string;
    readonly ownerKey: string;
    readonly visibility: DocumentationVisibility;
    readonly lifecycle: DocumentationLifecycle;
    readonly locales: readonly string[];
    readonly taskClasses: readonly string[];
    readonly compatibility: Readonly<Record<string, unknown>>;
    readonly routeKey: string;
    readonly pin: {
        readonly coordinate: {
            readonly ownerKey: string;
            readonly bundleId: string;
            readonly version: string;
            readonly digest: string;
            readonly schemaMajor: 1;
        };
    };
}
export interface CatalogIndex {
    readonly schemaVersion: "1";
    readonly records: readonly CatalogRecord[];
    readonly indexDigest: string;
    readonly signature: {
        readonly algorithm: string;
        readonly keyId: string;
        readonly signedDigest: string;
        readonly value: string;
    };
}
export interface HumanProjectionPage {
    readonly unitId: string;
    readonly kind: string;
    readonly path: string;
    readonly title: string;
    readonly contentDigest: string;
    readonly exactReferences: readonly Readonly<Record<string, unknown>>[];
}
export interface HumanProjection {
    readonly bundleDigest: string;
    readonly layoutProfile: "juntai.documentation.standard/v1";
    readonly scope: string;
    readonly locale: string;
    readonly pages: readonly HumanProjectionPage[];
    readonly searchIndex: {
        readonly path: "search-index.json";
        readonly digest: string;
    };
    readonly lifecycle: DocumentationLifecycle;
    readonly provenance: Readonly<Record<string, unknown>>;
    readonly projectionDigest: string;
}
export interface SearchEntry {
    readonly unitId: string;
    readonly title: string;
    readonly path: string;
}
export declare function parseCatalogIndex(value: unknown): CatalogIndex;
export declare function parseHumanProjection(value: unknown): HumanProjection;
export declare function parseSearchIndex(value: unknown): readonly SearchEntry[];
//# sourceMappingURL=contracts.d.ts.map