/** Тестовая сборка NPZ-спектрограммы (todo 42, только e2e/bench): STORED-ZIP
 * контейнер + NPY v1 массивы — байтовый аналог np.savez_compressed без
 * внешних зависимостей. Форма power_db — (полосы, время), как в движке. */

export interface SpectrogramNpzInput {
  timeS: readonly number[];
  frequencyHz: readonly number[];
  /** Плоский массив длиной bands*timeBins (f * timeBins + t). */
  powerDb: Float32Array;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return ~crc >>> 0;
}

class ByteWriter {
  private chunks: Uint8Array[] = [];
  length = 0;

  push(view: Uint8Array): void {
    this.chunks.push(view);
    this.length += view.length;
  }

  u16(value: number): void {
    const out = new DataView(new ArrayBuffer(2));
    out.setUint16(0, value, true);
    this.push(new Uint8Array(out.buffer));
  }

  u32(value: number): void {
    const out = new DataView(new ArrayBuffer(4));
    out.setUint32(0, value, true);
    this.push(new Uint8Array(out.buffer));
  }

  ascii(text: string): void {
    const out = new Uint8Array(text.length);
    for (let index = 0; index < text.length; index += 1) {
      out[index] = text.charCodeAt(index);
    }
    this.push(out);
  }

  build(): ArrayBuffer {
    const flat = new Uint8Array(this.length);
    let offset = 0;
    for (const chunk of this.chunks) {
      flat.set(chunk, offset);
      offset += chunk.length;
    }
    return flat.buffer;
  }
}

function npyF64(values: readonly number[]): Uint8Array {
  return npy(
    values,
    "<f8",
    (writer, value) => writer.data.setFloat64(writer.offset, value, true),
    8,
  );
}

function npyF32(values: Float32Array, shape?: readonly number[]): Uint8Array {
  return npy(
    values,
    "<f4",
    (writer, value) => writer.data.setFloat32(writer.offset, value, true),
    4,
    shape,
  );
}

interface NpyWriter {
  data: DataView;
  offset: number;
}

function npy(
  values: readonly number[] | Float32Array,
  descr: string,
  writeAt: (writer: NpyWriter, value: number) => void,
  itemSize: number,
  shape?: readonly number[],
): Uint8Array {
  const shapeTuple = shape === undefined ? `(${values.length},)` : `(${shape.join(",")})`;
  const headerBase = `{'descr': '${descr}', 'fortran_order': False, 'shape': ${shapeTuple}, }`;
  const paddedLength = Math.ceil((10 + headerBase.length + 1) / 64) * 64 - 10;
  const headerText = `${headerBase + " ".repeat(paddedLength - headerBase.length - 1)}\n`;
  const total = 10 + headerText.length + values.length * itemSize;
  const buffer = new ArrayBuffer(total);
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);
  bytes.set([0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59, 0x01, 0x00], 0);
  view.setUint16(8, headerText.length, true);
  for (let index = 0; index < headerText.length; index += 1) {
    bytes[10 + index] = headerText.charCodeAt(index);
  }
  const writer: NpyWriter = { data: view, offset: 10 + headerText.length };
  for (const value of values) {
    writeAt(writer, value);
    writer.offset += itemSize;
  }
  return bytes;
}

/** Собирает spectrogram.npz (STORED-записи, детерминированный порядок). */
export function buildSpectrogramNpz(input: SpectrogramNpzInput): ArrayBuffer {
  const entries: Array<{ name: string; body: Uint8Array }> = [
    { name: "time_s.npy", body: npyF64(input.timeS) },
    { name: "frequency_hz.npy", body: npyF64(input.frequencyHz) },
    {
      name: "power_db.npy",
      body: npyF32(input.powerDb, [input.frequencyHz.length, input.timeS.length]),
    },
  ];
  const writer = new ByteWriter();
  const offsets: number[] = [];
  for (const entry of entries) {
    offsets.push(writer.length);
    writer.u32(0x04034b50);
    writer.u16(20);
    writer.u16(0);
    writer.u16(0); // method 0 = stored
    writer.u16(0);
    writer.u16(0);
    writer.u32(crc32(entry.body));
    writer.u32(entry.body.length);
    writer.u32(entry.body.length);
    writer.u16(entry.name.length);
    writer.u16(0);
    writer.ascii(entry.name);
    writer.push(entry.body);
  }
  const directoryOffset = writer.length;
  for (const [index, entry] of entries.entries()) {
    writer.u32(0x02014b50);
    writer.u16(20);
    writer.u16(20);
    writer.u16(0);
    writer.u16(0);
    writer.u16(0);
    writer.u16(0);
    writer.u32(crc32(entry.body));
    writer.u32(entry.body.length);
    writer.u32(entry.body.length);
    writer.u16(entry.name.length);
    writer.u16(0);
    writer.u16(0);
    writer.u16(0);
    writer.u16(0);
    writer.u32(0);
    writer.u32(offsets[index] as number);
    writer.ascii(entry.name);
  }
  const directoryEnd = writer.length;
  writer.u32(0x06054b50);
  writer.u16(0);
  writer.u16(0);
  writer.u16(entries.length);
  writer.u16(entries.length);
  writer.u32(directoryEnd - directoryOffset);
  writer.u32(directoryOffset);
  writer.u16(0);
  return writer.build();
}
