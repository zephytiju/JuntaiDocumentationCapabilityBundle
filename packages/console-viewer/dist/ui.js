import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Card, NavItem, StatusBadge, TextField, ThemeScope, } from "@zephytiju/juntai-design-system";
import { createDocumentationViewerNavigationTarget, } from "@zephytiju/console-sdk";
import { useMemo, useState } from "react";
import { createDocumentationGateway, DocumentationGatewayError } from "./gateway.js";
import { documentationPagePath, offlineBundlePath, requireBundleDigest, requireUnitId } from "./paths.js";
import { useResource } from "./resource.js";
import { documentationViewerContribution } from "./module.js";
function Layout({ context, children }) {
    return (_jsxs(ThemeScope, { theme: context.theme.colorScheme, className: "documentation-page", children: [_jsxs("header", { className: "documentation-shell-header", children: [_jsx("p", { children: "Juntai Console / Documentation" }), _jsx("h1", { children: "Documentation" })] }), children] }));
}
function ResourceBoundary({ state, retry, children }) {
    if (state.status === "loading")
        return _jsx("div", { className: "documentation-state", role: "status", children: "Loading exact documentation\u2026" });
    if (state.status === "error") {
        const denied = state.error instanceof DocumentationGatewayError && [401, 403].includes(state.error.status ?? 0);
        return (_jsxs("div", { className: "documentation-state documentation-state--error", role: "alert", children: [_jsx(StatusBadge, { status: denied ? "warning" : "error", children: denied ? "Access denied" : "Unavailable" }), _jsx("h2", { children: denied ? "This documentation is restricted." : "Documentation could not be loaded." }), _jsx("p", { children: "No catalog record, bundle content, or application link was rendered." }), _jsx(Button, { variant: "secondary", onClick: retry, children: "Try again" })] }));
    }
    return children(state.value);
}
function lifecycleTone(value) {
    if (value === "release")
        return "success";
    if (value === "revoked")
        return "error";
    if (value === "deprecated")
        return "warning";
    return "draft";
}
function publicTarget(record, unitId) {
    return createDocumentationViewerNavigationTarget(documentationViewerContribution, {
        pageId: "bundle",
        params: {
            ownerKey: record.ownerKey,
            contributionKey: record.pin.coordinate.bundleId,
            bundleDigest: record.pin.coordinate.digest,
            unitId,
        },
    });
}
export function CatalogPage({ context }) {
    const gateway = useMemo(() => createDocumentationGateway(context), [context]);
    const { state, retry } = useResource((signal) => gateway.loadCatalog(signal), [gateway]);
    const [query, setQuery] = useState("");
    const openPublic = async (record) => {
        try {
            const { projection } = await gateway.loadBundle(record.pin.coordinate.digest);
            const first = projection.pages[0];
            if (!first)
                throw new Error("The immutable projection has no human documentation units.");
            context.navigate(publicTarget(record, first.unitId));
        }
        catch {
            context.notifications.show({
                severity: "error",
                message: { defaultMessage: "The exact documentation projection is unavailable." },
            });
        }
    };
    return (_jsx(Layout, { context: context, children: _jsxs("main", { className: "documentation-main", children: [_jsxs("section", { className: "documentation-intro", children: [_jsx("h2", { children: "Signed catalog" }), _jsx("p", { children: "Discover released documentation by stable owner, bundle, lifecycle, locale, and task class." }), _jsx(TextField, { label: "Search documentation", value: query, onChange: (event) => setQuery(event.currentTarget.value), placeholder: "Search title, owner, locale, or task class\u2026" })] }), _jsx(ResourceBoundary, { state: state, retry: retry, children: (catalog) => {
                        const needle = query.trim().toLowerCase();
                        const records = catalog.records.filter((record) => !needle || [record.title, record.summary, record.ownerKey, ...record.locales, ...record.taskClasses].join(" ").toLowerCase().includes(needle));
                        return (_jsxs("section", { "aria-label": "Documentation catalog", className: "documentation-grid", children: [records.map((record) => (_jsxs(Card, { className: "documentation-card", children: [_jsxs("div", { className: "documentation-card__badges", children: [_jsx(StatusBadge, { status: lifecycleTone(record.lifecycle), children: record.lifecycle }), _jsx("span", { children: record.visibility })] }), _jsx("h3", { children: record.title }), _jsx("p", { children: record.summary }), _jsxs("dl", { children: [_jsx("dt", { children: "Owner" }), _jsx("dd", { children: record.ownerKey }), _jsx("dt", { children: "Version" }), _jsx("dd", { children: record.pin.coordinate.version }), _jsx("dt", { children: "Locales" }), _jsx("dd", { children: record.locales.join(", ") })] }), record.visibility === "public" ? (_jsx(Button, { onClick: () => void openPublic(record), children: "Open exact bundle" })) : (_jsx("p", { className: "documentation-restricted", children: "Open from an exact application version to preserve provider authorization." }))] }, `${record.ownerKey}:${record.pin.coordinate.digest}`))), records.length === 0 ? _jsx("p", { children: "No matching documentation records." }) : null] }));
                    } })] }) }));
}
function ExactReferences({ page }) {
    return (_jsxs("section", { className: "documentation-references", "aria-labelledby": "exact-references-heading", children: [_jsx("h3", { id: "exact-references-heading", children: "Exact references" }), page.exactReferences.length === 0 ? _jsx("p", { children: "No exact API references." }) : (_jsx("ul", { children: page.exactReferences.map((reference, index) => (_jsx("li", { children: Object.values(reference).filter((value) => typeof value === "string").join(" · ") }, index))) }))] }));
}
function BundleContent({ context, ownerKey, contributionKey, routeDigest, unitId, projection, search }) {
    const page = projection.pages.find((candidate) => candidate.unitId === unitId);
    if (!page || !search.some((entry) => entry.unitId === unitId)) {
        return _jsxs("div", { className: "documentation-state documentation-state--error", role: "alert", children: [_jsx("h2", { children: "Documentation unit unavailable." }), _jsx("p", { children: "The exact unit is absent from this immutable projection." })] });
    }
    const navigateUnit = (targetUnitId) => context.navigate(createDocumentationViewerNavigationTarget(documentationViewerContribution, {
        pageId: "bundle",
        params: { ownerKey, contributionKey, bundleDigest: routeDigest, unitId: targetUnitId },
    }));
    return (_jsxs("main", { className: "documentation-bundle", "data-layout-profile": projection.layoutProfile, children: [_jsxs("nav", { "aria-label": "Documentation units", className: "documentation-navigation", children: [_jsx("p", { children: ownerKey }), search.map((entry) => _jsx(NavItem, { label: entry.title, selected: entry.unitId === unitId, onClick: () => navigateUnit(entry.unitId) }, entry.unitId))] }), _jsxs("article", { className: "documentation-content", children: [_jsxs("header", { children: [_jsx(StatusBadge, { status: projection.lifecycle === "release" ? "success" : projection.lifecycle === "revoked" ? "error" : "warning", children: projection.lifecycle }), _jsx("h2", { children: page.title }), _jsxs("p", { children: ["Immutable unit ", _jsx("code", { children: page.unitId })] })] }), _jsx("iframe", { className: "documentation-frame", src: documentationPagePath(routeDigest, page.unitId), title: page.title, sandbox: "" }), _jsx(ExactReferences, { page: page }), _jsxs("footer", { children: [_jsx("code", { children: routeDigest }), _jsx("a", { href: offlineBundlePath(routeDigest), download: true, children: "Download offline documentation" })] })] })] }));
}
export function BundlePage({ context }) {
    const ownerKey = context.route.params.ownerKey ?? "";
    const contributionKey = context.route.params.contributionKey ?? "";
    const routeDigest = requireBundleDigest(context.route.params.bundleDigest ?? "");
    const unitId = requireUnitId(context.route.params.unitId ?? "");
    const gateway = useMemo(() => createDocumentationGateway(context), [context]);
    const { state, retry } = useResource((signal) => gateway.loadBundle(routeDigest, signal), [gateway, routeDigest]);
    return (_jsx(Layout, { context: context, children: _jsx(ResourceBoundary, { state: state, retry: retry, children: ({ projection, search }) => (_jsx(BundleContent, { context: context, ownerKey: ownerKey, contributionKey: contributionKey, routeDigest: routeDigest, unitId: unitId, projection: projection, search: search })) }) }));
}
function ApplicationLinks({ context, applicationId, applicationVersionId, selections }) {
    const open = ({ link, record }) => {
        if (!record)
            return;
        if (record.visibility === "public") {
            context.navigate(createDocumentationViewerNavigationTarget(documentationViewerContribution, {
                pageId: "bundle",
                params: { ownerKey: record.ownerKey, contributionKey: link.contribution_key, bundleDigest: link.bundle_digest, unitId: link.unit_id },
            }));
            return;
        }
        context.navigate({
            routeKey: record.routeKey,
            params: {
                applicationId,
                applicationVersionId,
                contributionKey: link.contribution_key,
                bundleDigest: link.bundle_digest,
                unitId: link.unit_id,
            },
        });
    };
    if (selections.length === 0)
        return _jsx("p", { children: "No documentation contributions are associated with this application version." });
    return (_jsx("section", { className: "documentation-grid", "aria-label": "Application documentation links", children: selections.map((selection) => (_jsxs(Card, { children: [_jsx("h3", { children: selection.record?.title ?? selection.link.contribution_key }), _jsx("p", { children: selection.record?.summary ?? "The signed catalog has no matching immutable record." }), _jsxs("dl", { children: [_jsx("dt", { children: "Owner" }), _jsx("dd", { children: selection.link.owner_domain }), _jsx("dt", { children: "Unit" }), _jsx("dd", { children: selection.link.unit_id })] }), _jsx(Button, { disabled: !selection.record, onClick: () => open(selection), children: selection.record?.visibility === "public" ? "Open exact bundle" : "Open authorized provider" })] }, `${selection.link.contribution_key}:${selection.link.bundle_digest}:${selection.link.unit_id}`))) }));
}
export function ApplicationVersionPage({ context }) {
    const applicationId = context.route.params.applicationId ?? "";
    const applicationVersionId = context.route.params.applicationVersionId ?? "";
    const gateway = useMemo(() => createDocumentationGateway(context), [context]);
    const { state, retry } = useResource(async (signal) => {
        const [catalog, links] = await Promise.all([
            gateway.loadCatalog(signal),
            gateway.listApplicationLinks(applicationId, applicationVersionId, signal),
        ]);
        return { catalog, links };
    }, [gateway, applicationId, applicationVersionId]);
    return (_jsx(Layout, { context: context, children: _jsxs("main", { className: "documentation-main", children: [_jsxs("header", { className: "documentation-intro", children: [_jsx("h2", { children: "Application-version documentation" }), _jsx("p", { children: "Links are projected from Application Metadata and exact-matched to the signed catalog." })] }), _jsx(ResourceBoundary, { state: state, retry: retry, children: ({ catalog, links }) => {
                        const selections = links.map((link) => ({
                            link,
                            record: catalog.records.find((record) => record.ownerKey === link.owner_domain && record.routeKey === link.route_key && record.pin.coordinate.digest === link.bundle_digest),
                        }));
                        return _jsx(ApplicationLinks, { context: context, applicationId: applicationId, applicationVersionId: applicationVersionId, selections: selections });
                    } })] }) }));
}
//# sourceMappingURL=ui.js.map