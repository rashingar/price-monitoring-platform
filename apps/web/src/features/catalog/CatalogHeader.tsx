export function CatalogHeader({
  commerceApiBaseUrl,
  onReset,
}: {
  commerceApiBaseUrl: string;
  onReset: () => void;
}) {
  return (
    <section className="page-header">
      <p className="eyebrow">Catalog</p>
      <h2>Commerce catalog</h2>
      <p>Commerce API base URL: {commerceApiBaseUrl}</p>
      <button className="text-button" type="button" onClick={onReset}>
        Reset saved Catalog state
      </button>
    </section>
  );
}
