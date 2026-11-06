# Núcleo y catálogo · R0/R1

Origen: Zhana 7e12d54, contracts.py, tools/catalog.py y modelos *Args (hashes en
docs/inventario/reference.json). Contratos/validadores inventariados en args.json;
no se importa Zhana desde Botsky. Persistencia e ingreso se consultarán en R2.

Problema resuelto de origen: tipos y acciones acotadas, ámbito y guardias previas
a efectos. Sus contratos lingüísticos no forman parte del producto nuevo.

Decisión: reescribir entrada, lexer, registro, parser, recibos y DB. Conservar el
inventario técnico de acciones y restricciones; la autoridad procederá del adaptador.
R0 comprueba integridad de inventario/DB y aislamiento, sin atribuir aceptación
de herramientas. R1 probará sintaxis pura; R2 el recorrido durable con notas.

Límites: no transporte ni proveedor conectado, sin migrar usuario alguno. Nivel
de evidencia: inventario estático y catálogo puro; motores/proveedores NOT_TESTED.
