export interface ParsedOpenCartCategory {
  raw: string;
  family: string;
  category: string;
  subCategory: string;
  levels: string[];
}

export function parseOpenCartCategory(
  serializedCategory: string | null | undefined,
): ParsedOpenCartCategory {
  const raw = typeof serializedCategory === "string" ? serializedCategory : "";
  const normalizedRaw = raw.trim();
  if (normalizedRaw.length === 0) {
    return {
      raw,
      family: "",
      category: "",
      subCategory: "",
      levels: [],
    };
  }

  if (!normalizedRaw.includes(":::") && !normalizedRaw.includes("///")) {
    return {
      raw,
      family: normalizedRaw,
      category: "",
      subCategory: "",
      levels: [normalizedRaw],
    };
  }

  const nodes = normalizedRaw
    .split(":::")
    .map((node) =>
      node
        .split("///")
        .map((level) => level.trim())
        .filter((level) => level.length > 0),
    )
    .filter((levels) => levels.length > 0);
  const levels = nodes.reduce<string[]>(
    (deepest, current) => (current.length > deepest.length ? current : deepest),
    [],
  );

  return {
    raw,
    family: levels[0] ?? "",
    category: levels[1] ?? "",
    subCategory: levels[2] ?? "",
    levels,
  };
}
