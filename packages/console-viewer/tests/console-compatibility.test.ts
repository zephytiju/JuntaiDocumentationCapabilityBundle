import { describe, expect, it } from "vitest";
import { CONSOLE_SDK_VERSION } from "@zephytiju/console-sdk";
import { assertDeterministicConsoleModule } from "@zephytiju/console-sdk/testing";
import module from "../src/module.js";

describe("bounded Console SDK compatibility", () => {
  it.each(["2.1.0", "2.2.0"])("accepts supported SDK %s", (sdkVersion) => {
    expect(() => assertDeterministicConsoleModule(module, { compatibilityTarget: { consoleVersion: "1.1.0", sdkVersion, reactVersion: "19.2.7", typescriptSdkVersion: "3.9.0-local.prism-preview.0" } })).not.toThrow();
  });
  it.each(["2.0.0", "2.2.1", "3.0.0"])("rejects unsupported SDK %s", (sdkVersion) => {
    expect(() => assertDeterministicConsoleModule(module, { compatibilityTarget: { consoleVersion: "1.1.0", sdkVersion, reactVersion: "19.2.7", typescriptSdkVersion: "3.9.0-local.prism-preview.0" } })).toThrow();
  });
  it("runs against an installed supported SDK", () => {
    expect(["2.1.0", "2.2.0"]).toContain(CONSOLE_SDK_VERSION);
  });
});
