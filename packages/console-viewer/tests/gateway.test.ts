import { createConsolePageContext } from "@zephytiju/console-sdk/testing";
import { createDocumentationGateway } from "../src/gateway.js";
import { applicationId, applicationLinks, applicationVersionId, catalog, projection, routeBundleDigest, search } from "./fixtures.js";

test("uses injected same-origin fetch for catalog, projections, and Application Metadata", async () => {
  const requests: Request[] = [];
  const context = createConsolePageContext({ fetch: async (input, init) => {
    const request = input instanceof Request ? input : new Request(new URL(String(input), globalThis.location.origin), init);
    requests.push(request);
    const path = new URL(request.url, "https://console.invalid").pathname;
    const body = path.endsWith("catalog-index.json") ? catalog()
      : path.endsWith("projection.json") ? projection
        : path.endsWith("search-index.json") ? search
          : applicationLinks();
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  } });
  const gateway = createDocumentationGateway(context);
  await gateway.loadCatalog();
  await gateway.loadBundle(routeBundleDigest);
  const links = await gateway.listApplicationLinks(applicationId, applicationVersionId);
  expect(links[0]?.unit_id).toBe("overview");
  expect(requests).toHaveLength(4);
  expect(requests.map((request) => request.url).join("\n")).not.toMatch(/registry|oci|meridian|storage/i);
  expect(requests.every((request) => request.headers.has("x-correlation-id"))).toBe(true);
});
