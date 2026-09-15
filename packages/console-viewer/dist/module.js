import { defineConsoleModule, defineDocumentationViewerContribution, defineService, } from "@zephytiju/console-sdk";
export const DOCUMENTATION_MODULE_ID = "juntai-documentation-viewer";
export const DOCUMENTATION_SERVICE_ID = "platform.documentation";
export const documentationViewerContribution = defineDocumentationViewerContribution({
    serviceId: DOCUMENTATION_SERVICE_ID,
    pages: ["catalog", "bundle", "application-version"],
    layoutProfile: "juntai.documentation.standard/v1",
    parameters: [
        "applicationId",
        "applicationVersionId",
        "ownerKey",
        "contributionKey",
        "bundleDigest",
        "unitId",
    ],
});
const documentationService = defineService({
    id: DOCUMENTATION_SERVICE_ID,
    ownerModuleId: DOCUMENTATION_MODULE_ID,
    displayName: { defaultMessage: "Documentation" },
    summary: { defaultMessage: "Browse signed documentation catalogs and exact immutable bundles." },
    category: "Developer Tools",
    tags: ["documentation", "catalog", "applications"],
    icon: { name: "service" },
    discoveryPermissions: [{ resource: "documentation", action: "read" }],
    pages: [
        {
            id: "catalog",
            kind: "overview",
            path: "/",
            label: { defaultMessage: "Documentation catalog" },
            permissions: [{ resource: "documentation", action: "read" }],
            load: () => import("./pages/CatalogPage.js"),
        },
        {
            id: "bundle",
            kind: "custom",
            path: "/bundles/:ownerKey/:contributionKey/:bundleDigest/:unitId",
            label: { defaultMessage: "Documentation bundle" },
            permissions: [{ resource: "documentation", action: "read" }],
            load: () => import("./pages/BundlePage.js"),
        },
        {
            id: "application-version",
            kind: "custom",
            path: "/applications/:applicationId/versions/:applicationVersionId",
            label: { defaultMessage: "Application documentation" },
            permissions: [{ resource: "documentation", action: "read" }],
            load: () => import("./pages/ApplicationVersionPage.js"),
        },
    ],
});
export const documentationModule = defineConsoleModule({
    id: DOCUMENTATION_MODULE_ID,
    version: "2.0.3-local.prism-sdk.1",
    owner: {
        team: "data-intel-platform",
        repository: "zephytiju/JuntaiDocumentationCapabilityBundle",
    },
    compatibility: {
        console: "^1.0.0",
        sdk: ">=2.1.0 <=2.2.0",
        react: "^19.0.0",
        typescriptSdk: ">=3.9.0-local.prism-preview.0 <=3.9.0-local.prism-preview.0",
    },
    contributions: {
        documentationViewerContributions: [documentationViewerContribution],
    },
    register(registrar) {
        registrar.registerService(documentationService);
    },
});
export default documentationModule;
//# sourceMappingURL=module.js.map