import { createConsolePageContext } from "@zephytiju/console-sdk/testing";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApplicationVersionPage, BundlePage, CatalogPage } from "../src/ui.js";
import { applicationId, applicationLinks, applicationVersionId, catalog, projection, routeBundleDigest, search } from "./fixtures.js";

function responseFetch(visibility: "public" | "restricted" = "public") {
  return async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const path = new URL(url, "https://console.invalid").pathname;
    const body = path.endsWith("catalog-index.json") ? catalog(visibility)
      : path.endsWith("projection.json") ? projection
        : path.endsWith("search-index.json") ? search
          : applicationLinks();
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  };
}

test("catalog opens public records through the shared viewer", async () => {
  const navigate = vi.fn();
  render(<CatalogPage context={createConsolePageContext({ navigate, fetch: responseFetch() })} />);
  fireEvent.click(await screen.findByRole("button", { name: "Open exact bundle" }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ serviceId: "platform.documentation", pageId: "bundle" })));
});

test("bundle renders the standard projection in a sandboxed same-origin frame", async () => {
  const context = createConsolePageContext({
    fetch: responseFetch(),
    route: { serviceId: "platform.documentation", pageId: "bundle", params: { ownerKey: "example-owner", contributionKey: "example.bundle", bundleDigest: routeBundleDigest, unitId: "overview" } },
  });
  const { container } = render(<BundlePage context={context} />);
  const frame = await screen.findByTitle("Overview");
  expect(frame).toHaveAttribute("sandbox", "");
  expect(frame).toHaveAttribute("src", expect.stringContaining(encodeURIComponent(routeBundleDigest)));
  expect(container.querySelector("[data-layout-profile='juntai.documentation.standard/v1']")).toBeInTheDocument();
});

test("restricted application links project only the five provider scalars", async () => {
  const navigate = vi.fn();
  const context = createConsolePageContext({
    navigate,
    fetch: responseFetch("restricted"),
    route: { serviceId: "platform.documentation", pageId: "application-version", params: { applicationId, applicationVersionId } },
  });
  render(<ApplicationVersionPage context={context} />);
  fireEvent.click(await screen.findByRole("button", { name: "Open authorized provider" }));
  await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
  expect(navigate).toHaveBeenCalledWith({
    routeKey: "example.documentation",
    params: { applicationId, applicationVersionId, contributionKey: "example.bundle", bundleDigest: routeBundleDigest, unitId: "overview" },
  });
});
