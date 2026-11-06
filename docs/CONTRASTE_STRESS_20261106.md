# Paquete para contraste · todavía no ejecutado

El propietario elegirá el agente de contraste. Su encargo será revisar lo que
los testers consideran incorrecto antes de decidir correcciones. Este documento
no lanza otro agente, no autoriza nuevas pruebas remotas ni modifica producto.

Leer AGENTS.md, último ESTADO_COMPARTIDO.md y [balance](STRESS_20261106.md). Después:

1. `evidencia/STRESS-20261106/summary.json` y `tools.json`: alcance y recuentos.
2. `claims-for-contrast.json`:50claims de AGY con `UNREVIEWED_AGENT_CLAIM`.
3. `results.json`: expectativas originales, comandos, resultados, archivos y nivel
   de evidencia. Relacionar cada claim con `tool` y `case`; no confiar solo en la
   confianza del modelo ni en que una respuesta tenga status `ok`.
4. `reports.json`: qué funcionó, sospechas, errores de oracle y huecos según cada
   tester. Descargas conserva resultados aunque su informe final esté bloqueado.
5. `orchestrator-observations.json`: cancelación, incidente de harness y rechazo
   del proveedor AGY. La reproducción del atasco exige timeout externo.
6. `route-coverage.json`, `syntax-boundaries.json` y `fixture-ledger.json`: campos
   realmente observados, límites, tamaños y fixtures. No confundir fixture local
   con proveedor remoto ni ACK con recepción humana.

Para cada claim, clasificar por separado:

- Defecto de producto demostrado, con evidencia y contrato que incumple.
- Límite/denegación correctos según el contrato vigente.
- Error de expectativa del tester.
- Problema de fixture, setup o harness.
- Dependencia externa/configuración, como OAuth de Drive.
- No reproducido o información insuficiente.
- Frontera no probada/no autorizada.

Conservar cada claim y resultado original. Añadir adjudicación en un archivo nuevo;
no reescribir los FAIL/SUSPECTED/REVIEW históricos. Identificar duplicados por causa
raíz antes de contar errores.256discrepancias vienen de pruebas negativas y326del
estado esperado frente al observado; esos números por sí solos no prueban defectos.

El producto permanece en el comportamiento de `b34db69`. Consultar su código y los
contratos de `rebuildbotsky.md`; no ejecutar otros planes de Zhana ni investigar NLP.
Los scripts de campaña hacen red/envíos bajo encargo explícito: **no repetirlos por
leer este paquete**. Datos completos propios están bajo `private/stress-20261106/`;
no imprimir credenciales ni importar historias/perfiles. Las correcciones de código
y campañas adicionales se decidirán después del contraste, por encargo del dueño.
