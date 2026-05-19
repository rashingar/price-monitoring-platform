import { NavLink, Outlet, useLocation } from "react-router-dom";
import { ThemeToggle } from "../../features/theme/ThemeToggle";
import { GlobalJobsProvider } from "../../hooks/useGlobalJobs";
import { PipelineRunProvider } from "../../hooks/usePipelineRun";

const platformNavItems = [
  { to: "/", label: "Dashboard" },
  { to: "/catalog", label: "Catalog" },
  { to: "/price-monitoring", label: "Price Monitoring" },
  { to: "/find-source", label: "Find Source" },
  { to: "/vendor-sources", label: "Vendor Sources" },
  { to: "/product-factory", label: "Product Factory" },
];

const catalogNavItems = [
  { to: "/catalog", label: "Products" },
];

const vendorSourcesNavItems = [
  { to: "/vendor-sources/source-urls", label: "Source URLs / Coverage" },
  { to: "/vendor-sources/source-health", label: "Source Health" },
  { to: "/vendor-sources/captures", label: "Capture Runs" },
  { to: "/vendor-sources/imports", label: "Imports" },
];

const findSourceNavItems = [
  { to: "/find-source/runs", label: "Runs" },
  { to: "/find-source/candidates", label: "Candidates" },
];

const productFactoryNavItems = [
  { to: "/product-factory", label: "Pipeline" },
  { to: "/product-factory/batch-intake", label: "Batch Intake" },
  { to: "/product-factory/filters", label: "Filters Manager" },
  { to: "/prepare", label: "Prepare" },
  { to: "/render", label: "Render" },
  { to: "/publish", label: "Publish" },
  { to: "/jobs", label: "Jobs" },
];

const productFactoryPaths = new Set([
  "/product-factory",
  "/product-factory/batch-intake",
  "/product-factory/filters",
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
  const isProductFactorySection =
    productFactoryPaths.has(location.pathname) ||
    location.pathname.startsWith("/product-factory/") ||
    location.pathname.startsWith("/pipeline/") ||
    location.pathname.startsWith("/jobs/");
  const isPriceMonitoringSection = location.pathname.startsWith("/price-monitoring");
  const isCatalogSection = location.pathname.startsWith("/catalog");
  const isFindSourceSection = location.pathname.startsWith("/find-source");
  const isVendorSourcesSection = location.pathname.startsWith("/vendor-sources");

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local commerce operations</p>
          <h1>Product Factory Platform</h1>
        </div>
        <div className="topbar-actions">
          <nav className="nav-links" aria-label="Primary navigation">
            {platformNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => {
                  const isProductFactoryActive =
                    item.to === "/product-factory" && isProductFactorySection;
                  const isPriceMonitoringActive =
                    item.to === "/price-monitoring" && isPriceMonitoringSection;
                  const isCatalogActive = item.to === "/catalog" && isCatalogSection;
                  const isFindSourceActive =
                    item.to === "/find-source" && isFindSourceSection;
                  const isVendorSourcesActive =
                    item.to === "/vendor-sources" && isVendorSourcesSection;
                  return isActive ||
                    isProductFactoryActive ||
                    isPriceMonitoringActive ||
                    isCatalogActive ||
                    isFindSourceActive ||
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
          <ThemeToggle />
        </div>
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
      {isProductFactorySection ? (
        <nav className="subnav" aria-label="Product Factory navigation">
          {productFactoryNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/product-factory"}
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
                item.to === "/vendor-sources/source-urls" ||
                item.to === "/vendor-sources/source-health" ||
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
      {isFindSourceSection ? (
        <nav className="subnav find-source-subnav" aria-label="Find Source navigation">
          {findSourceNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/find-source/runs"}
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
