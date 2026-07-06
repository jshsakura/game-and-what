// Minimal client-side ZIP writer, STORED entries only (no compression) — used to
// bundle batch downloads into ONE file so the browser's multi-download blocking
// never eats files. Raw payloads like .565 frames are near-incompressible anyway.

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function dosDateTime(d) {
  const time = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
  const date = (((d.getFullYear() - 1980) & 0x7f) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  return { time, date };
}

const UTF8_NAMES_FLAG = 0x0800;

// entries: [{ name, data: Uint8Array }] → application/zip Blob (STORED).
export function buildZip(entries) {
  const enc = new TextEncoder();
  const { time, date } = dosDateTime(new Date());
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const { name, data } of entries) {
    const nameBytes = enc.encode(name);
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);   // local file header signature
    local.setUint16(4, 20, true);           // version needed to extract
    local.setUint16(6, UTF8_NAMES_FLAG, true);
    local.setUint16(8, 0, true);            // method: stored
    local.setUint16(10, time, true);
    local.setUint16(12, date, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true); // compressed size (= raw, stored)
    local.setUint32(22, data.length, true); // uncompressed size
    local.setUint16(26, nameBytes.length, true);
    local.setUint16(28, 0, true);           // extra length
    localParts.push(new Uint8Array(local.buffer), nameBytes, data);

    const central = new DataView(new ArrayBuffer(46));
    central.setUint32(0, 0x02014b50, true); // central directory signature
    central.setUint16(4, 20, true);         // version made by
    central.setUint16(6, 20, true);         // version needed
    central.setUint16(8, UTF8_NAMES_FLAG, true);
    central.setUint16(10, 0, true);         // method: stored
    central.setUint16(12, time, true);
    central.setUint16(14, date, true);
    central.setUint32(16, crc, true);
    central.setUint32(20, data.length, true);
    central.setUint32(24, data.length, true);
    central.setUint16(28, nameBytes.length, true);
    central.setUint32(42, offset, true);    // local header offset
    centralParts.push(new Uint8Array(central.buffer), nameBytes);

    offset += 30 + nameBytes.length + data.length;
  }

  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const eocd = new DataView(new ArrayBuffer(22));
  eocd.setUint32(0, 0x06054b50, true);      // end of central directory signature
  eocd.setUint16(8, entries.length, true);  // entries on this disk
  eocd.setUint16(10, entries.length, true); // entries total
  eocd.setUint32(12, centralSize, true);
  eocd.setUint32(16, offset, true);         // central directory offset
  return new Blob([...localParts, ...centralParts, new Uint8Array(eocd.buffer)], { type: "application/zip" });
}
