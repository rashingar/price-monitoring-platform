import { NavLink, Outlet, useLocation } from "react-router-dom";
import { GlobalJobsProvider } from "../../hooks/useGlobalJobs";
import { PipelineRunProvider } from "../../hooks/usePipelineRun";

const platformNavItems = [
  { to: "/", label: "Dashboard" },
  { to: "/catalog", label: "Catalog" },
  { to: "/csv-bridge", label: "CSV/Bridge" },
  { to: "/price-monitoring", label: "Price Monitoring" },
  { to: "/price-monitoring/alerts", label: "Price Alerts" },
  { to: "/vendor-sources", label: "Vendor Sources" },
  { to: "/product-agent", label: "Product-Agent" },
];

const catalogNavItems = [
  { to: "/catalog", label: "Products" },
];

const vendorSourcesNavItems = [
  { to: "/vendor-sources/runs", label: "Discovery Runs" },
  { to: "/vendor-sources/candidates", label: "Candidates" },
  { to: "/vendor-sources/source-urls", label: "Source URLs / Coverage" },
  { to: "/vendor-sources/captures", label: "Capture Runs" },
  { to: "/vendor-sources/imports", label: "Imports" },
];

const productAgentNavItems = [
  { to: "/product-agent", label: "Pipeline" },
  { to: "/product-agent/filters", label: "Filters Manager" },
  { to: "/prepare", label: "Prepare" },
  { to: "/render", label: "Render" },
  { to: "/publish", label: "Publish" },
  { to: "/jobs", label: "Jobs" },
];

const productAgentPaths = new Set([
  "/product-agent",
  "/product-agent/filters",
  "/pipeline",
  "/prepare",
  "/render",
  "/publish",
  "/jobs",
]);

const priceMonitoringNavItems = [
  { to: "/price-monitoring", label: "Workflow" },
  { to: "/price-monitoring/executions", label: "Executions" },
  { to: "/price-monitoring/alerts", label: "Alerts" },
];

export function AppShell() {
  const location = useLocation();
  const isProductAgentSection =
    productAgentPaths.has(location.pathname) ||
    location.pathname.startsWith("/product-agent/") ||
    location.pathname.startsWith("/pipeline/") ||
    location.pathname.startsWith("/jobs/");
  const isPriceMonitoringSection = location.pathname.startsWith("/price-monitoring");
  const isCatalogSection = location.pathname.startsWith("/catalog");
  const isVendorSourcesSection = location.pathname.startsWith("/vendor-sources");

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local commerce operations</p>
          <h1>Product Agent Platform</h1>
        </div>
        <nav className="nav-links" aria-label="Primary navigation">
          {platformNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => {
                const isProductAgentActive =
                  item.to === "/product-agent" && isProductAgentSection;
                const isPriceMonitoringActive =
                  item.to === "/price-monitoring" && isPriceMonitoringSection;
                const isCatalogActive = item.to === "/catalog" && isCatalogSection;
                const isVendorSourcesActive =
                  item.to === "/vendor-sources" && isVendorSourcesSection;
                return isActive ||
                  isProductAgentActive ||
                  isPriceMonitoringActive ||
                  isCatalogActive ||
                  isVendorSourcesActive
                  ? "nav-link active"
                  : "nav-link";
              }}
              end={item.to === "/"}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      {isCatalogSection ? (
        <nav className="subnav catalog-subnav" aria-label="Catalog navigation">
          {catalogNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/catalog"}
              className={({ isActive }) => (isActive ? "subnav-link active" : "subnav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
      {isProductAgentSection ? (
        <nav className="subnav" aria-label="Product-Agent navigation">
          {productAgentNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/product-agent"}
              className={({ isActive }) => (isActive ? "subnav-link active" : "subnav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
      {isVendorSourcesSection ? (
        <nav className="subnav vendor-sources-subnav" aria-label="Vendor Sources navigation">
          {vendorSourcesNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={
                item.to === "/vendor-sources/runs" ||
                item.to === "/vendor-sources/source-urls" ||
                item.to === "/vendor-sources/captures" ||
                item.to === "/vendor-sources/imports"
              }
              className={({ isActive }) => (isActive ? "subnav-link active" : "subnav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
      {isPriceMonitoringSection ? (
        <nav className="subnav price-monitoring-subnav" aria-label="Price Monitoring navigation">
          {priceMonitoringNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/price-monitoring"}
              className={({ isActive }) => (isActive ? "subnav-link active" : "subnav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
      <GlobalJobsProvider>
        <PipelineRunProvider>
          <main className="main-content">
            <Outlet />
          </main>
        </PipelineRunProvider>
      </GlobalJobsProvider>
    </div>
  );
}
