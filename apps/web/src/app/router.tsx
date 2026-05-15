import { Suspense, lazy, type ComponentType, type ReactElement } from "react";
import { Navigate, createBrowserRouter, useLocation } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/layout/StateBlocks";
import { NotFoundPage } from "../pages/NotFoundPage";

const DashboardPage = lazy(() => import("../pages/DashboardPage").then(({ DashboardPage }) => ({ default: DashboardPage })));
const CatalogPage = lazy(() => import("../pages/CatalogPage").then(({ CatalogPage }) => ({ default: CatalogPage })));
const CatalogProductDetailPage = lazy(() =>
  import("../pages/CatalogProductDetailPage").then(({ CatalogProductDetailPage }) => ({
    default: CatalogProductDetailPage,
  })),
);
const PriceMonitoringPage = lazy(() =>
  import("../pages/PriceMonitoringPage").then(({ PriceMonitoringPage }) => ({ default: PriceMonitoringPage })),
);
const PriceMonitoringExecutionsPage = lazy(() =>
  import("../pages/PriceMonitoringExecutionsPage").then(({ PriceMonitoringExecutionsPage }) => ({
    default: PriceMonitoringExecutionsPage,
  })),
);
const PriceMonitoringAlertsPage = lazy(() =>
  import("../pages/PriceMonitoringAlertsPage").then(({ PriceMonitoringAlertsPage }) => ({
    default: PriceMonitoringAlertsPage,
  })),
);
const SourceUrlAgentRunsPage = lazy(() =>
  import("../pages/SourceUrlAgentRunsPage").then(({ SourceUrlAgentRunsPage }) => ({
    default: SourceUrlAgentRunsPage,
  })),
);
const SourceUrlCandidatesPage = lazy(() =>
  import("../pages/SourceUrlCandidatesPage").then(({ SourceUrlCandidatesPage }) => ({
    default: SourceUrlCandidatesPage,
  })),
);
const VendorSourceUrlsPage = lazy(() =>
  import("../pages/VendorSourceUrlsPage").then(({ VendorSourceUrlsPage }) => ({ default: VendorSourceUrlsPage })),
);
const VendorSourceCaptureRunsPage = lazy(() =>
  import("../pages/VendorSourceCaptureRunsPage").then(({ VendorSourceCaptureRunsPage }) => ({
    default: VendorSourceCaptureRunsPage,
  })),
);
const VendorSourceImportsPage = lazy(() =>
  import("../pages/VendorSourceImportsPage").then(({ VendorSourceImportsPage }) => ({
    default: VendorSourceImportsPage,
  })),
);
const ProductFactoryWorkflowPage = lazy(() =>
  import("../pages/ProductFactoryWorkflowPage").then(({ ProductFactoryWorkflowPage }) => ({
    default: ProductFactoryWorkflowPage,
  })),
);
const FiltersManagerPage = lazy(() =>
  import("../pages/FiltersManagerPage").then(({ FiltersManagerPage }) => ({ default: FiltersManagerPage })),
);
const PrepareJobPage = lazy(() =>
  import("../pages/PrepareJobPage").then(({ PrepareJobPage }) => ({ default: PrepareJobPage })),
);
const RenderJobPage = lazy(() =>
  import("../pages/RenderJobPage").then(({ RenderJobPage }) => ({ default: RenderJobPage })),
);
const PublishJobPage = lazy(() =>
  import("../pages/PublishJobPage").then(({ PublishJobPage }) => ({ default: PublishJobPage })),
);
const JobsPage = lazy(() => import("../pages/JobsPage").then(({ JobsPage }) => ({ default: JobsPage })));
const JobDetailPage = lazy(() =>
  import("../pages/JobDetailPage").then(({ JobDetailPage }) => ({ default: JobDetailPage })),
);

function RedirectWithSearch({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={`${to}${location.search}`} replace />;
}

function RouteLoadingFallback() {
  return <LoadingState label="Loading page..." />;
}

function withPageSuspense(Page: ComponentType): ReactElement {
  return (
    <Suspense fallback={<RouteLoadingFallback />}>
      <Page />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: withPageSuspense(DashboardPage) },
      { path: "catalog", element: withPageSuspense(CatalogPage) },
      { path: "catalog/products/:catalogProductId", element: withPageSuspense(CatalogProductDetailPage) },
      { path: "price-monitoring", element: withPageSuspense(PriceMonitoringPage) },
      { path: "price-monitoring/executions", element: withPageSuspense(PriceMonitoringExecutionsPage) },
      { path: "price-monitoring/alerts", element: withPageSuspense(PriceMonitoringAlertsPage) },
      { path: "find-source", element: <RedirectWithSearch to="/find-source/runs" /> },
      { path: "find-source/runs", element: withPageSuspense(SourceUrlAgentRunsPage) },
      { path: "find-source/candidates", element: withPageSuspense(SourceUrlCandidatesPage) },
      { path: "vendor-sources", element: <RedirectWithSearch to="/vendor-sources/source-urls" /> },
      { path: "vendor-sources/runs", element: <RedirectWithSearch to="/find-source/runs" /> },
      { path: "vendor-sources/candidates", element: <RedirectWithSearch to="/find-source/candidates" /> },
      { path: "vendor-sources/source-urls", element: withPageSuspense(VendorSourceUrlsPage) },
      { path: "vendor-sources/captures", element: withPageSuspense(VendorSourceCaptureRunsPage) },
      { path: "vendor-sources/imports", element: withPageSuspense(VendorSourceImportsPage) },
      { path: "product-factory", element: withPageSuspense(ProductFactoryWorkflowPage) },
      { path: "product-factory/filters", element: withPageSuspense(FiltersManagerPage) },
      { path: "product-factory/:model", element: withPageSuspense(ProductFactoryWorkflowPage) },
      { path: "pipeline", element: withPageSuspense(ProductFactoryWorkflowPage) },
      { path: "pipeline/:model", element: withPageSuspense(ProductFactoryWorkflowPage) },
      { path: "prepare", element: withPageSuspense(PrepareJobPage) },
      { path: "render", element: withPageSuspense(RenderJobPage) },
      { path: "publish", element: withPageSuspense(PublishJobPage) },
      { path: "jobs", element: withPageSuspense(JobsPage) },
      { path: "jobs/:jobId", element: withPageSuspense(JobDetailPage) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
