export declare const STANDARD_LAYOUT_PROFILE: "juntai.documentation.standard/v1";

export interface ExactReference {
  kind: "mcp.tool" | "openapi.operation" | "schema" | "sdk.operation";
  id: string;
  digest: `sha256:${string}`;
}

export interface DocumentationViewerModel {
  title: string;
  ownerKey: string;
  version: string;
  lifecycle: "preview" | "release" | "deprecated" | "revoked";
  compatibility: string;
  bundleDigest: `sha256:${string}`;
  breadcrumbs: readonly { label: string; href?: string }[];
  navigation: readonly { unitId: string; title: string; href: string }[];
  contentHtml: string;
  exactReferences: readonly ExactReference[];
  offlineDownload?: string;
  replacement?: { title: string; href: string };
}

export interface DocumentationViewerContribution {
  serviceId: "platform.documentation";
  pages: readonly ["catalog", "bundle", "application-version"];
  layoutProfile: typeof STANDARD_LAYOUT_PROFILE;
  parameters: readonly [
    "applicationId",
    "applicationVersionId",
    "ownerKey",
    "contributionKey",
    "bundleDigest",
    "unitId",
  ];
}

export interface DocumentationProviderContribution {
  ownerKey: string;
  routeKey: string;
  capability: "platform.documentation.provider";
  parameters: DocumentationViewerContribution["parameters"];
  load: () => Promise<unknown>;
}

export declare function defineDocumentationViewerContribution(): Readonly<DocumentationViewerContribution>;
export declare function defineDocumentationProviderContribution(input: {
  ownerKey: string;
  routeKey: string;
  load: () => Promise<unknown>;
}): Readonly<DocumentationProviderContribution>;
export declare function renderDocumentationLayout(
  container: HTMLElement,
  model: DocumentationViewerModel,
): void;
export declare function safeDocumentationHref(value: unknown): string;
export declare function sanitizeDocumentationHtml(html: unknown): DocumentFragment;
export declare class JuntaiDocumentationViewerElement extends HTMLElement {
  model: DocumentationViewerModel | undefined;
}
export declare function registerDocumentationViewerElement(tagName?: string): void;
