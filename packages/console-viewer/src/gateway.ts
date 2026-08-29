import type { ConsolePageContext } from "@zephytiju/console-sdk";
import {
  createClient,
  listApplicationDocumentationLinks,
  type ApplicationDocumentationLink,
} from "@zephytiju/juntai-typescript-sdk/services/platform.application-metadata";
import { parseCatalogIndex, parseHumanProjection, parseSearchIndex, type CatalogIndex, type HumanProjection, type SearchEntry } from "./contracts.js";
import { catalogIndexPath, projectionPath, searchIndexPath } from "./paths.js";

export class DocumentationGatewayError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "DocumentationGatewayError";
  }
}

function origin(): string {
  const value = globalThis.location?.origin;
  if (!value || value === "null") throw new Error("The Console origin is unavailable.");
  return value;
}

async function json(context: ConsolePageContext, path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await context.fetch(path, {
    headers: { Accept: "application/json", "X-Correlation-ID": context.correlationIds.create() },
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) throw new DocumentationGatewayError("Documentation data is unavailable.", response.status);
  return response.json();
}

function validId(value: string, pattern: RegExp, name: string): string {
  if (!pattern.test(value)) throw new DocumentationGatewayError(`Invalid ${name}.`);
  return value;
}

export interface DocumentationGateway {
  loadCatalog(signal?: AbortSignal): Promise<CatalogIndex>;
  loadBundle(bundleDigest: string, signal?: AbortSignal): Promise<{ projection: HumanProjection; search: readonly SearchEntry[] }>;
  listApplicationLinks(applicationId: string, applicationVersionId: string, signal?: AbortSignal): Promise<readonly ApplicationDocumentationLink[]>;
}

export function createDocumentationGateway(context: ConsolePageContext): DocumentationGateway {
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
      if (result.data === undefined) throw new DocumentationGatewayError("Application documentation is unavailable.", result.response?.status);
      return result.data.items;
    },
  };
}
