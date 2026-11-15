import sqlite3
import sys
from datetime import datetime
from pathlib import Path

src_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/audit.db")
backup_dir = Path("backups")
backup_dir.mkdir(exist_ok=True)
dest_path = backup_dir / f"{src_path.stem}_{datetime.now():%Y%m%d_%H%M%S}.db"

src = sqlite3.connect(src_path)
dest = sqlite3.connect(dest_path)
with dest:
    src.backup(dest)

# verify the copy
ok = dest.execute("PRAGMA integrity_check").fetchone()[0]
n_src = src.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
n_dest = dest.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
src.close(); dest.close()

print(f"Backup: {dest_path}  ({dest_path.stat().st_size / 1024:.0f} KB)")
print(f"Integrity check: {ok}   runs: {n_src} -> {n_dest}")
assert ok == "ok" and n_src == n_dest, "backup verification failed"