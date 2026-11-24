#!/usr/bin/env python3
"""Write a reproducible zip of the tree plus RELEASE-MANIFEST.sha256 into dist/.

File order, timestamps and modes are fixed, so the same tree gives the same archive.
"""
import hashlib
import json
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import deltaos_harness as H  # noqa: E402

SKIP_DIRS = {".git", "__pycache__", "dist", ".pytest_cache"}
SKIP_FILES = {".DS_Store"}


def main() -> int:
    name = f"deltaos-gym-{H.VERSION}"
    files = sorted(p for p in ROOT.rglob("*")
                   if p.is_file() and not (set(p.relative_to(ROOT).parts[:-1]) & SKIP_DIRS)
                   and p.name not in SKIP_FILES and p.suffix != ".pyc")
    manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n"
                       for p in files)
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entries = [(p.relative_to(ROOT).as_posix(), p.read_bytes(),
                    0o755 if p.suffix == ".sh" else 0o644) for p in files]
        entries.append(("RELEASE-MANIFEST.sha256", manifest.encode(), 0o644))
        for rel, data, mode in sorted(entries):
            info = zipfile.ZipInfo(f"{name}/{rel}", date_time=(2026, 11, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    print(json.dumps({"zip": str(out), "files": len(files) + 1, "bytes": out.stat().st_size,
                      "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
