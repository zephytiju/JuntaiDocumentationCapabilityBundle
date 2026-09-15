import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(new URL("../", import.meta.url).pathname);

async function sourceFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  return (await Promise.all(entries.map((entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(target) : /\.tsx?$/.test(entry.name) ? [target] : [];
  }))).flat();
}

const allowedPackages = new Set([
  "@zephytiju/console-sdk",
  "@zephytiju/juntai-design-system",
  "@zephytiju/juntai-typescript-sdk/services/platform.application-metadata",
  "react",
  "react/jsx-runtime",
]);
const forbidden = [
  [/\b(?:accessToken|refreshToken|bearerToken|secret|credential)\b/i, "credential material"],
  [/\b(?:eventBus|globalStore|localStorage|sessionStorage)\b/, "shared or persisted authority"],
  [/\b(?:Registry|OCI|Meridian|Artifact|Configuration)(?:Client|Transport)\b/, "foreign infrastructure client"],
  [/https?:\/\//, "direct protected origin"],
] as const;

const failures: string[] = [];
for (const file of await sourceFiles(path.join(root, "src"))) {
  const content = await readFile(file, "utf8");
  for (const match of content.matchAll(/from\s+["']([^"']+)["']/g)) {
    const specifier = match[1];
    if (specifier && !specifier.startsWith(".") && !allowedPackages.has(specifier)) {
      failures.push(`${path.relative(root, file)} imports unauthorized package ${specifier}`);
    }
  }
  for (const [pattern, label] of forbidden) {
    if (pattern.test(content)) failures.push(`${path.relative(root, file)} contains ${label}`);
  }
}

const packageJson = JSON.parse(await readFile(path.join(root, "package.json"), "utf8")) as {
  dependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
};
for (const [name, version] of Object.entries({
  "@zephytiju/juntai-design-system": "0.1.0",
  "@zephytiju/juntai-typescript-sdk": "3.9.0-local.prism-preview.0",
})) {
  if (packageJson.dependencies?.[name] !== version) failures.push(`${name} must be pinned to ${version}`);
}
if (packageJson.peerDependencies?.["@zephytiju/console-sdk"] !== ">=2.1.0 <=2.2.0") {
  failures.push("@zephytiju/console-sdk must retain the bounded range >=2.1.0 <=2.2.0");
}
if (failures.length) throw new Error(`Boundary verification failed:\n${failures.join("\n")}`);
console.log("Documentation Console boundary verified.");
