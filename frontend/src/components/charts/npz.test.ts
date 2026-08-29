/** Todo 42: читатель NPZ — STORED-контейнер собирается в тесте байт за
 * байтом (детерминированно, без файловых фикстур); битые контейнеры дают
 * типизированную TileError("corrupt_payload"). */

import { describe, expect, it } from "vitest";
import { parseNpy, readNpzArrays } from "./npz";
import { TileError } from "./tileError";

function bytes(...parts: ReadonlyArray<number | Uint8Array | ArrayBuffer>): ArrayBuffer {
  const flat = new Uint8Array(
    parts.reduce<number>((total, part) => total + partByteLength(part), 0),
  );
  let offset = 0;
  for (const part of parts) {
    const view = partView(part);
    flat.set(view, offset);
    offset += view.length;
  }
  return flat.buffer;
}

function partByteLength(part: number | Uint8Array | ArrayBuffer): number {
  if (part instanceof Uint8Array || part instanceof ArrayBuffer) return part.byteLength;
  return 1;
}

function partView(part: number | Uint8Array | ArrayBuffer): Uint8Array {
  if (typeof part === "number") return new Uint8Array([part]);
  if (part instanceof Uint8Array) return part;
  return new Uint8Array(part);
}

function u16le(value: number): Uint8Array {
  const out = new Uint8Array(2);
  new DataView(out.buffer).setUint16(0, value, true);
  return out;
}

function u32le(value: number): Uint8Array {
  const out = new Uint8Array(4);
  new DataView(out.buffer).setUint32(0, value, true);
  return out;
}

function ascii(text: string): Uint8Array {
  const out = new Uint8Array(text.length);
  for (let index = 0; index < text.length; index += 1) {
    out[index] = text.charCodeAt(index);
  }
  return out;
}

function npyF8(values: readonly number[]): ArrayBuffer {
  const header = `{'descr': '<f8', 'fortran_order': False, 'shape': (${values.length},), }`;
  const paddedLength = Math.ceil((10 + header.length + 1) / 64) * 64 - 10;
  const headerText = `${header + " ".repeat(paddedLength - header.length - 1)}\n`;
  const payload = new Float64Array(values);
  return bytes(
    ascii("\x93NUMPY\x01\x00"),
    u16le(headerText.length),
    ascii(headerText),
    payload.buffer as ArrayBuffer,
  );
}

function storedZip(entries: ReadonlyArray<{ name: string; content: ArrayBuffer }>): ArrayBuffer {
  const locals: ArrayBuffer[] = [];
  const centrals: ArrayBuffer[] = [];
  let offset = 0;
  for (const entry of entries) {
    const size = entry.content.byteLength;
    locals.push(
      bytes(
        u32le(0x04034b50),
        u16le(20),
        u16le(0),
        u16le(0), // method STORED
        u16le(0),
        u16le(0),
        u32le(0),
        u32le(size),
        u32le(size),
        u16le(entry.name.length),
        u16le(0),
        ascii(entry.name),
        entry.content,
      ),
    );
    centrals.push(
      bytes(
        u32le(0x02014b50),
        u16le(20),
        u16le(20),
        u16le(0),
        u16le(0), // method STORED
        u16le(0),
        u16le(0),
        u32le(0),
        u32le(size),
        u32le(size),
        u16le(entry.name.length),
        u16le(0),
        u16le(0),
        u16le(0),
        u16le(0),
        u32le(0),
        u32le(offset),
        ascii(entry.name),
      ),
    );
    offset += partByteLength(locals[locals.length - 1] as ArrayBuffer);
  }
  const directoryOffset = locals.reduce((total, local) => total + local.byteLength, 0);
  const directory = centrals.reduce((total, central) => bytes(total, central), new ArrayBuffer(0));
  return bytes(
    ...locals,
    directory,
    u32le(0x06054b50),
    u16le(0),
    u16le(0),
    u16le(entries.length),
    u16le(entries.length),
    u32le(directory.byteLength),
    u32le(directoryOffset),
    u16le(0),
  );
}

describe("readNpzArrays", () => {
  it("читает STORED-записи time_s/frequency_hz/power_db как типизированные массивы", async () => {
    const zip = storedZip([
      { name: "time_s.npy", content: npyF8([0, 0.5, 1]) },
      { name: "frequency_hz.npy", content: npyF8([10, 20]) },
      {
        name: "power_db.npy",
        content: (() => {
          const values = new Float32Array([1, 2, 3, 4, 5, 6]);
          const header = "{'descr': '<f4', 'fortran_order': False, 'shape': (2, 3), }";
          const padded = `${header + " ".repeat(64 - ((10 + header.length + 1) % 64) - 1)}\n`;
          return bytes(
            ascii("\x93NUMPY\x01\x00"),
            u16le(padded.length),
            ascii(padded),
            values.buffer as ArrayBuffer,
          );
        })(),
      },
    ]);
    const arrays = await readNpzArrays(zip, ["time_s", "frequency_hz", "power_db"]);
    expect(Array.from(new Float64Array(arrays.get("time_s")?.data ?? new ArrayBuffer(0)))).toEqual([
      0, 0.5, 1,
    ]);
    const power = arrays.get("power_db");
    expect(power?.descr).toBe("<f4");
    expect(power?.shape).toEqual([2, 3]);
    expect(Array.from(new Float32Array(power?.data ?? new ArrayBuffer(0)))).toEqual([
      1, 2, 3, 4, 5, 6,
    ]);
  });

  it("обрезанный или не-NPZ буфер даёт corrupt_payload", async () => {
    await expect(readNpzArrays(new ArrayBuffer(10), ["time_s"])).rejects.toMatchObject({
      name: "TileError",
      code: "corrupt_payload",
    });
    await expect(readNpzArrays(storedZip([]), ["time_s"])).rejects.toBeInstanceOf(TileError);
  });

  it("битая NPY-запись внутри контейнера даёт corrupt_payload", async () => {
    const badNpy = bytes(ascii("NOTNUMPY!"), u16le(10), ascii("          "));
    const zip = storedZip([{ name: "time_s.npy", content: badNpy }]);
    await expect(readNpzArrays(zip, ["time_s"])).rejects.toMatchObject({ code: "corrupt_payload" });
  });

  it("отклоняет power_db с descr не <f4", async () => {
    const zip = storedZip([
      { name: "time_s.npy", content: npyF8([0, 1]) },
      { name: "frequency_hz.npy", content: npyF8([10]) },
      { name: "power_db.npy", content: npyF8([1, 2]) },
    ]);
    await expect(readNpzArrays(zip, ["time_s", "frequency_hz", "power_db"])).rejects.toMatchObject({
      name: "TileError",
      code: "corrupt_payload",
    });
  });

  it("parseNpy отклоняет fortran_order и кривую форму", () => {
    const header = "{'descr': '<f8', 'fortran_order': True, 'shape': (2,), }";
    const padded = `${header + " ".repeat(63 - header.length)}\n`;
    const buffer = bytes(
      ascii("\x93NUMPY\x01\x00"),
      u16le(padded.length),
      ascii(padded),
      new Float64Array([1, 2]).buffer as ArrayBuffer,
    );
    expect(() => parseNpy(buffer)).toThrowError(TileError);
  });
});
