# Cobertura natural · inventario F0

155 variantes, 146 operaciones y 34 familias. Contratos naturales pendientes de F1.
Inventario reproducido desde Registry; destino = operation + original_action del dispatcher.

| Variante | Operación | Acción del dominio | Estado |
| --- | --- | --- | --- |
| ayuda | core.help | help | PENDING_F1 |
| estado | core.estado | estado | PENDING_F1 |
| cancelar | core.cancelar | cancelar | PENDING_F1 |
| confirmar | core.confirmar | confirmar | PENDING_F1 |
| bot.estado | manage_conversation.status | status | PENDING_F1 |
| bot.modo | manage_conversation.mode | mode | PENDING_F1 |
| bot.pausa | manage_conversation.pause | pause | PENDING_F1 |
| bot.reanudar | manage_conversation.resume | resume | PENDING_F1 |
| reaccion | send_sticker.run |  | PENDING_F1 |
| sticker | make_sticker.run |  | PENDING_F1 |
| ia | conversation.respond | respond | PENDING_F1 |
| nota.guardar | save_note.run |  | PENDING_F1 |
| notas | find_notes.run |  | PENDING_F1 |
| ocr | read_image.run |  | PENDING_F1 |
| qr | read_image.run |  | PENDING_F1 |
| transcribir | transcribe_media.run |  | PENDING_F1 |
| dl.mp3 | download_media.url | url | PENDING_F1 |
| dl.mp4 | download_media.url | url | PENDING_F1 |
| dl.webm | download_media.url | url | PENDING_F1 |
| dl.srt | download_media.url | url | PENDING_F1 |
| dl.buscar | download_media.search | search | PENDING_F1 |
| dl.elegir | download_media.choose | choose | PENDING_F1 |
| dl.detalle | download_media.inspect | inspect | PENDING_F1 |
| dl.anterior | download_media.previous | previous | PENDING_F1 |
| editar | edit_media.run |  | PENDING_F1 |
| voz | make_voice.verbatim | verbatim | PENDING_F1 |
| voz.crear | make_voice.compose | compose | PENDING_F1 |
| voz.cita | make_voice.verbatim | verbatim | PENDING_F1 |
| voz.ultima | make_voice.verbatim | verbatim | PENDING_F1 |
| voces | make_voice.catalog | catalog | PENDING_F1 |
| llamar | control_call.start | start | PENDING_F1 |
| llamada.estado | control_call.status | status | PENDING_F1 |
| llamada.colgar | control_call.hangup | hangup | PENDING_F1 |
| llamada.cancelar | control_call.cancel | cancel | PENDING_F1 |
| pdf.iniciar | manage_pdf.start | start | PENDING_F1 |
| pdf.agregar | manage_pdf.add | add | PENDING_F1 |
| pdf.terminar | manage_pdf.finish | finish | PENDING_F1 |
| pdf.cancelar | manage_pdf.cancel | cancel | PENDING_F1 |
| pdf.extraer | manage_pdf.extract | extract | PENDING_F1 |
| pdf.reintentar | manage_pdf.retry | retry | PENDING_F1 |
| convertir | convert_document.run |  | PENDING_F1 |
| tarea.crear | manage_school.add_task | add_task | PENDING_F1 |
| tareas | manage_school.list_tasks | list_tasks | PENDING_F1 |
| tarea.completar | manage_school.complete_task | complete_task | PENDING_F1 |
| tarea.borrar | manage_school.delete_task | delete_task | PENDING_F1 |
| tarea.archivo | manage_school.get_attachment | get_attachment | PENDING_F1 |
| horario.agregar | manage_school.set_lesson | set_lesson | PENDING_F1 |
| horario.listar | manage_school.list_schedule | list_schedule | PENDING_F1 |
| horario.borrar | manage_school.delete_lesson | delete_lesson | PENDING_F1 |
| escuela.resumen.configurar | manage_school.configure_digest | configure_digest | PENDING_F1 |
| escuela.resumen.estado | manage_school.status_digest | status_digest | PENDING_F1 |
| encuesta.crear | manage_poll.create | create | PENDING_F1 |
| encuesta.votar | manage_poll.vote | vote | PENDING_F1 |
| encuesta.resultados | manage_poll.results | results | PENDING_F1 |
| encuesta.cerrar | manage_poll.close | close | PENDING_F1 |
| recado.preparar | manage_messages.prepare | prepare | PENDING_F1 |
| recado.estado | manage_messages.status | status | PENDING_F1 |
| recado.enviar | manage_messages.send | send | PENDING_F1 |
| recado.cancelar | manage_messages.cancel | cancel | PENDING_F1 |
| contactos | manage_messages.contacts | contacts | PENDING_F1 |
| pack.catalogo | manage_pack.catalog | catalog | PENDING_F1 |
| pack.comprar | manage_pack.buy | buy | PENDING_F1 |
| pack.confirmar | manage_pack.buy | buy | PENDING_F1 |
| pack.estado | manage_pack.status | status | PENDING_F1 |
| coop.crear | manage_cooperacha.start | start | PENDING_F1 |
| coop.aportar | manage_cooperacha.contribute | contribute | PENDING_F1 |
| coop.estado | manage_cooperacha.status | status | PENDING_F1 |
| coop.cancelar | manage_cooperacha.cancel | cancel | PENDING_F1 |
| hh.iniciar | manage_happy_hour.start | start | PENDING_F1 |
| hh.parar | manage_happy_hour.stop | stop | PENDING_F1 |
| hh.estado | manage_happy_hour.status | status | PENDING_F1 |
| hh.lluvia | manage_happy_hour.rain | rain | PENDING_F1 |
| hh.airdrop | manage_happy_hour.airdrop | airdrop | PENDING_F1 |
| hh.reclamar | manage_happy_hour.claim | claim | PENDING_F1 |
| mem.guardar | manage_memory.remember | remember | PENDING_F1 |
| mem.listar | manage_memory.list | list | PENDING_F1 |
| mem.corregir | manage_memory.correct | correct | PENDING_F1 |
| mem.olvidar | manage_memory.forget | forget | PENDING_F1 |
| mem.borrar-todo | manage_memory.forget_all | forget_all | PENDING_F1 |
| mc.estado | manage_minecraft.status | status | PENDING_F1 |
| mc.jugadores | manage_minecraft.players | players | PENDING_F1 |
| mc.mundos | manage_minecraft.worlds | worlds | PENDING_F1 |
| mc.mods | manage_minecraft.mods | mods | PENDING_F1 |
| mc.config | manage_minecraft.config | config | PENDING_F1 |
| mc.diagnostico | manage_minecraft.discover | discover | PENDING_F1 |
| mc.iniciar | manage_minecraft.start | start | PENDING_F1 |
| mc.parar | manage_minecraft.stop | stop | PENDING_F1 |
| mc.reiniciar | manage_minecraft.restart | restart | PENDING_F1 |
| mc.backup | manage_minecraft.backup | backup | PENDING_F1 |
| mc.recuperar | manage_minecraft.recover | recover | PENDING_F1 |
| mc.mod.activar | manage_minecraft.enable_mod | enable_mod | PENDING_F1 |
| mc.mod.desactivar | manage_minecraft.disable_mod | disable_mod | PENDING_F1 |
| mc.consola | manage_minecraft.console | console | PENDING_F1 |
| admin.advertir | manage_admin.warn | warn | PENDING_F1 |
| admin.quitar-aviso | manage_admin.unwarn | unwarn | PENDING_F1 |
| admin.avisos | manage_admin.warnings | warnings | PENDING_F1 |
| admin.expulsar | manage_admin.kick | kick | PENDING_F1 |
| admin.ban | manage_admin.ban | ban | PENDING_F1 |
| admin.unban | manage_admin.unban | unban | PENDING_F1 |
| admin.promover | manage_admin.promote | promote | PENDING_F1 |
| admin.degradar | manage_admin.demote | demote | PENDING_F1 |
| admin.silenciar | manage_admin.mute | mute | PENDING_F1 |
| admin.desilenciar | manage_admin.unmute | unmute | PENDING_F1 |
| admin.cerrar | manage_admin.lock | lock | PENDING_F1 |
| admin.abrir | manage_admin.unlock | unlock | PENDING_F1 |
| admin.xp-dar | manage_admin.xp_grant | xp_grant | PENDING_F1 |
| admin.xp-quitar | manage_admin.xp_remove | xp_remove | PENDING_F1 |
| admin.nuclear-preparar | manage_admin.nuclear_prepare | nuclear_prepare | PENDING_F1 |
| admin.nuclear-confirmar | manage_admin.nuclear_confirm | nuclear_confirm | PENDING_F1 |
| admin.nuclear-cancelar | manage_admin.nuclear_cancel | nuclear_cancel | PENDING_F1 |
| bj.iniciar | manage_blackjack.start | start | PENDING_F1 |
| bj.mesa | manage_blackjack.table | table | PENDING_F1 |
| bj.entrar | manage_blackjack.join | join | PENDING_F1 |
| bj.repartir | manage_blackjack.deal | deal | PENDING_F1 |
| bj.pedir | manage_blackjack.hit | hit | PENDING_F1 |
| bj.plantarse | manage_blackjack.stand | stand | PENDING_F1 |
| bj.doblar | manage_blackjack.double | double | PENDING_F1 |
| bj.estado | manage_blackjack.status | status | PENDING_F1 |
| bj.cancelar | manage_blackjack.cancel | cancel | PENDING_F1 |
| ruleta.crear | manage_roulette.create | create | PENDING_F1 |
| ruleta.entrar | manage_roulette.join | join | PENDING_F1 |
| ruleta.jugar | manage_roulette.play | play | PENDING_F1 |
| ruleta.estado | manage_roulette.status | status | PENDING_F1 |
| ruleta.cancelar | manage_roulette.cancel | cancel | PENDING_F1 |
| broma | make_prank.run |  | PENDING_F1 |
| daily | manage_economy.daily | daily | PENDING_F1 |
| saldo | manage_economy.balance | balance | PENDING_F1 |
| top | manage_economy.top | top | PENDING_F1 |
| recordar.en | manage_reminder.create | create | PENDING_F1 |
| recordar.el | manage_reminder.create | create | PENDING_F1 |
| recordatorios | manage_reminder.list | list | PENDING_F1 |
| recordatorio.cancelar | manage_reminder.cancel | cancel | PENDING_F1 |
| recordatorio.archivar | manage_reminder.archive | archive | PENDING_F1 |
| buscar | search_web.run |  | PENDING_F1 |
| drive.guardar | manage_drive.save | save | PENDING_F1 |
| drive.buscar | manage_drive.search | search | PENDING_F1 |
| drive.elegir | manage_drive.choose | choose | PENDING_F1 |
| drive.cuota | manage_drive.capacity | capacity | PENDING_F1 |
| clip.lista | audiovisual.clip.list | list | PENDING_F1 |
| clip.poner | audiovisual.clip.play | play | PENDING_F1 |
| clip.pausa | audiovisual.clip.pause | pause | PENDING_F1 |
| clip.seguir | audiovisual.clip.resume | resume | PENDING_F1 |
| clip.repetir | audiovisual.clip.replay | replay | PENDING_F1 |
| clip.siguiente | audiovisual.clip.next | next | PENDING_F1 |
| clip.parar | audiovisual.clip.stop | stop | PENDING_F1 |
| clip.volumen | audiovisual.clip.volume | volume | PENDING_F1 |
| clip.ajustar | audiovisual.clip.volume | volume | PENDING_F1 |
| avatar.fondo | audiovisual.avatar.background | background | PENDING_F1 |
| avatar.expresion | audiovisual.avatar.expression | expression | PENDING_F1 |
| avatar.gesto | audiovisual.avatar.gesture | gesture | PENDING_F1 |
| avatar.rubor | audiovisual.avatar.blush | blush | PENDING_F1 |
| llamada.programar | audiovisual.agenda.create | create | PENDING_F1 |
| llamada.agenda | audiovisual.agenda.list | list | PENDING_F1 |
| llamada.reprogramar | audiovisual.agenda.update | update | PENDING_F1 |
| llamada.cancelar-agenda | audiovisual.agenda.cancel | cancel | PENDING_F1 |
