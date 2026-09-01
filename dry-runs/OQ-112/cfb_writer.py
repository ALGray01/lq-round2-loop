"""
Minimal writer for the Microsoft Compound File Binary (CFB) format,
[MS-CFB], sufficient to build valid native .msg (MS-OXMSG) files. No
pip package for writing .msg exists (checked: msg-writer/python-msg/oxmsg/
pymsg are all unavailable or read-only/broken) so this hand-rolls the
container format. Only the subset of [MS-CFB] needed for a small
(<< few hundred KB) single-root-storage file is implemented:
 - v3, 512-byte sectors, 64-byte mini-sectors, 4096-byte mini cutoff
 - single-level FAT (no DIFAT sectors beyond the 109 header slots -
   enough for files up to ~8.5MB, far more than we need)
 - a MiniFAT + mini-stream for small streams
 - directory entries built as a degenerate right-sibling chain per
   storage (a valid, if unbalanced, red-black tree per spec 2.6.4 -
   correctness was verified against `olefile` and `extract-msg`, not
   assumed; see msg_writer.py's self-test).
"""
import struct

SECTOR = 512
MINI_SECTOR = 64
MINI_CUTOFF = 4096
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF

STGTY_STORAGE = 1
STGTY_STREAM = 2
STGTY_ROOT = 5


class Entry:
    def __init__(self, name, kind, data=b""):
        self.name = name
        self.kind = kind  # STGTY_STORAGE / STGTY_STREAM / STGTY_ROOT
        self.data = data
        self.children = []  # list of Entry, only for storages/root
        # filled in during layout:
        self.sid = None
        self.left = NOSTREAM
        self.right = NOSTREAM
        self.child = NOSTREAM
        self.start_sector = ENDOFCHAIN
        self.size = 0


def _pad(b, size, fill=b"\x00"):
    if len(b) % size:
        b = b + fill * (size - (len(b) % size))
    return b


def _chain_children(entries):
    """Build a balanced binary search tree over a list of sibling Entry
    objects (already assigned .sid), return the child pointer (sid of the
    tree root) for the parent. Order sorted per [MS-CFB] 2.6.4 (length then
    case-insensitive UTF-16 codepoint) since some strict readers do
    validate BST ordering.

    An earlier version built a degenerate right-only chain here (a linked
    list dressed as a tree). It round-tripped fine on the ~3-10 sibling
    counts this repo's fixtures actually use, but an adversarial audit
    built a .msg with ~1000 attachments (an ordinary "email with many
    exhibits" scenario) via the public msg_writer.save_msg() API and hit
    RecursionError in olefile/extract-msg, which walk the sibling chain
    recursively - a linear chain means O(N) recursion depth. Fixed by
    building the tree via recursive median split, which keeps depth
    O(log N): a 1000-attachment file now nests ~10 deep instead of ~1000."""
    if not entries:
        return NOSTREAM

    def sort_key(e):
        u = e.name.upper()
        return (len(u), u)

    ordered = sorted(entries, key=sort_key)

    def build(lo, hi):
        if lo >= hi:
            return NOSTREAM
        mid = (lo + hi) // 2
        e = ordered[mid]
        e.left = build(lo, mid)
        e.right = build(mid + 1, hi)
        return e.sid

    return build(0, len(ordered))


def write_cfb(root_children, out_path):
    """root_children: list of Entry (top-level storages/streams under the
    root storage). Writes a complete .msg-shaped CFB file to out_path."""
    root = Entry("Root Entry", STGTY_ROOT)
    root.children = root_children

    # Flatten all entries (root first) and assign SIDs by a pre-order walk.
    all_entries = [root]

    def collect(e):
        for c in e.children:
            all_entries.append(c)
        for c in e.children:
            collect(c)

    collect(root)
    for i, e in enumerate(all_entries):
        e.sid = i

    # Wire up child pointers (degenerate sibling chains) for every storage.
    for e in all_entries:
        if e.kind in (STGTY_STORAGE, STGTY_ROOT):
            e.child = _chain_children(e.children)

    # --- Sector allocation -------------------------------------------------
    fat_chain = []  # list of sector index -> next sector index (or ENDOFCHAIN)
    sectors = []    # list of 512-byte sector payloads, index-aligned with fat_chain

    def alloc_chain(data, sector_size):
        """Split data into sector_size-byte chunks, return list of chunk bytes."""
        if not data:
            return []
        padded = _pad(data, sector_size)
        return [padded[i:i + sector_size] for i in range(0, len(padded), sector_size)]

    def append_sectors(chunks):
        """Append chunks (each already sector_size, but tracked at 512-byte
        granularity by caller) to `sectors`/`fat_chain`, chaining them, and
        return the starting sector index."""
        start = len(sectors)
        for i, chunk in enumerate(chunks):
            sectors.append(chunk)
            fat_chain.append(ENDOFCHAIN)
            if i > 0:
                fat_chain[start + i - 1] = start + i
        return start if chunks else ENDOFCHAIN

    # 1. Mini-stream: concatenate all stream data < MINI_CUTOFF, in SID order,
    #    tracked at 64-byte granularity via a separate MiniFAT.
    mini_fat_chain = []
    mini_data = bytearray()
    for e in all_entries:
        if e.kind != STGTY_STREAM:
            continue
        if len(e.data) == 0:
            e.start_sector = ENDOFCHAIN
            e.size = 0
            continue
        if len(e.data) < MINI_CUTOFF:
            start_mini = len(mini_data) // MINI_SECTOR
            padded = _pad(e.data, MINI_SECTOR)
            n_mini = len(padded) // MINI_SECTOR
            mini_data.extend(padded)
            for i in range(n_mini):
                mini_fat_chain.append(
                    ENDOFCHAIN if i == n_mini - 1 else start_mini + i + 1
                )
            e.start_sector = start_mini
            e.size = len(e.data)
        else:
            chunks = alloc_chain(e.data, SECTOR)
            e.start_sector = append_sectors(chunks)
            e.size = len(e.data)

    # 2. Root Entry's stream data IS the mini-stream, stored as a normal
    #    (512-byte-sector) stream chain.
    root.size = len(mini_data)
    if mini_data:
        chunks = alloc_chain(bytes(mini_data), SECTOR)
        root.start_sector = append_sectors(chunks)
    else:
        root.start_sector = ENDOFCHAIN

    # 3. MiniFAT sectors (128 x 4-byte entries per 512-byte sector).
    minifat_start = ENDOFCHAIN
    n_minifat_sectors = 0
    if mini_fat_chain:
        entries_per_sector = SECTOR // 4
        padded_len = -(-len(mini_fat_chain) // entries_per_sector) * entries_per_sector
        arr = mini_fat_chain + [FREESECT] * (padded_len - len(mini_fat_chain))
        chunks = [
            b"".join(struct.pack("<I", v) for v in arr[i:i + entries_per_sector])
            for i in range(0, len(arr), entries_per_sector)
        ]
        minifat_start = append_sectors(chunks)
        n_minifat_sectors = len(chunks)

    # 4. Directory sectors (4 x 128-byte entries per 512-byte sector).
    dir_entries_bytes = []
    for e in all_entries:
        name_utf16 = e.name.encode("utf-16-le")
        name_utf16 = name_utf16[:62]  # max 31 chars + null
        name_field = _pad(name_utf16 + b"\x00\x00", 64)
        name_len = len(name_utf16) + 2
        color = 1  # black; degenerate chain, color irrelevant to readers we target
        entry = (
            name_field
            + struct.pack("<H", name_len)
            + struct.pack("<B", e.kind)
            + struct.pack("<B", color)
            + struct.pack("<I", e.left)
            + struct.pack("<I", e.right)
            + struct.pack("<I", e.child)
            + b"\x00" * 16  # CLSID
            + struct.pack("<I", 0)  # state bits
            + b"\x00" * 8  # creation time
            + b"\x00" * 8  # modified time
            + struct.pack("<I", e.start_sector)
            + struct.pack("<Q", e.size)
        )
        assert len(entry) == 128, len(entry)
        dir_entries_bytes.append(entry)

    entries_per_dsector = SECTOR // 128
    while len(dir_entries_bytes) % entries_per_dsector:
        dir_entries_bytes.append(b"\x00" * 128)
    dir_chunks = [
        b"".join(dir_entries_bytes[i:i + entries_per_dsector])
        for i in range(0, len(dir_entries_bytes), entries_per_dsector)
    ]
    dir_start = append_sectors(dir_chunks)

    # 5. FAT sectors themselves (allocate LAST, then patch fat_chain values
    #    for the FAT sectors' own slots to FATSECT).
    entries_per_fsector = SECTOR // 4
    n_fat_sectors_guess = 0
    while True:
        total_needed = len(sectors) + n_fat_sectors_guess
        n_fat_sectors = -(-total_needed // entries_per_fsector)
        if n_fat_sectors == n_fat_sectors_guess:
            break
        n_fat_sectors_guess = n_fat_sectors

    fat_start = len(sectors)
    for i in range(n_fat_sectors_guess):
        sectors.append(None)  # placeholder, filled below
        fat_chain.append(FATSECT)

    total_sectors = len(sectors)
    padded_fat_len = n_fat_sectors_guess * entries_per_fsector
    fat_arr = fat_chain + [FREESECT] * (padded_fat_len - len(fat_chain))
    fat_bytes = b"".join(struct.pack("<I", v) for v in fat_arr)
    for i in range(n_fat_sectors_guess):
        sectors[fat_start + i] = fat_bytes[i * SECTOR:(i + 1) * SECTOR]

    # --- Header --------------------------------------------------------
    header = bytearray(512)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, 0x0003)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 9)   # 512-byte sectors
    struct.pack_into("<H", header, 32, 6)   # 64-byte mini sectors
    struct.pack_into("<I", header, 40, 0)   # num dir sectors (0 for v3)
    struct.pack_into("<I", header, 44, n_fat_sectors_guess)
    struct.pack_into("<I", header, 48, dir_start)
    struct.pack_into("<I", header, 52, 0)
    struct.pack_into("<I", header, 56, MINI_CUTOFF)
    struct.pack_into("<I", header, 60, minifat_start)
    struct.pack_into("<I", header, 64, n_minifat_sectors)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)  # no DIFAT sectors needed
    struct.pack_into("<I", header, 72, 0)

    difat = [FREESECT] * 109
    for i in range(min(n_fat_sectors_guess, 109)):
        difat[i] = fat_start + i
    if n_fat_sectors_guess > 109:
        raise NotImplementedError("File too large for header-only DIFAT (>109 FAT sectors)")
    for i, v in enumerate(difat):
        struct.pack_into("<I", header, 76 + i * 4, v)

    with open(out_path, "wb") as f:
        f.write(bytes(header))
        for s in sectors:
            f.write(s if s is not None else b"\x00" * SECTOR)

    return total_sectors
