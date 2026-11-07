# Cobertura natural · inventario F0

155 variantes, 146 operaciones y 34 familias. Contratos nativos comprobados contra ejemplos del parser; comprensión GLM pendiente de F7.
Inventario reproducido desde Registry; destino = operation + original_action del dispatcher.

| Variante | Operación | Acción del dominio | Estado |
| --- | --- | --- | --- |
| ayuda | core.help | help | CONTRACT_LOCAL_PASS |
| estado | core.estado | estado | CONTRACT_LOCAL_PASS |
| cancelar | core.cancelar | cancelar | CONTRACT_LOCAL_PASS |
| confirmar | core.confirmar | confirmar | CONTRACT_LOCAL_PASS |
| bot.estado | manage_conversation.status | status | CONTRACT_LOCAL_PASS |
| bot.modo | manage_conversation.mode | mode | CONTRACT_LOCAL_PASS |
| bot.pausa | manage_conversation.pause | pause | CONTRACT_LOCAL_PASS |
| bot.reanudar | manage_conversation.resume | resume | CONTRACT_LOCAL_PASS |
| reaccion | send_sticker.run |  | CONTRACT_LOCAL_PASS |
| sticker | make_sticker.run |  | CONTRACT_LOCAL_PASS |
| ia | conversation.respond | respond | CONTRACT_LOCAL_PASS |
| nota.guardar | save_note.run |  | CONTRACT_LOCAL_PASS |
| notas | find_notes.run |  | CONTRACT_LOCAL_PASS |
| ocr | read_image.run |  | CONTRACT_LOCAL_PASS |
| qr | read_image.run |  | CONTRACT_LOCAL_PASS |
| transcribir | transcribe_media.run |  | CONTRACT_LOCAL_PASS |
| dl.mp3 | download_media.url | url | CONTRACT_LOCAL_PASS |
| dl.mp4 | download_media.url | url | CONTRACT_LOCAL_PASS |
| dl.webm | download_media.url | url | CONTRACT_LOCAL_PASS |
| dl.srt | download_media.url | url | CONTRACT_LOCAL_PASS |
| dl.buscar | download_media.search | search | CONTRACT_LOCAL_PASS |
| dl.elegir | download_media.choose | choose | CONTRACT_LOCAL_PASS |
| dl.detalle | download_media.inspect | inspect | CONTRACT_LOCAL_PASS |
| dl.anterior | download_media.previous | previous | CONTRACT_LOCAL_PASS |
| editar | edit_media.run |  | CONTRACT_LOCAL_PASS |
| voz | make_voice.verbatim | verbatim | CONTRACT_LOCAL_PASS |
| voz.crear | make_voice.compose | compose | CONTRACT_LOCAL_PASS |
| voz.cita | make_voice.verbatim | verbatim | CONTRACT_LOCAL_PASS |
| voz.ultima | make_voice.verbatim | verbatim | CONTRACT_LOCAL_PASS |
| voces | make_voice.catalog | catalog | CONTRACT_LOCAL_PASS |
| llamar | control_call.start | start | CONTRACT_LOCAL_PASS |
| llamada.estado | control_call.status | status | CONTRACT_LOCAL_PASS |
| llamada.colgar | control_call.hangup | hangup | CONTRACT_LOCAL_PASS |
| llamada.cancelar | control_call.cancel | cancel | CONTRACT_LOCAL_PASS |
| pdf.iniciar | manage_pdf.start | start | CONTRACT_LOCAL_PASS |
| pdf.agregar | manage_pdf.add | add | CONTRACT_LOCAL_PASS |
| pdf.terminar | manage_pdf.finish | finish | CONTRACT_LOCAL_PASS |
| pdf.cancelar | manage_pdf.cancel | cancel | CONTRACT_LOCAL_PASS |
| pdf.extraer | manage_pdf.extract | extract | CONTRACT_LOCAL_PASS |
| pdf.reintentar | manage_pdf.retry | retry | CONTRACT_LOCAL_PASS |
| convertir | convert_document.run |  | CONTRACT_LOCAL_PASS |
| tarea.crear | manage_school.add_task | add_task | CONTRACT_LOCAL_PASS |
| tareas | manage_school.list_tasks | list_tasks | CONTRACT_LOCAL_PASS |
| tarea.completar | manage_school.complete_task | complete_task | CONTRACT_LOCAL_PASS |
| tarea.borrar | manage_school.delete_task | delete_task | CONTRACT_LOCAL_PASS |
| tarea.archivo | manage_school.get_attachment | get_attachment | CONTRACT_LOCAL_PASS |
| horario.agregar | manage_school.set_lesson | set_lesson | CONTRACT_LOCAL_PASS |
| horario.listar | manage_school.list_schedule | list_schedule | CONTRACT_LOCAL_PASS |
| horario.borrar | manage_school.delete_lesson | delete_lesson | CONTRACT_LOCAL_PASS |
| escuela.resumen.configurar | manage_school.configure_digest | configure_digest | CONTRACT_LOCAL_PASS |
| escuela.resumen.estado | manage_school.status_digest | status_digest | CONTRACT_LOCAL_PASS |
| encuesta.crear | manage_poll.create | create | CONTRACT_LOCAL_PASS |
| encuesta.votar | manage_poll.vote | vote | CONTRACT_LOCAL_PASS |
| encuesta.resultados | manage_poll.results | results | CONTRACT_LOCAL_PASS |
| encuesta.cerrar | manage_poll.close | close | CONTRACT_LOCAL_PASS |
| recado.preparar | manage_messages.prepare | prepare | CONTRACT_LOCAL_PASS |
| recado.estado | manage_messages.status | status | CONTRACT_LOCAL_PASS |
| recado.enviar | manage_messages.send | send | CONTRACT_LOCAL_PASS |
| recado.cancelar | manage_messages.cancel | cancel | CONTRACT_LOCAL_PASS |
| contactos | manage_messages.contacts | contacts | CONTRACT_LOCAL_PASS |
| pack.catalogo | manage_pack.catalog | catalog | CONTRACT_LOCAL_PASS |
| pack.comprar | manage_pack.buy | buy | CONTRACT_LOCAL_PASS |
| pack.confirmar | manage_pack.buy | buy | CONTRACT_LOCAL_PASS |
| pack.estado | manage_pack.status | status | CONTRACT_LOCAL_PASS |
| coop.crear | manage_cooperacha.start | start | CONTRACT_LOCAL_PASS |
| coop.aportar | manage_cooperacha.contribute | contribute | CONTRACT_LOCAL_PASS |
| coop.estado | manage_cooperacha.status | status | CONTRACT_LOCAL_PASS |
| coop.cancelar | manage_cooperacha.cancel | cancel | CONTRACT_LOCAL_PASS |
| hh.iniciar | manage_happy_hour.start | start | CONTRACT_LOCAL_PASS |
| hh.parar | manage_happy_hour.stop | stop | CONTRACT_LOCAL_PASS |
| hh.estado | manage_happy_hour.status | status | CONTRACT_LOCAL_PASS |
| hh.lluvia | manage_happy_hour.rain | rain | CONTRACT_LOCAL_PASS |
| hh.airdrop | manage_happy_hour.airdrop | airdrop | CONTRACT_LOCAL_PASS |
| hh.reclamar | manage_happy_hour.claim | claim | CONTRACT_LOCAL_PASS |
| mem.guardar | manage_memory.remember | remember | CONTRACT_LOCAL_PASS |
| mem.listar | manage_memory.list | list | CONTRACT_LOCAL_PASS |
| mem.corregir | manage_memory.correct | correct | CONTRACT_LOCAL_PASS |
| mem.olvidar | manage_memory.forget | forget | CONTRACT_LOCAL_PASS |
| mem.borrar-todo | manage_memory.forget_all | forget_all | CONTRACT_LOCAL_PASS |
| mc.estado | manage_minecraft.status | status | CONTRACT_LOCAL_PASS |
| mc.jugadores | manage_minecraft.players | players | CONTRACT_LOCAL_PASS |
| mc.mundos | manage_minecraft.worlds | worlds | CONTRACT_LOCAL_PASS |
| mc.mods | manage_minecraft.mods | mods | CONTRACT_LOCAL_PASS |
| mc.config | manage_minecraft.config | config | CONTRACT_LOCAL_PASS |
| mc.diagnostico | manage_minecraft.discover | discover | CONTRACT_LOCAL_PASS |
| mc.iniciar | manage_minecraft.start | start | CONTRACT_LOCAL_PASS |
| mc.parar | manage_minecraft.stop | stop | CONTRACT_LOCAL_PASS |
| mc.reiniciar | manage_minecraft.restart | restart | CONTRACT_LOCAL_PASS |
| mc.backup | manage_minecraft.backup | backup | CONTRACT_LOCAL_PASS |
| mc.recuperar | manage_minecraft.recover | recover | CONTRACT_LOCAL_PASS |
| mc.mod.activar | manage_minecraft.enable_mod | enable_mod | CONTRACT_LOCAL_PASS |
| mc.mod.desactivar | manage_minecraft.disable_mod | disable_mod | CONTRACT_LOCAL_PASS |
| mc.consola | manage_minecraft.console | console | CONTRACT_LOCAL_PASS |
| admin.advertir | manage_admin.warn | warn | CONTRACT_LOCAL_PASS |
| admin.quitar-aviso | manage_admin.unwarn | unwarn | CONTRACT_LOCAL_PASS |
| admin.avisos | manage_admin.warnings | warnings | CONTRACT_LOCAL_PASS |
| admin.expulsar | manage_admin.kick | kick | CONTRACT_LOCAL_PASS |
| admin.ban | manage_admin.ban | ban | CONTRACT_LOCAL_PASS |
| admin.unban | manage_admin.unban | unban | CONTRACT_LOCAL_PASS |
| admin.promover | manage_admin.promote | promote | CONTRACT_LOCAL_PASS |
| admin.degradar | manage_admin.demote | demote | CONTRACT_LOCAL_PASS |
| admin.silenciar | manage_admin.mute | mute | CONTRACT_LOCAL_PASS |
| admin.desilenciar | manage_admin.unmute | unmute | CONTRACT_LOCAL_PASS |
| admin.cerrar | manage_admin.lock | lock | CONTRACT_LOCAL_PASS |
| admin.abrir | manage_admin.unlock | unlock | CONTRACT_LOCAL_PASS |
| admin.xp-dar | manage_admin.xp_grant | xp_grant | CONTRACT_LOCAL_PASS |
| admin.xp-quitar | manage_admin.xp_remove | xp_remove | CONTRACT_LOCAL_PASS |
| admin.nuclear-preparar | manage_admin.nuclear_prepare | nuclear_prepare | CONTRACT_LOCAL_PASS |
| admin.nuclear-confirmar | manage_admin.nuclear_confirm | nuclear_confirm | CONTRACT_LOCAL_PASS |
| admin.nuclear-cancelar | manage_admin.nuclear_cancel | nuclear_cancel | CONTRACT_LOCAL_PASS |
| bj.iniciar | manage_blackjack.start | start | CONTRACT_LOCAL_PASS |
| bj.mesa | manage_blackjack.table | table | CONTRACT_LOCAL_PASS |
| bj.entrar | manage_blackjack.join | join | CONTRACT_LOCAL_PASS |
| bj.repartir | manage_blackjack.deal | deal | CONTRACT_LOCAL_PASS |
| bj.pedir | manage_blackjack.hit | hit | CONTRACT_LOCAL_PASS |
| bj.plantarse | manage_blackjack.stand | stand | CONTRACT_LOCAL_PASS |
| bj.doblar | manage_blackjack.double | double | CONTRACT_LOCAL_PASS |
| bj.estado | manage_blackjack.status | status | CONTRACT_LOCAL_PASS |
| bj.cancelar | manage_blackjack.cancel | cancel | CONTRACT_LOCAL_PASS |
| ruleta.crear | manage_roulette.create | create | CONTRACT_LOCAL_PASS |
| ruleta.entrar | manage_roulette.join | join | CONTRACT_LOCAL_PASS |
| ruleta.jugar | manage_roulette.play | play | CONTRACT_LOCAL_PASS |
| ruleta.estado | manage_roulette.status | status | CONTRACT_LOCAL_PASS |
| ruleta.cancelar | manage_roulette.cancel | cancel | CONTRACT_LOCAL_PASS |
| broma | make_prank.run |  | CONTRACT_LOCAL_PASS |
| daily | manage_economy.daily | daily | CONTRACT_LOCAL_PASS |
| saldo | manage_economy.balance | balance | CONTRACT_LOCAL_PASS |
| top | manage_economy.top | top | CONTRACT_LOCAL_PASS |
| recordar.en | manage_reminder.create | create | CONTRACT_LOCAL_PASS |
| recordar.el | manage_reminder.create | create | CONTRACT_LOCAL_PASS |
| recordatorios | manage_reminder.list | list | CONTRACT_LOCAL_PASS |
| recordatorio.cancelar | manage_reminder.cancel | cancel | CONTRACT_LOCAL_PASS |
| recordatorio.archivar | manage_reminder.archive | archive | CONTRACT_LOCAL_PASS |
| buscar | search_web.run |  | CONTRACT_LOCAL_PASS |
| drive.guardar | manage_drive.save | save | CONTRACT_LOCAL_PASS |
| drive.buscar | manage_drive.search | search | CONTRACT_LOCAL_PASS |
| drive.elegir | manage_drive.choose | choose | CONTRACT_LOCAL_PASS |
| drive.cuota | manage_drive.capacity | capacity | CONTRACT_LOCAL_PASS |
| clip.lista | audiovisual.clip.list | list | CONTRACT_LOCAL_PASS |
| clip.poner | audiovisual.clip.play | play | CONTRACT_LOCAL_PASS |
| clip.pausa | audiovisual.clip.pause | pause | CONTRACT_LOCAL_PASS |
| clip.seguir | audiovisual.clip.resume | resume | CONTRACT_LOCAL_PASS |
| clip.repetir | audiovisual.clip.replay | replay | CONTRACT_LOCAL_PASS |
| clip.siguiente | audiovisual.clip.next | next | CONTRACT_LOCAL_PASS |
| clip.parar | audiovisual.clip.stop | stop | CONTRACT_LOCAL_PASS |
| clip.volumen | audiovisual.clip.volume | volume | CONTRACT_LOCAL_PASS |
| clip.ajustar | audiovisual.clip.volume | volume | CONTRACT_LOCAL_PASS |
| avatar.fondo | audiovisual.avatar.background | background | CONTRACT_LOCAL_PASS |
| avatar.expresion | audiovisual.avatar.expression | expression | CONTRACT_LOCAL_PASS |
| avatar.gesto | audiovisual.avatar.gesture | gesture | CONTRACT_LOCAL_PASS |
| avatar.rubor | audiovisual.avatar.blush | blush | CONTRACT_LOCAL_PASS |
| llamada.programar | audiovisual.agenda.create | create | CONTRACT_LOCAL_PASS |
| llamada.agenda | audiovisual.agenda.list | list | CONTRACT_LOCAL_PASS |
| llamada.reprogramar | audiovisual.agenda.update | update | CONTRACT_LOCAL_PASS |
| llamada.cancelar-agenda | audiovisual.agenda.cancel | cancel | CONTRACT_LOCAL_PASS |
