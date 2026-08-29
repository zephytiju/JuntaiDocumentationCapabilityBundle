import axe from "axe-core";
import { createConsolePageContext } from "@zephytiju/console-sdk/testing";
import { render, screen } from "@testing-library/react";
import { CatalogPage } from "../src/ui.js";
import { catalog } from "./fixtures.js";

test("catalog has no automated accessibility violations", async () => {
  const context = createConsolePageContext({ fetch: async () => new Response(JSON.stringify(catalog()), { status: 200, headers: { "content-type": "application/json" } }) });
  const { container } = render(<CatalogPage context={context} />);
  await screen.findByText("Example documentation");
  const result = await axe.run(container);
  expect(result.violations).toEqual([]);
});
