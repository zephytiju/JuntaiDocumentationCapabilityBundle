import { parseCatalogIndex, parseHumanProjection } from "../src/contracts.js";
import { catalogIndexPath, documentationPagePath, offlineBundlePath, projectionPath, searchIndexPath } from "../src/paths.js";
import { catalog, projection, routeBundleDigest } from "./fixtures.js";

test("validates signed catalog and standard projection contracts", () => {
  expect(parseCatalogIndex(catalog()).records[0]?.pin.coordinate.digest).toBe(routeBundleDigest);
  expect(parseHumanProjection(projection).pages[0]?.unitId).toBe("overview");
  expect(() => parseCatalogIndex({ ...catalog(), signature: { ...catalog().signature, signedDigest: `sha256:${"0".repeat(64)}` } })).toThrow(/signature/);
});

test("constructs only same-origin immutable delivery paths", () => {
  expect(catalogIndexPath).toBe("/documentation/v1/catalog-index.json");
  expect(projectionPath(routeBundleDigest)).toContain(encodeURIComponent(routeBundleDigest));
  expect(searchIndexPath(routeBundleDigest)).toMatch(/search-index\.json$/);
  expect(documentationPagePath(routeBundleDigest, "overview")).toMatch(/pages\/overview\.html$/);
  expect(offlineBundlePath(routeBundleDigest)).toMatch(/documentation-human\.tar$/);
  expect(() => documentationPagePath("latest", "overview")).toThrow(/sha256/);
  expect(() => documentationPagePath(routeBundleDigest, "../active payload")).toThrow(/unitId/);
});
