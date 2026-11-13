/**
 * Reads back an `.xlsx` the page wrote, for the tests: its sheet names and
 * the first sheet's cells, by row. Node's zlib and a few lines of zip and
 * XML reading, so the tests need no spreadsheet library: an `.xlsx` is a zip
 * of XML files, its text in `xl/sharedStrings.xml`.
 */

import { readFile } from "node:fs/promises";
import { inflateRawSync } from "node:zlib";

/** Each file in a zip, by name, from its central directory. */
function unzip(zip: Buffer): Map<string, Buffer> {
  const end = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (end < 0) throw new Error("not a zip: no end of central directory");
  const files = new Map<string, Buffer>();
  let at = zip.readUInt32LE(end + 16);
  for (let i = 0; i < zip.readUInt16LE(end + 10); i++) {
    const method = zip.readUInt16LE(at + 10);
    const size = zip.readUInt32LE(at + 20);
    const nameLength = zip.readUInt16LE(at + 28);
    const skip = nameLength + zip.readUInt16LE(at + 30) + zip.readUInt16LE(at + 32);
    const name = zip.toString("utf-8", at + 46, at + 46 + nameLength);
    const local = zip.readUInt32LE(at + 42);
    const start = local + 30 + zip.readUInt16LE(local + 26) + zip.readUInt16LE(local + 28);
    const data = zip.subarray(start, start + size);
    files.set(name, method === 8 ? inflateRawSync(data) : data);
    at += 46 + skip;
  }
  return files;
}

const unescape = (text: string) =>
  text.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");

/** "C" is column 2. */
const columnIndex = (letters: string) => [...letters].reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0) - 1;

/** A cell's value: a shared string, inline text or a number; an absent cell is "". */
function cellValue(attributes: string, body: string, strings: string[]): string | number {
  const value = /<v>([^<]*)<\/v>/.exec(body)?.[1];
  const type = /\bt="([^"]+)"/.exec(attributes)?.[1];
  if (type === "s") return strings[Number(value)];
  if (type === "inlineStr" || type === "str") return unescape(/<t[^>]*>([^<]*)<\/t>/.exec(body)?.[1] ?? value ?? "");
  return value === undefined ? "" : Number(value);
}

export interface Workbook {
  sheets: string[];
  /** The first sheet, by row, each as wide as the widest; a missing cell is "". */
  rows: (string | number)[][];
}

export async function readXlsx(path: string): Promise<Workbook> {
  const files = unzip(await readFile(path));
  const text = (name: string) => files.get(name)?.toString("utf-8") ?? "";
  const strings = [...text("xl/sharedStrings.xml").matchAll(/<si>([\s\S]*?)<\/si>/g)].map((si) =>
    [...si[1].matchAll(/<t[^>]*>([^<]*)<\/t>/g)].map((t) => unescape(t[1])).join("")
  );
  const sheets = [...text("xl/workbook.xml").matchAll(/<sheet\b[^>]*\bname="([^"]*)"/g)].map((m) => unescape(m[1]));
  const rows = [...text("xl/worksheets/sheet1.xml").matchAll(/<row\b[^>]*>([\s\S]*?)<\/row>/g)].map((row) => {
    const cells: (string | number)[] = [];
    for (const cell of row[1].matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
      const index = columnIndex(/\br="([A-Z]+)\d+"/.exec(cell[1])?.[1] ?? "A");
      while (cells.length < index) cells.push("");
      cells[index] = cellValue(cell[1], cell[2] ?? "", strings);
    }
    return cells;
  });
  const width = Math.max(0, ...rows.map((row) => row.length));
  return { sheets, rows: rows.map((row) => [...row, ...Array<string>(width - row.length).fill("")]) };
}
