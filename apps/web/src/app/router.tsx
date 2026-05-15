import { Navigate, createBrowserRouter, useLocation } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { CatalogPage } from "../pages/CatalogPage";
import { CatalogProductDetailPage } from "../pages/CatalogProductDetailPage";
import { DashboardPage } from "../pages/DashboardPage";
import { FiltersManagerPage } from "../pages/FiltersManagerPage";
import { JobDetailPage } from "../pages/JobDetailPage";
import { JobsPage } from "../pages/JobsPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PrepareJobPage } from "../pages/PrepareJobPage";
import { PriceMonitoringAlertsPage } from "../pages/PriceMonitoringAlertsPage";
import { PriceMonitoringExecutionsPage } from "../pages/PriceMonitoringExecutionsPage";
import { PriceMonitoringPage } from "../pages/PriceMonitoringPage";
import { ProductFactoryWorkflowPage } from "../pages/ProductFactoryWorkflowPage";
import { PublishJobPage } from "../pages/PublishJobPage";
import { RenderJobPage } from "../pages/RenderJobPage";
import { SourceUrlAgentRunsPage } from "../pages/SourceUrlAgentRunsPage";
import { SourceUrlCandidatesPage } from "../pages/SourceUrlCandidatesPage";
import { VendorSourceCaptureRunsPage } from "../pages/VendorSourceCaptureRunsPage";
import { VendorSourceImportsPage } from "../pages/VendorSourceImportsPage";
import { VendorSourceUrlsPage } from "../pages/VendorSourceUrlsPage";

function RedirectWithSearch({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={`${to}${location.search}`} replace />;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "catalog", element: <CatalogPage /> },
      { path: "catalog/products/:catalogProductId", element: <CatalogProductDetailPage /> },
      { path: "price-monitoring", element: <PriceMonitoringPage /> },
      { path: "price-monitoring/executions", element: <PriceMonitoringExecutionsPage /> },
      { path: "price-monitoring/alerts", element: <PriceMonitoringAlertsPage /> },
      { path: "find-source", element: <RedirectWithSearch to="/find-source/runs" /> },
      { path: "find-source/runs", element: <SourceUrlAgentRunsPage /> },
      { path: "find-source/candidates", element: <SourceUrlCandidatesPage /> },
      { path: "vendor-sources", element: <RedirectWithSearch to="/vendor-sources/source-urls" /> },
      { path: "vendor-sources/runs", element: <RedirectWithSearch to="/find-source/runs" /> },
      { path: "vendor-sources/candidates", element: <RedirectWithSearch to="/find-source/candidates" /> },
      { path: "vendor-sources/source-urls", element: <VendorSourceUrlsPage /> },
      { path: "vendor-sources/captures", element: <VendorSourceCaptureRunsPage /> },
      { path: "vendor-sources/imports", element: <VendorSourceImportsPage /> },
      { path: "product-factory", element: <ProductFactoryWorkflowPage /> },
      { path: "product-factory/filters", element: <FiltersManagerPage /> },
      { path: "product-factory/:model", element: <ProductFactoryWorkflowPage /> },
      { path: "pipeline", element: <ProductFactoryWorkflowPage /> },
      { path: "pipeline/:model", element: <ProductFactoryWorkflowPage /> },
      { path: "prepare", element: <PrepareJobPage /> },
      { path: "render", element: <RenderJobPage /> },
      { path: "publish", element: <PublishJobPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "jobs/:jobId", element: <JobDetailPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
