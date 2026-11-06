"""IA/ASR/TTS consumen contratos de contenido; carecen de registro o ejecutor general."""

from ..contracts import Result
from ..jobs import EngineOutput
from .process import MediaError


async def analysis_files(paths, directory):
    from ..adapters.gemini import ContentFile
    from .documents import DocumentEngine, detect_document_format
    from .media_edit import _demuxer

    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "webp": "image/webp",
        "pdf": "application/pdf",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "flac": "audio/flac",
        "aac": "audio/aac",
        "txt": "text/plain",
    }
    result = []
    for index, path in enumerate(paths):
        with path.open("rb") as stream:
            header = stream.read(4096)
        try:
            format = _demuxer(header)
            format = {"mov": "mp4", "matroska": "webm"}.get(format, format)
        except MediaError:
            if path.stat().st_size > 100000000:
                raise MediaError("analysis_document_too_large")
            format = detect_document_format(path.read_bytes())
        if format == "pdf":
            path = await DocumentEngine(directory / f"analysis-{index}").convert(
                path.read_bytes(), "pdf"
            )
        elif format == "tiff":
            path = await DocumentEngine(directory / f"analysis-{index}").convert(
                path.read_bytes(), "pdf"
            )
            format = "pdf"
        elif format in ("png", "jpg", "webp"):
            from .image_validation import _image_codec, validate_image

            await validate_image(path, _image_codec(path.read_bytes()))
        elif format not in mime:
            path = await DocumentEngine(directory / f"analysis-{index}").convert(
                path.read_bytes(), "txt"
            )
            format = "txt"
        result.append(ContentFile(path, mime[format], path.stat().st_size))
    return result


async def execute(job, directory, paths, manager, gemini, tts, asr):
    operation = job["operation"]
    args = job["arguments"]
    if operation == "conversation.respond":
        if gemini is None:
            raise MediaError("gemini_not_configured")
        files = await analysis_files(paths, directory)
        manager.mark_provider(job)
        text = await gemini.generate(
            args["text"],
            purpose="answer",
            history=args.get("history", ()),
            files=files,
            quoted_text=args.get("quoted_text"),
            memories=args.get("memories", ()),
        )
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise MediaError("gemini_invalid_response")
        return EngineOutput(Result("ok", "ai_reply", text, {"purpose": "answer"}))
    if operation.startswith("make_voice."):
        if tts is None:
            raise MediaError("tts_not_configured")
        text = args["text"]
        manager.mark_provider(job)
        if args["mode"] == "compose":
            if gemini is None:
                raise MediaError("gemini_not_configured")
            text = await gemini.generate(
                text, purpose="compose", requested_seconds=args.get("requested_seconds")
            )
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise MediaError("voice_invalid_text")
        output = await tts.synthesize(text, args["voice"], args["effect"], directory)
        return EngineOutput(
            Result(
                "ok",
                "voice_ready",
                "Voz " + ("literal" if args["mode"] == "verbatim" else "compuesta") + " lista.",
                {
                    "mode": args["mode"],
                    "spoken_text": text,
                    "voice": args["voice"],
                    "effect": args["effect"],
                },
            ),
            (output,),
        )
    if operation == "transcribe_media.run":
        if asr is None:
            raise MediaError("asr_not_configured")
        if paths[0].stat().st_size > 10 * 1024 * 1024:
            raise MediaError("audio_too_large")
        from .audio import AudioTranscriber

        manager.mark_provider(job)
        result = await AudioTranscriber(directory / "asr", asr).transcribe(paths[0].read_bytes())
        if result.status != "ok":
            return EngineOutput(result)
        transcript = result.text
        mode = args["output_mode"]
        if mode == "texto":
            return EngineOutput(
                Result("ok", "transcript_ready", transcript, {"transcript": transcript})
            )
        try:
            if gemini is None:
                raise MediaError("gemini_not_configured")
            summary = await gemini.generate(transcript, purpose="summary")
            if not isinstance(summary, str) or not summary.strip() or len(summary) > 6000:
                raise MediaError("invalid_summary")
        except Exception:
            return EngineOutput(
                Result(
                    "failed",
                    "summary_unavailable",
                    (transcript + "\n\n" if mode == "ambos" else "")
                    + "La transcripción se completó, pero el resumen no está disponible.",
                    {"transcript": transcript},
                )
            )
        return EngineOutput(
            Result(
                "ok",
                "transcript_summary_ready",
                (transcript + "\n\nResumen:\n" if mode == "ambos" else "") + summary,
                {"transcript": transcript, "summary": summary},
            )
        )
    raise MediaError("content_operation_unavailable")
