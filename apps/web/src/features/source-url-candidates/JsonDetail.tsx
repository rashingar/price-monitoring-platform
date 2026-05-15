import { renderJsonValue } from "./sourceUrlCandidateHelpers";

interface JsonDetailProps {
  value: unknown;
}

export function JsonDetail({ value }: JsonDetailProps) {
  const rendered = renderJsonValue(value);
  if (rendered === "-") {
    return <span className="muted">-</span>;
  }

  if (typeof value === "object" && value !== null) {
    return <pre className="json-block compact-json-block">{rendered}</pre>;
  }

  return <span>{rendered}</span>;
}
