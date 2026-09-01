#!/usr/bin/env node
// Minimal, dependency-free ZIP writer (Node stdlib only) that preserves
// Unix file-mode bits in each entry's external_attr field. Needed because
// PowerShell's Compress-Archive has no concept of POSIX permissions and
// would silently strip loop.sh's executable bit.
// Usage: node make-zip.js <srcDir> <outPath> <wrapperName> [execRelPath...]
//
// <wrapperName> wraps every entry in a single top-level folder, matching the
// real starter-kit (1).zip's actual internal structure (verified directly
// via `unzip -l`: every entry is under one "starter-kit/" folder, including
// an explicit 0-length directory entry for it — NOT the flat layout this
// script originally produced).
"use strict";
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

let crcTable = null;
function crc32(buf) {
  if (!crcTable) {
    crcTable = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      crcTable[n] = c;
    }
  }
  let crc = -1;
  for (let i = 0; i < buf.length; i++) crc = crcTable[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ -1) >>> 0;
}

function toDosDateTime(d) {
  // DOS date/time bit-packing (the format ZIP local/central headers use).
  // Writing 0 for both fields (as this file previously did) produces an
  // invalid 1980-00-00 timestamp — month/day 0 isn't a real date — visible
  // via `unzip -Z`. Clamp to 1980 (DOS dates can't represent earlier years)
  // and otherwise derive from the file's real mtime.
  let year = d.getFullYear();
  if (year < 1980) year = 1980;
  const dosDate = ((year - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  const dosTime = (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2);
  return { dosDate, dosTime };
}

function listFiles(dir, base) {
  base = base || "";
  let out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    const rel = base ? base + "/" + entry.name : entry.name;
    if (entry.isDirectory()) out = out.concat(listFiles(full, rel));
    else out.push({ full: full, rel: rel });
  }
  return out;
}

function writeZip(srcDir, outPath, wrapperName, execRelPaths) {
  // execRelPaths: relative paths (forward-slash form, relative to srcDir —
  // NOT including wrapperName) that the caller has independently confirmed
  // are executable and wants stamped as such, regardless of what
  // fs.statSync() reports for this file. This exists because on Windows,
  // Node's fs.statSync().mode is synthesized from the FILE_ATTRIBUTE_READONLY
  // flag only — it never reflects the Unix permission bits that Git-Bash/MSYS
  // chmod and ls -la manipulate via NTFS ACLs. Without this override, every
  // file (including a chmod +x'd loop.sh) reports mode 100666 to Node, and
  // the exec bit silently never makes it into the zip. package.sh passes
  // "loop.sh" here after its own chmod +x, since bash can see the real
  // permission state and Node cannot.
  const execSet = new Set((execRelPaths || []).map((p) => p.replace(/\\/g, "/")));
  const execMatched = new Set();
  const files = listFiles(srcDir).sort((a, b) => a.rel.localeCompare(b.rel));
  const localChunks = [];
  const centralChunks = [];
  let offset = 0;
  const now = new Date();
  const { dosDate: dirDosDate, dosTime: dirDosTime } = toDosDateTime(now);

  if (wrapperName) {
    // Explicit directory entry for the wrapper folder itself, matching the
    // real starter-kit zip's own structure (a 0-length entry named
    // "starter-kit/"). method=0 (store), size 0, mode carries S_IFDIR
    // (0o040000) plus rwxr-xr-x, and the low-16-bit DOS directory attribute
    // (0x10) is set alongside the unix mode in the high 16 bits, since not
    // every zip reader honors the unix mode for directory detection.
    const dirNameBuf = Buffer.from(wrapperName.replace(/\\/g, "/") + "/", "utf8");
    const dirMode = 0o040755;

    const dirLocal = Buffer.alloc(30);
    dirLocal.writeUInt32LE(0x04034b50, 0);
    dirLocal.writeUInt16LE(20, 4);
    dirLocal.writeUInt16LE(0, 6);
    dirLocal.writeUInt16LE(0, 8);
    dirLocal.writeUInt16LE(dirDosTime, 10);
    dirLocal.writeUInt16LE(dirDosDate, 12);
    dirLocal.writeUInt32LE(0, 14);
    dirLocal.writeUInt32LE(0, 18);
    dirLocal.writeUInt32LE(0, 22);
    dirLocal.writeUInt16LE(dirNameBuf.length, 26);
    dirLocal.writeUInt16LE(0, 28);
    localChunks.push(dirLocal, dirNameBuf);

    const dirCentral = Buffer.alloc(46);
    dirCentral.writeUInt32LE(0x02014b50, 0);
    dirCentral.writeUInt16LE(0x0314, 4);
    dirCentral.writeUInt16LE(20, 6);
    dirCentral.writeUInt16LE(0, 8);
    dirCentral.writeUInt16LE(0, 10);
    dirCentral.writeUInt16LE(dirDosTime, 12);
    dirCentral.writeUInt16LE(dirDosDate, 14);
    dirCentral.writeUInt32LE(0, 16);
    dirCentral.writeUInt32LE(0, 20);
    dirCentral.writeUInt32LE(0, 24);
    dirCentral.writeUInt16LE(dirNameBuf.length, 28);
    dirCentral.writeUInt16LE(0, 30);
    dirCentral.writeUInt16LE(0, 32);
    dirCentral.writeUInt16LE(0, 34);
    dirCentral.writeUInt16LE(0, 36);
    dirCentral.writeUInt32LE((((dirMode & 0xffff) << 16) | 0x10) >>> 0, 38);
    dirCentral.writeUInt32LE(offset, 42);
    centralChunks.push(dirCentral, dirNameBuf);

    offset += dirLocal.length + dirNameBuf.length;
  }

  for (const f of files) {
    const relNorm0 = f.rel.replace(/\\/g, "/");
    const relNorm = wrapperName ? wrapperName.replace(/\\/g, "/") + "/" + relNorm0 : relNorm0;
    const data = fs.readFileSync(f.full);
    const isExecOverride = execSet.has(relNorm0);
    if (isExecOverride) execMatched.add(relNorm0);
    const stat = fs.statSync(f.full);
    const mode = isExecOverride ? 0o100755 : stat.mode;
    const { dosDate, dosTime } = toDosDateTime(stat.mtime);
    const compressed = zlib.deflateRawSync(data);
    const useStore = compressed.length >= data.length;
    const method = useStore ? 0 : 8;
    const payload = useStore ? data : compressed;
    const crc = crc32(data);
    const nameBuf = Buffer.from(relNorm, "utf8");

    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0, 6);
    localHeader.writeUInt16LE(method, 8);
    localHeader.writeUInt16LE(dosTime, 10);
    localHeader.writeUInt16LE(dosDate, 12);
    localHeader.writeUInt32LE(crc, 14);
    localHeader.writeUInt32LE(payload.length, 18);
    localHeader.writeUInt32LE(data.length, 22);
    localHeader.writeUInt16LE(nameBuf.length, 26);
    localHeader.writeUInt16LE(0, 28);
    localChunks.push(localHeader, nameBuf, payload);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(0x0314, 4); // version made by: host=3 (Unix)
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0, 8);
    centralHeader.writeUInt16LE(method, 10);
    centralHeader.writeUInt16LE(dosTime, 12);
    centralHeader.writeUInt16LE(dosDate, 14);
    centralHeader.writeUInt32LE(crc, 16);
    centralHeader.writeUInt32LE(payload.length, 20);
    centralHeader.writeUInt32LE(data.length, 24);
    centralHeader.writeUInt16LE(nameBuf.length, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(((mode & 0xffff) << 16) >>> 0, 38); // unix mode in upper 16 bits
    centralHeader.writeUInt32LE(offset, 42);
    centralChunks.push(centralHeader, nameBuf);

    offset += localHeader.length + nameBuf.length + payload.length;
  }

  // Guardrail: an execRelPaths entry that never matched a real file would
  // otherwise be a silent no-op — e.g. a typo'd path, or the caller passing
  // a path relative to the wrong directory — quietly shipping loop.sh (or
  // whatever was meant) non-executable with no indication anything went
  // wrong. Fail loudly instead.
  const unmatched = (execRelPaths || [])
    .map((p) => p.replace(/\\/g, "/"))
    .filter((p) => !execMatched.has(p));
  if (unmatched.length > 0) {
    console.error(
      "make-zip.js: execRelPaths entry did not match any file found by listFiles(): " +
        unmatched.join(", ")
    );
    process.exit(1);
  }

  const centralStart = offset;
  const centralSize = centralChunks.reduce((sum, c) => sum + c.length, 0);
  const totalEntries = files.length + (wrapperName ? 1 : 0);

  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(totalEntries, 8);
  end.writeUInt16LE(totalEntries, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(centralStart, 16);
  end.writeUInt16LE(0, 20);

  fs.writeFileSync(outPath, Buffer.concat(localChunks.concat(centralChunks).concat([end])));
}

const srcDir = process.argv[2];
const outPath = process.argv[3];
const wrapperName = process.argv[4] || ""; // "" means no wrapper folder (flat)
const execRelPaths = process.argv.slice(5);
if (!srcDir || !outPath) {
  console.error("usage: make-zip.js <srcDir> <outPath> <wrapperName|''> [execRelPath...]");
  process.exit(1);
}
writeZip(srcDir, outPath, wrapperName, execRelPaths);
console.log("make-zip.js: wrote " + outPath);
