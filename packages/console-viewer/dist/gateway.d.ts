import type { ConsolePageContext } from "@zephytiju/console-sdk";
import { type ApplicationDocumentationLink } from "@zephytiju/juntai-typescript-sdk/services/platform.application-metadata";
import { type CatalogIndex, type HumanProjection, type SearchEntry } from "./contracts.js";
export declare class DocumentationGatewayError extends Error {
    readonly status?: number | undefined;
    constructor(message: string, status?: number | undefined);
}
export interface DocumentationGateway {
    loadCatalog(signal?: AbortSignal): Promise<CatalogIndex>;
    loadBundle(bundleDigest: string, signal?: AbortSignal): Promise<{
        projection: HumanProjection;
        search: readonly SearchEntry[];
    }>;
    listApplicationLinks(applicationId: string, applicationVersionId: string, signal?: AbortSignal): Promise<readonly ApplicationDocumentationLink[]>;
}
export declare function createDocumentationGateway(context: ConsolePageContext): DocumentationGateway;
//# sourceMappingURL=gateway.d.ts.map