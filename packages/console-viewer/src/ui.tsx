import {
  Button,
  Card,
  NavItem,
  StatusBadge,
  TextField,
  ThemeScope,
} from "@zephytiju/juntai-design-system";
import {
  createDocumentationViewerNavigationTarget,
  type ConsolePageContext,
  type ConsolePageProps,
} from "@zephytiju/console-sdk";
import type { ApplicationDocumentationLink } from "@zephytiju/juntai-typescript-sdk/services/platform.application-metadata";
import { useMemo, useState, type ChangeEvent, type ReactNode } from "react";
import type { CatalogIndex, CatalogRecord, HumanProjection, SearchEntry } from "./contracts.js";
import { createDocumentationGateway, DocumentationGatewayError } from "./gateway.js";
import { documentationPagePath, offlineBundlePath, requireBundleDigest, requireUnitId } from "./paths.js";
import { useResource, type ResourceState } from "./resource.js";
import { documentationViewerContribution } from "./module.js";

function Layout({ context, children }: { context: ConsolePageContext; children: ReactNode }) {
  return (
    <ThemeScope theme={context.theme.colorScheme} className="documentation-page">
      <header className="documentation-shell-header">
        <p>Juntai Console / Documentation</p>
        <h1>Documentation</h1>
      </header>
      {children}
    </ThemeScope>
  );
}

function ResourceBoundary<T>({ state, retry, children }: {
  state: ResourceState<T>;
  retry: () => void;
  children: (value: T) => ReactNode;
}) {
  if (state.status === "loading") return <div className="documentation-state" role="status">Loading exact documentation…</div>;
  if (state.status === "error") {
    const denied = state.error instanceof DocumentationGatewayError && [401, 403].includes(state.error.status ?? 0);
    return (
      <div className="documentation-state documentation-state--error" role="alert">
        <StatusBadge status={denied ? "warning" : "error"}>{denied ? "Access denied" : "Unavailable"}</StatusBadge>
        <h2>{denied ? "This documentation is restricted." : "Documentation could not be loaded."}</h2>
        <p>No catalog record, bundle content, or application link was rendered.</p>
        <Button variant="secondary" onClick={retry}>Try again</Button>
      </div>
    );
  }
  return children(state.value);
}

function lifecycleTone(value: CatalogRecord["lifecycle"]): "success" | "warning" | "error" | "draft" {
  if (value === "release") return "success";
  if (value === "revoked") return "error";
  if (value === "deprecated") return "warning";
  return "draft";
}

function publicTarget(record: CatalogRecord, unitId: string) {
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

export function CatalogPage({ context }: ConsolePageProps) {
  const gateway = useMemo(() => createDocumentationGateway(context), [context]);
  const { state, retry } = useResource((signal) => gateway.loadCatalog(signal), [gateway]);
  const [query, setQuery] = useState("");
  const openPublic = async (record: CatalogRecord) => {
    try {
      const { projection } = await gateway.loadBundle(record.pin.coordinate.digest);
      const first = projection.pages[0];
      if (!first) throw new Error("The immutable projection has no human documentation units.");
      context.navigate(publicTarget(record, first.unitId));
    } catch {
      context.notifications.show({
        severity: "error",
        message: { defaultMessage: "The exact documentation projection is unavailable." },
      });
    }
  };
  return (
    <Layout context={context}>
      <main className="documentation-main">
        <section className="documentation-intro">
          <h2>Signed catalog</h2>
          <p>Discover released documentation by stable owner, bundle, lifecycle, locale, and task class.</p>
          <TextField label="Search documentation" value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.currentTarget.value)} placeholder="Search title, owner, locale, or task class…" />
        </section>
        <ResourceBoundary state={state} retry={retry}>{(catalog) => {
          const needle = query.trim().toLowerCase();
          const records = catalog.records.filter((record) => !needle || [record.title, record.summary, record.ownerKey, ...record.locales, ...record.taskClasses].join(" ").toLowerCase().includes(needle));
          return (
            <section aria-label="Documentation catalog" className="documentation-grid">
              {records.map((record) => (
                <Card key={`${record.ownerKey}:${record.pin.coordinate.digest}`} className="documentation-card">
                  <div className="documentation-card__badges">
                    <StatusBadge status={lifecycleTone(record.lifecycle)}>{record.lifecycle}</StatusBadge>
                    <span>{record.visibility}</span>
                  </div>
                  <h3>{record.title}</h3>
                  <p>{record.summary}</p>
                  <dl>
                    <dt>Owner</dt><dd>{record.ownerKey}</dd>
                    <dt>Version</dt><dd>{record.pin.coordinate.version}</dd>
                    <dt>Locales</dt><dd>{record.locales.join(", ")}</dd>
                  </dl>
                  {record.visibility === "public" ? (
                    <Button onClick={() => void openPublic(record)}>Open exact bundle</Button>
                  ) : (
                    <p className="documentation-restricted">Open from an exact application version to preserve provider authorization.</p>
                  )}
                </Card>
              ))}
              {records.length === 0 ? <p>No matching documentation records.</p> : null}
            </section>
          );
        }}</ResourceBoundary>
      </main>
    </Layout>
  );
}

function ExactReferences({ page }: { page: HumanProjection["pages"][number] }) {
  return (
    <section className="documentation-references" aria-labelledby="exact-references-heading">
      <h3 id="exact-references-heading">Exact references</h3>
      {page.exactReferences.length === 0 ? <p>No exact API references.</p> : (
        <ul>{page.exactReferences.map((reference, index) => (
          <li key={index}>{Object.values(reference).filter((value) => typeof value === "string").join(" · ")}</li>
        ))}</ul>
      )}
    </section>
  );
}

function BundleContent({ context, ownerKey, contributionKey, routeDigest, unitId, projection, search }: {
  context: ConsolePageContext;
  ownerKey: string;
  contributionKey: string;
  routeDigest: string;
  unitId: string;
  projection: HumanProjection;
  search: readonly SearchEntry[];
}) {
  const page = projection.pages.find((candidate) => candidate.unitId === unitId);
  if (!page || !search.some((entry) => entry.unitId === unitId)) {
    return <div className="documentation-state documentation-state--error" role="alert"><h2>Documentation unit unavailable.</h2><p>The exact unit is absent from this immutable projection.</p></div>;
  }
  const navigateUnit = (targetUnitId: string) => context.navigate(createDocumentationViewerNavigationTarget(documentationViewerContribution, {
    pageId: "bundle",
    params: { ownerKey, contributionKey, bundleDigest: routeDigest, unitId: targetUnitId },
  }));
  return (
    <main className="documentation-bundle" data-layout-profile={projection.layoutProfile}>
      <nav aria-label="Documentation units" className="documentation-navigation">
        <p>{ownerKey}</p>
        {search.map((entry) => <NavItem key={entry.unitId} label={entry.title} selected={entry.unitId === unitId} onClick={() => navigateUnit(entry.unitId)} />)}
      </nav>
      <article className="documentation-content">
        <header>
          <StatusBadge status={projection.lifecycle === "release" ? "success" : projection.lifecycle === "revoked" ? "error" : "warning"}>{projection.lifecycle}</StatusBadge>
          <h2>{page.title}</h2>
          <p>Immutable unit <code>{page.unitId}</code></p>
        </header>
        <iframe
          className="documentation-frame"
          src={documentationPagePath(routeDigest, page.unitId)}
          title={page.title}
          sandbox=""
        />
        <ExactReferences page={page} />
        <footer>
          <code>{routeDigest}</code>
          <a href={offlineBundlePath(routeDigest)} download>Download offline documentation</a>
        </footer>
      </article>
    </main>
  );
}

export function BundlePage({ context }: ConsolePageProps) {
  const ownerKey = context.route.params.ownerKey ?? "";
  const contributionKey = context.route.params.contributionKey ?? "";
  const routeDigest = requireBundleDigest(context.route.params.bundleDigest ?? "");
  const unitId = requireUnitId(context.route.params.unitId ?? "");
  const gateway = useMemo(() => createDocumentationGateway(context), [context]);
  const { state, retry } = useResource((signal) => gateway.loadBundle(routeDigest, signal), [gateway, routeDigest]);
  return (
    <Layout context={context}>
      <ResourceBoundary state={state} retry={retry}>{({ projection, search }) => (
        <BundleContent context={context} ownerKey={ownerKey} contributionKey={contributionKey} routeDigest={routeDigest} unitId={unitId} projection={projection} search={search} />
      )}</ResourceBoundary>
    </Layout>
  );
}

interface ApplicationDocumentationSelection {
  readonly link: ApplicationDocumentationLink;
  readonly record: CatalogRecord | undefined;
}

function ApplicationLinks({ context, applicationId, applicationVersionId, selections }: {
  context: ConsolePageContext;
  applicationId: string;
  applicationVersionId: string;
  selections: readonly ApplicationDocumentationSelection[];
}) {
  const open = ({ link, record }: ApplicationDocumentationSelection) => {
    if (!record) return;
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
  if (selections.length === 0) return <p>No documentation contributions are associated with this application version.</p>;
  return (
    <section className="documentation-grid" aria-label="Application documentation links">
      {selections.map((selection) => (
        <Card key={`${selection.link.contribution_key}:${selection.link.bundle_digest}:${selection.link.unit_id}`}>
          <h3>{selection.record?.title ?? selection.link.contribution_key}</h3>
          <p>{selection.record?.summary ?? "The signed catalog has no matching immutable record."}</p>
          <dl><dt>Owner</dt><dd>{selection.link.owner_domain}</dd><dt>Unit</dt><dd>{selection.link.unit_id}</dd></dl>
          <Button disabled={!selection.record} onClick={() => open(selection)}>
            {selection.record?.visibility === "public" ? "Open exact bundle" : "Open authorized provider"}
          </Button>
        </Card>
      ))}
    </section>
  );
}

export function ApplicationVersionPage({ context }: ConsolePageProps) {
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
  return (
    <Layout context={context}>
      <main className="documentation-main">
        <header className="documentation-intro"><h2>Application-version documentation</h2><p>Links are projected from Application Metadata and exact-matched to the signed catalog.</p></header>
        <ResourceBoundary state={state} retry={retry}>{({ catalog, links }: { catalog: CatalogIndex; links: readonly ApplicationDocumentationLink[] }) => {
          const selections = links.map((link) => ({
            link,
            record: catalog.records.find((record) => record.ownerKey === link.owner_domain && record.routeKey === link.route_key && record.pin.coordinate.digest === link.bundle_digest),
          }));
          return <ApplicationLinks context={context} applicationId={applicationId} applicationVersionId={applicationVersionId} selections={selections} />;
        }}</ResourceBoundary>
      </main>
    </Layout>
  );
}
