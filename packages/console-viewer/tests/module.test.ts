import { assertDeterministicConsoleModule, loadConsolePageModule, recordConsoleModule } from "@zephytiju/console-sdk/testing";
import documentationModule, { DOCUMENTATION_SERVICE_ID } from "../src/module.js";

test("registers one deterministic documentation service and one viewer contribution", async () => {
  expect(() => assertDeterministicConsoleModule(documentationModule)).not.toThrow();
  const recording = recordConsoleModule(documentationModule);
  expect(recording.services).toHaveLength(1);
  expect(recording.services[0]?.id).toBe(DOCUMENTATION_SERVICE_ID);
  expect(recording.services[0]?.pages.map((page) => page.id)).toEqual(["catalog", "bundle", "application-version"]);
  expect(recording.documentationViewerContributions).toEqual([expect.objectContaining({
    serviceId: "platform.documentation",
    layoutProfile: "juntai.documentation.standard/v1",
    parameters: ["applicationId", "applicationVersionId", "ownerKey", "contributionKey", "bundleDigest", "unitId"],
  })]);
  for (const page of recording.services[0]?.pages ?? []) {
    await expect(loadConsolePageModule(page.load)).resolves.toEqual(expect.objectContaining({ default: expect.any(Function) }));
  }
});
