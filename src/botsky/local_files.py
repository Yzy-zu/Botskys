"""Directorios propios y exclusión del worker local; sin servicios adicionales."""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path


def private_directory(project, relative):
    project = Path(project).resolve()
    target = project / relative
    if not target.resolve().is_relative_to(project):
        raise ValueError("directorio fuera del proyecto propio")
    current = project
    for part in Path(relative).parts:
        if part in ("..", ".") or Path(part).is_absolute():
            raise ValueError("directorio no admisible")
        current = current / part
        if current.is_symlink():
            raise ValueError("directorio symlink no admisible")
        current.mkdir(exist_ok=True, mode=0o700)
        current.chmod(0o700)
    return target


class WorkerBusy(RuntimeError):
    pass


@contextmanager
def worker_lock(project):
    directory = private_directory(project, "private")
    fd = os.open(
        directory / "worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkerBusy("Ya hay un worker local ejecutándose.") from None
        yield
    finally:
        os.close(fd)
