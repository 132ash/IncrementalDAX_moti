"""Seal one complete guest root overlay upper as an immutable DAX layer."""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def archive_upper(image: Path, archive: Path) -> None:
    """Archive an overlay upper, preserving whiteouts, ownership and xattrs."""
    mountpoint = Path(tempfile.mkdtemp(prefix="mixfs-exp5-upper-"))
    mounted = False
    try:
        subprocess.run(["sudo", "-n", "mount", "-o", "loop,ro,noload", str(image), str(mountpoint)], check=True)
        mounted = True
        root = mountpoint / "root"
        if not root.is_dir():
            raise RuntimeError(f"overlay upper has no root directory: {image}")
        subprocess.run([
            "sudo", "-n", "tar", "--xattrs", "--xattrs-include=*", "--acls",
            "--numeric-owner", "-C", str(root), "-cf", str(archive), ".",
        ], check=True)
        subprocess.run(["sudo", "-n", "chown", f"{os.getuid()}:{os.getgid()}", str(archive)], check=True)
    finally:
        if mounted:
            subprocess.run(["sudo", "-n", "umount", str(mountpoint)], check=True)
        mountpoint.rmdir()


def build_layer(archive: Path, image: Path) -> None:
    """Materialize one root upper without copying the shared base or older layers."""
    with tarfile.open(archive) as tar:
        payload = sum(member.size for member in tar.getmembers())
    size = max(256 << 20, int(payload * 1.5) + (128 << 20))
    size = (size + (2 << 20) - 1) // (2 << 20) * (2 << 20)
    image.parent.mkdir(parents=True, exist_ok=True)
    if image.exists():
        raise FileExistsError(image)
    with image.open("wb") as handle:
        handle.truncate(size)
    mountpoint = Path(tempfile.mkdtemp(prefix="mixfs-exp5-dax-"))
    mounted = False
    try:
        subprocess.run(["mkfs.ext4", "-F", "-q", str(image)], check=True)
        subprocess.run(["sudo", "-n", "mount", "-o", "loop", str(image), str(mountpoint)], check=True)
        mounted = True
        subprocess.run(["sudo", "-n", "mkdir", str(mountpoint / "delta")], check=True)
        subprocess.run(["sudo", "-n", "tar", "--xattrs", "--xattrs-include=*", "--acls",
                        "--numeric-owner", "-C", str(mountpoint / "delta"), "-xf", str(archive)], check=True)
    except BaseException:
        image.unlink(missing_ok=True)
        raise
    finally:
        if mounted:
            subprocess.run(["sudo", "-n", "umount", str(mountpoint)], check=True)
        mountpoint.rmdir()
    image.chmod(0o444)
    os.sync()
    with image.open("rb") as handle:
        os.posix_fadvise(handle.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)


def link_layers(instance: Path, template_image: Path) -> list[str]:
    """Preserve inode identity for every inherited and newly attached DAX layer."""
    names = []
    for source in sorted(instance.glob("checkpoint-*.ext4")):
        target = template_image / source.name
        os.link(source, target)
        names.append(source.name)
    return names
