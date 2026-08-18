export const STANDARD_LAYOUT_PROFILE = "juntai.documentation.standard/v1";

const PARAMETERS = Object.freeze([
  "applicationId",
  "applicationVersionId",
  "ownerKey",
  "contributionKey",
  "bundleDigest",
  "unitId",
]);

export function defineDocumentationViewerContribution() {
  return Object.freeze({
    serviceId: "platform.documentation",
    pages: Object.freeze(["catalog", "bundle", "application-version"]),
    layoutProfile: STANDARD_LAYOUT_PROFILE,
    parameters: PARAMETERS,
  });
}

export function defineDocumentationProviderContribution(input) {
  if (!input || typeof input.ownerKey !== "string" || !input.ownerKey ||
      typeof input.routeKey !== "string" || !input.routeKey || typeof input.load !== "function") {
    throw new TypeError("ownerKey, routeKey and a build-time load function are required");
  }
  return Object.freeze({
    ownerKey: input.ownerKey,
    routeKey: input.routeKey,
    capability: "platform.documentation.provider",
    parameters: PARAMETERS,
    load: input.load,
  });
}

function element(name, text) {
  const value = document.createElement(name);
  if (text !== undefined) value.textContent = text;
  return value;
}

const SAFE_CONTENT_ELEMENTS = new Set([
  "A", "BLOCKQUOTE", "BR", "CODE", "EM", "H1", "H2", "H3", "H4", "H5", "H6",
  "HR", "LI", "OL", "P", "PRE", "STRONG", "TABLE", "TBODY", "TD", "TH", "THEAD",
  "TR", "UL",
]);
const SAFE_CONTENT_ATTRIBUTES = new Set(["aria-label", "colspan", "rowspan", "scope", "title"]);

export function safeDocumentationHref(value) {
  if (typeof value !== "string" || value.length === 0 || value.startsWith("//")) return "#";
  if (value.startsWith("#") || value.startsWith("/") || value.startsWith("./") ||
      value.startsWith("../")) return value;
  try {
    const url = new URL(value);
    return ["https:", "http:", "blob:"].includes(url.protocol) ? value : "#";
  } catch {
    return "#";
  }
}

export function sanitizeDocumentationHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = String(html);
  for (const node of template.content.querySelectorAll("*")) {
    if (!SAFE_CONTENT_ELEMENTS.has(node.tagName)) {
      node.replaceWith(document.createTextNode(node.textContent ?? ""));
      continue;
    }
    for (const attribute of [...node.attributes]) {
      if (attribute.name === "href" && node.tagName === "A") {
        node.setAttribute("href", safeDocumentationHref(attribute.value));
      } else if (!SAFE_CONTENT_ATTRIBUTES.has(attribute.name)) {
        node.removeAttribute(attribute.name);
      }
    }
  }
  return template.content.cloneNode(true);
}

export function renderDocumentationLayout(container, model) {
  if (!container || !model || model.bundleDigest?.startsWith("sha256:") !== true) {
    throw new TypeError("a container and exact documentation model are required");
  }
  container.replaceChildren();
  const root = element("article");
  root.dataset.layoutProfile = STANDARD_LAYOUT_PROFILE;
  const breadcrumbs = element("nav");
  breadcrumbs.setAttribute("aria-label", "Breadcrumb");
  const crumbs = element("ol");
  for (const item of model.breadcrumbs) {
    const row = element("li");
    if (item.href) {
      const link = element("a", item.label);
      link.href = safeDocumentationHref(item.href);
      row.append(link);
    } else row.textContent = item.label;
    crumbs.append(row);
  }
  breadcrumbs.append(crumbs);
  const header = element("header");
  header.append(element("h1", model.title));
  header.append(element("p", `${model.ownerKey} · ${model.version} · ${model.lifecycle}`));
  header.append(element("p", model.compatibility));
  if (model.lifecycle === "deprecated" || model.lifecycle === "revoked") {
    const notice = element("aside", `${model.lifecycle}: select an explicitly approved replacement.`);
    notice.setAttribute("role", "status");
    header.append(notice);
  }
  const body = element("div");
  body.className = "juntai-documentation-layout";
  const navigation = element("nav");
  navigation.setAttribute("aria-label", "Documentation");
  const links = element("ul");
  for (const item of model.navigation) {
    const row = element("li");
    const link = element("a", item.title);
    link.href = safeDocumentationHref(item.href);
    link.dataset.unitId = item.unitId;
    row.append(link);
    links.append(row);
  }
  navigation.append(links);
  const main = element("main");
  main.id = "documentation-content";
  const content = element("section");
  content.append(sanitizeDocumentationHtml(model.contentHtml));
  main.append(content);
  const references = element("section");
  references.append(element("h2", "Exact references"));
  const referenceList = element("ul");
  for (const reference of model.exactReferences) {
    referenceList.append(element("li", `${reference.kind} ${reference.id} ${reference.digest}`));
  }
  references.append(referenceList);
  main.append(references);
  body.append(navigation, main);
  const footer = element("footer", `Bundle ${model.bundleDigest}`);
  if (model.offlineDownload) {
    const download = element("a", "Download offline documentation");
    download.href = safeDocumentationHref(model.offlineDownload);
    download.download = "";
    footer.append(" ", download);
  }
  root.append(breadcrumbs, header, body, footer);
  container.append(root);
}

const HTMLElementBase = globalThis.HTMLElement ?? class {};

export class JuntaiDocumentationViewerElement extends HTMLElementBase {
  #model;
  set model(value) {
    this.#model = value;
    if (this.isConnected) renderDocumentationLayout(this, value);
  }
  get model() { return this.#model; }
  connectedCallback() {
    if (this.#model) renderDocumentationLayout(this, this.#model);
  }
}

export function registerDocumentationViewerElement(tagName = "juntai-documentation-viewer") {
  if (!globalThis.customElements) throw new Error("Custom Elements are unavailable");
  if (!globalThis.customElements.get(tagName)) {
    globalThis.customElements.define(tagName, JuntaiDocumentationViewerElement);
  }
}
