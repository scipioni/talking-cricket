"""Startup safety check: refuse to run against a database on a network filesystem.
SQLite's locking is unreliable over NFS/CIFS and the failure mode is silent
corruption, not a clean error - so this is checked once, loudly, at boot rather
than discovered later as data loss (design.md - Persistence, Risks/Trade-offs)."""

from __future__ import annotations

from pathlib import Path


class NetworkFilesystemError(RuntimeError):
    pass


def ensure_database_not_on_network_fs(database_path: str) -> None:
    """Best-effort check via /proc/self/mountinfo on Linux. No-op (does not raise)
    on platforms or filesystems where this cannot be determined, since a false
    positive would be worse than an unchecked deployment - this is a guardrail
    against the common Swarm misconfiguration (an NFS-backed volume), not a
    general-purpose filesystem detector."""
    directory = Path(database_path).resolve().parent
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return

    network_fs_types = {"nfs", "nfs4", "cifs", "smb", "smbfs", "9p"}
    best_match: tuple[int, str] | None = None  # (mount point length, fs type)

    try:
        for line in mountinfo.read_text().splitlines():
            parts = line.split(" - ")
            if len(parts) != 2:
                continue
            pre, post = parts
            mount_point = pre.split()[4]
            fs_type = post.split()[0]
            if str(directory).startswith(mount_point) and (
                best_match is None or len(mount_point) > best_match[0]
            ):
                best_match = (len(mount_point), fs_type)
    except OSError:
        return

    if best_match is not None and best_match[1] in network_fs_types:
        raise NetworkFilesystemError(
            f"Refusing to start: the database directory {directory} is on a "
            f"'{best_match[1]}' network filesystem. SQLite requires a local "
            "filesystem for reliable locking (design.md - Persistence). Use a "
            "local Docker volume instead."
        )
