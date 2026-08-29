/** Минимальный читатель NPZ (todo 42): ZIP-контейнер + NPY-заголовки.
 * Продуктовая форма артефакта бэкенда — np.savez_compressed с массивами
 * time_s (f8), frequency_hz (f8), power_db (f4). Битый/обрезанный контейнер
 * даёт типизированную TileError("corrupt_payload"), а не исключение ZIP. */

import { TileError } from "./tileError";

export interface NpzArray {
  data: ArrayBuffer;
  descr: string;
  shape: readonly number[];
}

const LOCAL_HEADER_SIG = 0x04034b50;
const CENTRAL_HEADER_SIG = 0x02014b50;
const EOCD_SIG = 0x06054b50;

function u16(view: DataView, offset: number): number {
  return view.getUint16(offset, true);
}

function u32(view: DataView, offset: number): number {
  return view.getUint32(offset, true);
}

interface ZipEntry {
  name: string;
  method: number;
  compressedSize: number;
  dataOffset: number;
}

function readCentralDirectory(view: DataView): ZipEntry[] {
  const sig = (offset: number): number => u32(view, offset);
  let eocd = -1;
  for (
    let offset = view.byteLength - 22;
    offset >= Math.max(0, view.byteLength - 65_559);
    offset -= 1
  ) {
    if (view.byteLength - offset >= 22 && sig(offset) === EOCD_SIG) {
      eocd = offset;
      break;
    }
  }
  if (eocd < 0) throw new TileError("corrupt_payload");
  const count = u16(view, eocd + 10);
  const directoryOffset = u32(view, eocd + 16);
  const entries: ZipEntry[] = [];
  let cursor = directoryOffset;
  for (let index = 0; index < count; index += 1) {
    if (sig(cursor) !== CENTRAL_HEADER_SIG) throw new TileError("corrupt_payload");
    const nameLength = u16(view, cursor + 28);
    const extraLength = u16(view, cursor + 30);
    const commentLength = u16(view, cursor + 32);
    const localOffset = u32(view, cursor + 42);
    if (u32(view, localOffset) !== LOCAL_HEADER_SIG) throw new TileError("corrupt_payload");
    const localNameLength = u16(view, localOffset + 26);
    const localExtraLength = u16(view, localOffset + 28);
    entries.push({
      name: decodeName(view, cursor + 46, nameLength),
      method: u16(view, cursor + 10),
      compressedSize: u32(view, cursor + 20),
      dataOffset: localOffset + 30 + localNameLength + localExtraLength,
    });
    cursor += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

function decodeName(view: DataView, offset: number, length: number): string {
  let text = "";
  for (let index = 0; index < length; index += 1)
    text += String.fromCharCode(u8(view, offset + index));
  return text;
}

function u8(view: DataView, offset: number): number {
  return view.getUint8(offset);
}

async function inflateRaw(bytes: Uint8Array): Promise<ArrayBuffer> {
  if (typeof DecompressionStream !== "function") {
    throw new TileError("unsupported_compression");
  }
  const stream = new DecompressionStream("deflate-raw");
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  const response = new Response(new Blob([copy]).stream().pipeThrough(stream));
  return response.arrayBuffer();
}

/** Читает выбранные имена из NPZ; отсутствующее имя — corrupt_payload. */
export async function readNpzArrays(
  buffer: ArrayBuffer,
  names: readonly string[],
): Promise<Map<string, NpzArray>> {
  if (buffer.byteLength < 22) throw new TileError("corrupt_payload");
  const view = new DataView(buffer);
  const entries = readCentralDirectory(view);
  const wanted = new Map(entries.map((entry) => [entry.name, entry]));
  const result = new Map<string, NpzArray>();
  for (const name of names) {
    const entry = wanted.get(`${name}.npy`);
    if (entry === undefined) throw new TileError("corrupt_payload", { detail: `(${name})` });
    const raw = new Uint8Array(buffer, entry.dataOffset, entry.compressedSize);
    const payload =
      entry.method === 0
        ? raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength)
        : entry.method === 8
          ? await inflateRaw(raw)
          : (() => {
              throw new TileError("corrupt_payload", { detail: `(метод ${entry.method})` });
            })();
    const parsed = parseNpy(payload);
    if (name === "power_db" && parsed.descr !== "<f4") {
      throw new TileError("corrupt_payload", { detail: "(power_db descr)" });
    }
    result.set(name, parsed);
  }
  return result;
}

const NUMPY_MAGIC = [0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59]; // \x93NUMPY

/** Разбирает NPY v1/v2: заголовок-словарь + сырые данные без копий значений. */
export function parseNpy(buffer: ArrayBuffer): NpzArray {
  const view = new DataView(buffer);
  const magicMatches =
    buffer.byteLength >= 10 && NUMPY_MAGIC.every((byte, index) => u8(view, index) === byte);
  if (!magicMatches) {
    throw new TileError("corrupt_payload", { detail: "(нет магии NUMPY)" });
  }
  const major = u8(view, 6);
  const headerLength = major === 1 ? u16(view, 8) : u32(view, 8);
  const headerStart = major === 1 ? 10 : 12;
  const headerText = decodeLatin(buffer, headerStart, headerLength);
  const descr = /'descr'\s*:\s*'([^']+)'/.exec(headerText)?.[1];
  const fortran = /'fortran_order'\s*:\s*(True|False)/.exec(headerText)?.[1] === "True";
  const shapeMatch = /'shape'\s*:\s*\(([^)]*)\)/.exec(headerText)?.[1] ?? "";
  if (descr === undefined || fortran) {
    throw new TileError("corrupt_payload", { detail: "(описание массива)" });
  }
  const shape = shapeMatch
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((part) => Number.parseInt(part, 10));
  if (shape.some((dimension) => !Number.isFinite(dimension) || dimension < 0)) {
    throw new TileError("corrupt_payload", { detail: "(форма)" });
  }
  return { data: buffer.slice(headerStart + headerLength), descr, shape };
}

function decodeLatin(buffer: ArrayBuffer, start: number, length: number): string {
  let text = "";
  const bytes = new Uint8Array(buffer, start, length);
  for (const byte of bytes) text += String.fromCharCode(byte);
  return text;
}
