export interface CsvPreview {
  columns: string[];
  rows: Record<string, string>[];
  delimiter: "," | ";" | "\t";
  rowCount: number;
  parseWarning?: string;
}

type CsvDelimiter = "," | ";" | "\t";

const DELIMITERS: CsvDelimiter[] = [",", ";", "\t"];

function countDelimiterOutsideQuotes(line: string, delimiter: CsvDelimiter): number {
  let count = 0;
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const nextChar = line[index + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (!inQuotes && char === delimiter) {
      count += 1;
    }
  }

  return count;
}

function detectDelimiter(content: string): CsvDelimiter {
  const sampleLines = content
    .split(/\r\n|\n|\r/)
    .filter((line) => line.trim().length > 0)
    .slice(0, 10);

  const scores = DELIMITERS.map((delimiter) => ({
    delimiter,
    score: sampleLines.reduce(
      (total, line) => total + countDelimiterOutsideQuotes(line, delimiter),
      0,
    ),
  }));

  scores.sort((first, second) => second.score - first.score);
  return scores[0]?.score ? scores[0].delimiter : ",";
}

function parseRows(content: string, delimiter: CsvDelimiter): {
  rows: string[][];
  warning?: string;
} {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  let warning: string | undefined;

  for (let index = 0; index < content.length; index += 1) {
    const char = content[index];
    const nextChar = content[index + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        field += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (!inQuotes && char === delimiter) {
      row.push(field);
      field = "";
      continue;
    }

    if (!inQuotes && (char === "\n" || char === "\r")) {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";

      if (char === "\r" && nextChar === "\n") {
        index += 1;
      }
      continue;
    }

    field += char;
  }

  if (inQuotes) {
    warning = "CSV preview found an unclosed quoted value. Showing best-effort parsed rows.";
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return { rows, warning };
}

function normalizeColumns(header: string[], width: number): string[] {
  return Array.from({ length: width }, (_, index) => {
    const value = header[index]?.trim();
    return value && value.length > 0 ? value : `Column ${index + 1}`;
  });
}

export function parseCsvPreview(content: string): CsvPreview {
  try {
    const delimiter = detectDelimiter(content);
    const parsed = parseRows(content, delimiter);
    const nonEmptyRows = parsed.rows.filter((row) =>
      row.some((field) => field.length > 0),
    );

    if (nonEmptyRows.length === 0) {
      return {
        columns: [],
        rows: [],
        delimiter,
        rowCount: 0,
        parseWarning: parsed.warning,
      };
    }

    const header = nonEmptyRows[0];
    const dataRows = nonEmptyRows.slice(1);
    const width = Math.max(header.length, ...dataRows.map((row) => row.length), 0);
    const columns = normalizeColumns(header, width);

    return {
      columns,
      rows: dataRows.map((row) =>
        columns.reduce<Record<string, string>>((nextRow, column, index) => {
          nextRow[column] = row[index] ?? "";
          return nextRow;
        }, {}),
      ),
      delimiter,
      rowCount: dataRows.length,
      parseWarning: parsed.warning,
    };
  } catch (error) {
    return {
      columns: [],
      rows: [],
      delimiter: ",",
      rowCount: 0,
      parseWarning: error instanceof Error ? error.message : String(error),
    };
  }
}
