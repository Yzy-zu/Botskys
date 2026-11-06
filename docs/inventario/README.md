# Inventario R0 · referencia técnica

Referencia de código `7e12d5401611ddb6664211f55c2f3066661017dd` (plan documental posterior a `98d147a`).
Hashes en reference.json. Instalación activa según relevo: NLP 0.2.2; no se inspeccionó ni modificó el proceso.

Catálogo exportado con todas las capacidades habilitadas: **30**. No implica habilitación en Botsky.

| Herramienta | Acciones del catálogo | Campos originales |
| --- | --- | --- |
| `manage_conversation` | cancel, mode, pause, resume, status | action, value |
| `send_sticker` | operación única | sticker_id, requested |
| `make_sticker` | operación única | attachment_id |
| `conversation` | respond, ask, silent | action, text_lines, table, footer, literal_span |
| `save_note` | operación única | text_lines, literal_span |
| `find_notes` | operación única | query, page |
| `read_image` | operación única | mode, attachment_id |
| `transcribe_media` | operación única | attachment_id, summarize, output_mode |
| `download_media` | operación única | query, url, choice, previous, format, source, options |
| `edit_media` | operación única | attachment_id, options |
| `make_voice` | operación única | mode, text, voice, effect, source, requested_seconds |
| `control_call` | start, status, hangup, cancel | action, topic, max_seconds, video |
| `manage_pdf` | start, add, finish, extract, retry, cancel | action, attachment_ids, pages, confirm_uncertain |
| `convert_document` | operación única | target, attachment_id |
| `manage_school` | add_task, list_tasks, complete_task, delete_task, set_lesson, list_schedule, delete_lesson, configure_digest, status_digest, get_attachment | action, text, subject, due_date, due_time, time_text, task_id, weekday, start_time, end_time, lesson_id, enabled, digest_time, page, include_closed, attach, attachment_id |
| `manage_poll` | create, vote, results, close | action, question, options, poll_id, choice |
| `manage_messages` | prepare, status, send, cancel, contacts | action, draft_id, recipients, text, source, attach |
| `manage_pack` | catalog, buy, status | action, category, purchase_id, page |
| `manage_cooperacha` | start, contribute, status, cancel | action, challenge_id, category, target_xp, amount |
| `manage_happy_hour` | start, stop, status, rain, airdrop, claim | action, duration_minutes, event_id |
| `manage_memory` | remember, list, correct, forget, forget_all | action, memory_id, kind, text, page |
| `manage_minecraft` | status, players, worlds, mods, config, start, stop, restart, backup, enable_mod, disable_mod, console | action, name, command |
| `manage_admin` | warn, unwarn, warnings, kick, ban, unban, promote, demote, mute, unmute, lock, unlock, xp_grant, xp_remove, nuclear_prepare, nuclear_confirm, nuclear_cancel | action, target, warning_id, account_id, amount, draft_id |
| `manage_blackjack` | start, table, join, deal, hit, stand, double, status, cancel | action, bet, game_id |
| `manage_roulette` | create, join, play, status, cancel | action, bet, room_id |
| `make_prank` | operación única | label |
| `manage_economy` | daily, balance, top | action |
| `manage_reminder` | create, list, cancel, archive | action, text, time_text, at, after_seconds, reminder_id, include_closed, page |
| `search_web` | operación única | query, required_terms |
| `manage_drive` | save, search, choose, capacity | action, query, choice, attachment_id |

Modelos, restricciones por campo y validadores completos: [args.json](args.json).
Declaraciones completas de referencia: [catalog.json](catalog.json). No se trasladan `interpretation`, anclas lingüísticas ni clasificador al parser.

La matriz acción/campo de sintaxis es el cierre de R1, no una capacidad ya implementada en R0.
