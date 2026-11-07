# Cobertura natural · inventario F0

155 variantes, 146 operaciones y 34 familias. Contratos nativos comprobados contra ejemplos del parser; comprensión GLM pendiente de F7.
F5:155 variantes con contrato y despacho comprobados mediante dobles; no acredita efectos, disponibilidad productiva ni semántica GLM (F7).
Inventario reproducido desde Registry; destino = operation + original_action del dispatcher.

| Variante | Operación | Acción del dominio | Estado |
| --- | --- | --- | --- |
| ayuda | core.help | help | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| estado | core.estado | estado | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| cancelar | core.cancelar | cancelar | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| confirmar | core.confirmar | confirmar | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bot.estado | manage_conversation.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bot.modo | manage_conversation.mode | mode | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bot.pausa | manage_conversation.pause | pause | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bot.reanudar | manage_conversation.resume | resume | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| reaccion | send_sticker.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| sticker | make_sticker.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ia | conversation.respond | respond | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| nota.guardar | save_note.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| notas | find_notes.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ocr | read_image.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| qr | read_image.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| transcribir | transcribe_media.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.mp3 | download_media.url | url | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.mp4 | download_media.url | url | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.webm | download_media.url | url | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.srt | download_media.url | url | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.buscar | download_media.search | search | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.elegir | download_media.choose | choose | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.detalle | download_media.inspect | inspect | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| dl.anterior | download_media.previous | previous | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| editar | edit_media.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| voz | make_voice.verbatim | verbatim | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| voz.crear | make_voice.compose | compose | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| voz.cita | make_voice.verbatim | verbatim | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| voz.ultima | make_voice.verbatim | verbatim | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| voces | make_voice.catalog | catalog | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamar | control_call.start | start | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.estado | control_call.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.colgar | control_call.hangup | hangup | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.cancelar | control_call.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pdf.iniciar | manage_pdf.start | start | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pdf.agregar | manage_pdf.add | add | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pdf.terminar | manage_pdf.finish | finish | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pdf.cancelar | manage_pdf.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pdf.extraer | manage_pdf.extract | extract | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pdf.reintentar | manage_pdf.retry | retry | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| convertir | convert_document.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| tarea.crear | manage_school.add_task | add_task | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| tareas | manage_school.list_tasks | list_tasks | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| tarea.completar | manage_school.complete_task | complete_task | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| tarea.borrar | manage_school.delete_task | delete_task | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| tarea.archivo | manage_school.get_attachment | get_attachment | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| horario.agregar | manage_school.set_lesson | set_lesson | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| horario.listar | manage_school.list_schedule | list_schedule | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| horario.borrar | manage_school.delete_lesson | delete_lesson | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| escuela.resumen.configurar | manage_school.configure_digest | configure_digest | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| escuela.resumen.estado | manage_school.status_digest | status_digest | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| encuesta.crear | manage_poll.create | create | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| encuesta.votar | manage_poll.vote | vote | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| encuesta.resultados | manage_poll.results | results | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| encuesta.cerrar | manage_poll.close | close | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recado.preparar | manage_messages.prepare | prepare | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recado.estado | manage_messages.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recado.enviar | manage_messages.send | send | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recado.cancelar | manage_messages.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| contactos | manage_messages.contacts | contacts | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pack.catalogo | manage_pack.catalog | catalog | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pack.comprar | manage_pack.buy | buy | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pack.confirmar | manage_pack.buy | buy | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| pack.estado | manage_pack.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| coop.crear | manage_cooperacha.start | start | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| coop.aportar | manage_cooperacha.contribute | contribute | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| coop.estado | manage_cooperacha.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| coop.cancelar | manage_cooperacha.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| hh.iniciar | manage_happy_hour.start | start | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| hh.parar | manage_happy_hour.stop | stop | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| hh.estado | manage_happy_hour.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| hh.lluvia | manage_happy_hour.rain | rain | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| hh.airdrop | manage_happy_hour.airdrop | airdrop | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| hh.reclamar | manage_happy_hour.claim | claim | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mem.guardar | manage_memory.remember | remember | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mem.listar | manage_memory.list | list | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mem.corregir | manage_memory.correct | correct | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mem.olvidar | manage_memory.forget | forget | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mem.borrar-todo | manage_memory.forget_all | forget_all | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.estado | manage_minecraft.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.jugadores | manage_minecraft.players | players | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.mundos | manage_minecraft.worlds | worlds | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.mods | manage_minecraft.mods | mods | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.config | manage_minecraft.config | config | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.diagnostico | manage_minecraft.discover | discover | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.iniciar | manage_minecraft.start | start | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.parar | manage_minecraft.stop | stop | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.reiniciar | manage_minecraft.restart | restart | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.backup | manage_minecraft.backup | backup | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.recuperar | manage_minecraft.recover | recover | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.mod.activar | manage_minecraft.enable_mod | enable_mod | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.mod.desactivar | manage_minecraft.disable_mod | disable_mod | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| mc.consola | manage_minecraft.console | console | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.advertir | manage_admin.warn | warn | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.quitar-aviso | manage_admin.unwarn | unwarn | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.avisos | manage_admin.warnings | warnings | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.expulsar | manage_admin.kick | kick | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.ban | manage_admin.ban | ban | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.unban | manage_admin.unban | unban | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.promover | manage_admin.promote | promote | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.degradar | manage_admin.demote | demote | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.silenciar | manage_admin.mute | mute | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.desilenciar | manage_admin.unmute | unmute | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.cerrar | manage_admin.lock | lock | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.abrir | manage_admin.unlock | unlock | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.xp-dar | manage_admin.xp_grant | xp_grant | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.xp-quitar | manage_admin.xp_remove | xp_remove | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.nuclear-preparar | manage_admin.nuclear_prepare | nuclear_prepare | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.nuclear-confirmar | manage_admin.nuclear_confirm | nuclear_confirm | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| admin.nuclear-cancelar | manage_admin.nuclear_cancel | nuclear_cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.iniciar | manage_blackjack.start | start | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.mesa | manage_blackjack.table | table | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.entrar | manage_blackjack.join | join | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.repartir | manage_blackjack.deal | deal | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.pedir | manage_blackjack.hit | hit | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.plantarse | manage_blackjack.stand | stand | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.doblar | manage_blackjack.double | double | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.estado | manage_blackjack.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| bj.cancelar | manage_blackjack.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ruleta.crear | manage_roulette.create | create | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ruleta.entrar | manage_roulette.join | join | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ruleta.jugar | manage_roulette.play | play | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ruleta.estado | manage_roulette.status | status | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| ruleta.cancelar | manage_roulette.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| broma | make_prank.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| daily | manage_economy.daily | daily | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| saldo | manage_economy.balance | balance | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| top | manage_economy.top | top | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recordar.en | manage_reminder.create | create | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recordar.el | manage_reminder.create | create | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recordatorios | manage_reminder.list | list | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recordatorio.cancelar | manage_reminder.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| recordatorio.archivar | manage_reminder.archive | archive | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| buscar | search_web.run |  | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| drive.guardar | manage_drive.save | save | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| drive.buscar | manage_drive.search | search | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| drive.elegir | manage_drive.choose | choose | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| drive.cuota | manage_drive.capacity | capacity | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.lista | audiovisual.clip.list | list | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.poner | audiovisual.clip.play | play | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.pausa | audiovisual.clip.pause | pause | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.seguir | audiovisual.clip.resume | resume | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.repetir | audiovisual.clip.replay | replay | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.siguiente | audiovisual.clip.next | next | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.parar | audiovisual.clip.stop | stop | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.volumen | audiovisual.clip.volume | volume | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| clip.ajustar | audiovisual.clip.volume | volume | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| avatar.fondo | audiovisual.avatar.background | background | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| avatar.expresion | audiovisual.avatar.expression | expression | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| avatar.gesto | audiovisual.avatar.gesture | gesture | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| avatar.rubor | audiovisual.avatar.blush | blush | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.programar | audiovisual.agenda.create | create | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.agenda | audiovisual.agenda.list | list | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.reprogramar | audiovisual.agenda.update | update | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
| llamada.cancelar-agenda | audiovisual.agenda.cancel | cancel | CONTRACT_AND_DISPATCH_DOUBLE_PASS |
