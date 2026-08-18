import test from "node:test";
import assert from "node:assert/strict";
import {
  STANDARD_LAYOUT_PROFILE,
  defineDocumentationProviderContribution,
  defineDocumentationViewerContribution,
  safeDocumentationHref,
} from "../dist/index.js";

test("viewer contribution is deterministic and service-free", () => {
  const contribution = defineDocumentationViewerContribution();
  assert.equal(contribution.serviceId, "platform.documentation");
  assert.equal(contribution.layoutProfile, STANDARD_LAYOUT_PROFILE);
  assert.deepEqual(contribution.pages, ["catalog", "bundle", "application-version"]);
  assert.equal(Object.isFrozen(contribution), true);
});

test("viewer rejects active and protocol-relative link targets", () => {
  assert.equal(safeDocumentationHref("javascript:alert(1)"), "#");
  assert.equal(safeDocumentationHref("data:text/html,active"), "#");
  assert.equal(safeDocumentationHref("//outside.example/content"), "#");
  assert.equal(safeDocumentationHref("/documentation/unit"), "/documentation/unit");
  assert.equal(safeDocumentationHref("https://docs.example/unit"), "https://docs.example/unit");
});

test("provider contribution carries route identity, not runtime payload", () => {
  const load = async () => ({ default: "page" });
  const contribution = defineDocumentationProviderContribution({
    ownerKey: "generic-owner",
    routeKey: "generic.documentation",
    load,
  });
  assert.equal(contribution.capability, "platform.documentation.provider");
  assert.equal(contribution.load, load);
  assert.equal("bundleBytes" in contribution, false);
});
