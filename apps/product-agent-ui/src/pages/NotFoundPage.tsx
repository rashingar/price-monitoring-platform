import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="page-stack narrow">
      <section className="page-header">
        <p className="eyebrow">Not found</p>
        <h2>Page not found</h2>
        <p>The requested operator page does not exist.</p>
      </section>
      <Link className="button primary inline-button" to="/">
        Go to dashboard
      </Link>
    </div>
  );
}
