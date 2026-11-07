"""URL, búsqueda, elección por vista entregada y anterior retenido: fuentes excluyentes."""

import json

from ..artifacts import ArtifactProblem
from ..contracts import Result
from ..engines.process import MediaError
from .notes import SCOPE_SQL


def validate_url(url, adult=False):
    from ..engines.downloads import (
        download_source,
        is_spotify_url,
        validate_download_url,
        validate_spotify_url,
    )

    if is_spotify_url(url):
        return validate_spotify_url(url)
    normalized = validate_download_url(url)
    if download_source(normalized) in ("pornhub", "xnxx") and not adult:
        raise MediaError("adult_sources_disabled")
    return normalized


def execute(db, context, spec, args, now, jobs, artifacts, backend):
    action = spec.original_action
    if action == "previous":
        prior = db.execute(
            f"SELECT * FROM interactions WHERE {SCOPE_SQL} AND kind='download_previous' AND state='active' AND expires_ms>? ORDER BY rowid DESC LIMIT 1",
            (*context.scope_key, now),
        ).fetchone()
        if not prior:
            return Result(
                "needs_input",
                "previous_download_missing",
                "No hay una descarga propia entregada y retenida en este chat. Adjunta el archivo de nuevo.",
            )
        data = json.loads(prior["data_json"])
        try:
            artifacts.owned(db, data["artifact_id"], context, now)
            return jobs.reserve(db, context, "edit_media.run", args, [data["artifact_id"]], now)
        except ArtifactProblem as exc:
            return Result(
                "failed",
                exc.code,
                "El archivo anterior ya no está disponible; no redescargué el enlace.",
            )
    if backend is None or getattr(backend, "enabled", True) is not True:
        return Result(
            "failed",
            "downloads_not_configured",
            "Las fuentes remotas no están habilitadas en este laboratorio.",
        )
    adult = getattr(backend, "adult_sources_enabled", False)
    if action == "choose":
        from ..interactions import choose_view

        view, ambiguity = choose_view(db, context, "download", now, args.get("view_id"))
        if ambiguity:
            return ambiguity
        if not view:
            return Result(
                "needs_input",
                "download_view_unavailable",
                "La lista no está disponible o venció. Vuelve a buscar con /dl buscar.",
            )
        data = json.loads(view["data_json"])
        if args["choice"] > len(data["choices"]):
            return Result(
                "needs_input", "download_choice_out_of_range", "La elección no está en esa vista."
            )
        selected = data["choices"][args["choice"] - 1]
        params = {**data["arguments"], "url": selected["url"], "title": selected["title"]}
        params.pop("query", None)
        operation = "download_media.url"
    else:
        params = dict(args)
        operation = spec.operation
    try:
        if "url" in params:
            params["url"] = validate_url(params["url"], adult)
        if params.get("source") in ("pornhub", "xnxx", "adult") and not adult:
            raise MediaError("adult_sources_disabled")
        if action == "search" and params.get("source", "youtube") not in (
            "youtube",
            "pornhub",
            "xnxx",
            "adult",
        ):
            raise MediaError("source_search_unavailable")
    except MediaError as exc:
        return Result(
            "failed", exc.code, "La fuente o el enlace no están admitidos para esta operación."
        )
    return jobs.reserve(db, context, operation, params, [], now)
