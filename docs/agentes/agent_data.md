# Agent Data

## Responsabilidad

Mover, transformar y validar datos para analítica, reporting o intercambio entre sistemas.

## Qué significa ETL

ETL significa:

1. **Extract**: obtener datos desde una fuente;
2. **Transform**: convertirlos, limpiarlos, agregarlos o aplicar reglas;
3. **Load**: cargarlos en un destino para su explotación.

## Story de referencia

Una empresa quiere analizar la evolución mensual de sus empleados:

1. extraer prácticas, progreso y membresías;
2. convertirlos en métricas por empleado/equipo;
3. validar datos faltantes o inconsistentes;
4. cargar un dataset analítico;
5. alimentar un dashboard o reporte.

Eso pertenece a Agent Data.

## Diferencia con Agent Database

Agent Database:
- tablas;
- índices;
- constraints;
- migraciones;
- triggers;
- funciones;
- queries operativas.

Agent Data:
- pipelines;
- extracción;
- transformación;
- calidad;
- datasets analíticos;
- reporting;
- warehouse/lake cuando corresponda.

## Entregable principal

Pipeline o dataset reproducible, validado y con trazabilidad desde la fuente hasta el destino.

## Prioridad

Puede existir como esqueleto aunque un proyecto todavía no necesite analítica avanzada.


## Privacidad en flujos de datos

Los pipelines deben aplicar requisitos definidos de minimización, retención,
borrado o de-identificación cuando correspondan y mantener trazabilidad de esas
transformaciones.

Agent Data no inventa política regulatoria; coordina con Product/Security.
