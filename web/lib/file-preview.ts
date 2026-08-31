/**
 * Client-side row-count preview for each of the five uploads. This is an
 * informational preview only -- the real parse (and the real validation)
 * happens server-side, inside api/reconcile.py, when the file is actually
 * uploaded. A naive line-count for CSV, and a direct JSON.parse for the
 * JSON files, is accurate enough for "here's roughly what you're about to
 * upload" without pulling in a full CSV parser for a preview number.
 */

export type FileKind = "orders" | "payments" | "settlements" | "bank_statement" | "refunds";

export interface FilePreview {
  file: File;
  rowCount: number | null;
  parseError: string | null;
}

async function countJsonRecords(file: File): Promise<number> {
  const text = await file.text();
  const data = JSON.parse(text) as unknown;
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.records)) return obj.records.length;
    if (Array.isArray(obj.data)) return obj.data.length;
  }
  return 1;
}

function countCsvRows(text: string): number {
  const lines = text.split(/\r\n|\n|\r/).filter((line) => line.trim().length > 0);
  return Math.max(0, lines.length - 1); // minus header row
}

async function countXlsxRows(file: File): Promise<number> {
  const XLSX = await import("xlsx");
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array" });
  const sheetName = workbook.SheetNames.includes("orders") ? "orders" : workbook.SheetNames[0];
  const sheet = sheetName ? workbook.Sheets[sheetName] : undefined;
  if (!sheet) return 0;
  const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 }) as unknown[][];
  return Math.max(0, rows.length - 1); // minus header row
}

export async function previewFile(kind: FileKind, file: File): Promise<FilePreview> {
  try {
    let rowCount: number;
    if (kind === "orders") {
      rowCount = await countXlsxRows(file);
    } else if (kind === "bank_statement") {
      rowCount = countCsvRows(await file.text());
    } else {
      rowCount = await countJsonRecords(file);
    }
    return { file, rowCount, parseError: null };
  } catch (err) {
    return {
      file,
      rowCount: null,
      parseError: err instanceof Error ? `could not parse this file: ${err.message}` : "could not parse this file",
    };
  }
}
