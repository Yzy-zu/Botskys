"""Operación explícita offline; no descubre fuentes ni arranca proveedores."""

import argparse
import json
from pathlib import Path

from botsky.assets_import import import_assets
from botsky.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--gallery", type=Path)
parser.add_argument("--avatar-manifest", type=Path)
parser.add_argument("--avatar-model", type=Path)
args = parser.parse_args()
print(
    json.dumps(
        import_assets(
            Settings.load(args.config),
            gallery=args.gallery,
            avatar_manifest=args.avatar_manifest,
            avatar_model=args.avatar_model,
        )
    )
)
