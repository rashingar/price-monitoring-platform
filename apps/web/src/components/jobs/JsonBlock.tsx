interface JsonBlockProps {
  value: unknown;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "No payload";
  }

  if (typeof value === "string") {
    return value.length > 0 ? value : "No payload";
  }

  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}

export function JsonBlock({ value }: JsonBlockProps) {
  return <pre className="json-block">{formatValue(value)}</pre>;
}
