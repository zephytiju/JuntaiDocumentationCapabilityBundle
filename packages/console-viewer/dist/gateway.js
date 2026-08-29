import { createClient, listApplicationDocumentationLinks, } from "@zephytiju/juntai-typescript-sdk/services/platform.application-metadata";
import { parseCatalogIndex, parseHumanProjection, parseSearchIndex } from "./contracts.js";
import { catalogIndexPath, projectionPath, searchIndexPath } from "./paths.js";
export class DocumentationGatewayError extends Error {
    status;
    constructor(message, status) {
        super(message);
        this.status = status;
        this.name = "DocumentationGatewayError";
    }
}
function origin() {
    const value = globalThis.location?.origin;
    if (!value || value === "null")
        throw new Error("The Console origin is unavailable.");
    return value;
}
async function json(context, path, signal) {
    const response = await context.fetch(path, {
        headers: { Accept: "application/json", "X-Correlation-ID": context.correlationIds.create() },
        ...(signal ? { signal } : {}),
    });
    if (!response.ok)
        throw new DocumentationGatewayError("Documentation data is unavailable.", response.status);
    return response.json();
}
function validId(value, pattern, name) {
    if (!pattern.test(value))
        throw new DocumentationGatewayError(`Invalid ${name}.`);
    return value;
}
export function createDocumentationGateway(context) {
    const client = createClient({ baseUrl: origin(), fetch: context.fetch });
    return {
        async loadCatalog(signal) {
            return parseCatalogIndex(await json(context, catalogIndexPath, signal));
        },
        async loadBundle(bundleDigest, signal) {
            const [projection, search] = await Promise.all([
                json(context, projectionPath(bundleDigest), signal),
                json(context, searchIndexPath(bundleDigest), signal),
            ]);
            return { projection: parseHumanProjection(projection), search: parseSearchIndex(search) };
        },
        async listApplicationLinks(applicationId, applicationVersionId, signal) {
            validId(applicationId, /^app_[0-9a-f]{32}$/, "applicationId");
            validId(applicationVersionId, /^appv_[0-9a-f]{32}$/, "applicationVersionId");
            const result = await listApplicationDocumentationLinks({
                client,
                path: { application_id: applicationId, version_id: applicationVersionId },
                headers: { "X-Correlation-ID": context.correlationIds.create() },
                ...(signal ? { signal } : {}),
            });
            if (result.data === undefined)
                throw new DocumentationGatewayError("Application documentation is unavailable.", result.response?.status);
            return result.data.items;
        },
    };
}
//# sourceMappingURL=gateway.js.map