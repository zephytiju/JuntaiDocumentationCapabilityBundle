export declare const DOCUMENTATION_MODULE_ID = "juntai-documentation-viewer";
export declare const DOCUMENTATION_SERVICE_ID = "platform.documentation";
export declare const documentationViewerContribution: {
    readonly serviceId: "platform.documentation";
    readonly pages: readonly ["catalog", "bundle", "application-version"];
    readonly layoutProfile: "juntai.documentation.standard/v1";
    readonly parameters: readonly ["applicationId", "applicationVersionId", "ownerKey", "contributionKey", "bundleDigest", "unitId"];
};
export declare const documentationModule: {
    readonly id: "juntai-documentation-viewer";
    readonly version: "2.0.3-local.prism-sdk.0";
    readonly owner: {
        readonly team: "data-intel-platform";
        readonly repository: "zephytiju/JuntaiDocumentationCapabilityBundle";
    };
    readonly compatibility: {
        readonly console: "^1.0.0";
        readonly sdk: ">=2.1.0 <=2.2.0";
        readonly react: "^19.0.0";
        readonly typescriptSdk: ">=3.9.0-local.prism-preview.0 <=3.9.0-local.prism-preview.0";
    };
    readonly contributions: {
        readonly documentationViewerContributions: readonly [{
            readonly serviceId: "platform.documentation";
            readonly pages: readonly ["catalog", "bundle", "application-version"];
            readonly layoutProfile: "juntai.documentation.standard/v1";
            readonly parameters: readonly ["applicationId", "applicationVersionId", "ownerKey", "contributionKey", "bundleDigest", "unitId"];
        }];
    };
    readonly register: (registrar: import("@zephytiju/console-sdk").ConsoleRegistrar) => void;
};
export default documentationModule;
//# sourceMappingURL=module.d.ts.map