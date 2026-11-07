"""Guarda credenciales de laboratorio con entrada oculta; no hace red ni cambia runtime."""

import getpass
import json
import os
import re
import stat
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / "private"
    if not directory.exists():
        directory.mkdir(mode=0o700)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise SystemExit("private/ debe ser un directorio propio con permisos 0700.")
    account = input("Cloudflare Account ID: ").strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account):
        raise SystemExit("Account ID inválido: debe contener 32 caracteres hexadecimales.")
    token = getpass.getpass("Workers AI API token (oculto): ").strip()
    if len(token) < 20 or any(c.isspace() for c in token):
        raise SystemExit("Formato de token no admisible; no se guardó nada.")
    destination = directory / "cloudflare-toolcall.json"
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise SystemExit("El archivo ya existe; se conserva sin sobrescribir.") from None
    with os.fdopen(fd, "w") as stream:
        json.dump({"account_id": account, "api_token": token}, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print("Credenciales guardadas en private/cloudflare-toolcall.json (0600).")
    print("No se ha verificado acceso, consumido cuota ni cambiado producción.")


if __name__ == "__main__":
    main()
