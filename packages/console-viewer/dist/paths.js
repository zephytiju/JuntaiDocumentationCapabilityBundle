const DIGEST = /^sha256:[0-9a-f]{64}$/;
const UNIT_ID = /^[a-z0-9][a-z0-9._/-]{1,199}$/;
export function requireBundleDigest(value) {
    if (!DIGEST.test(value))
        throw new Error("An exact sha256 bundleDigest is required.");
    return value;
}
export function requireUnitId(value) {
    if (!UNIT_ID.test(value))
        throw new Error("A stable documentation unitId is required.");
    return value;
}
export const catalogIndexPath = "/documentation/v1/catalog-index.json";
function projectionRoot(bundleDigest) {
    return `/documentation/v1/projections/${encodeURIComponent(requireBundleDigest(bundleDigest))}`;
}
export function projectionPath(bundleDigest) {
    return `${projectionRoot(bundleDigest)}/projection.json`;
}
export function searchIndexPath(bundleDigest) {
    return `${projectionRoot(bundleDigest)}/search-index.json`;
}
export function documentationPagePath(bundleDigest, unitId) {
    return `${projectionRoot(bundleDigest)}/pages/${encodeURIComponent(requireUnitId(unitId))}.html`;
}
export function offlineBundlePath(bundleDigest) {
    return `${projectionRoot(bundleDigest)}/documentation-human.tar`;
}
//# sourceMappingURL=paths.js.map