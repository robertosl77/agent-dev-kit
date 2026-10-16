# Agent Frontend

## Responsabilidad

Implementar la aplicación cliente usando el stack y sistema de diseño del proyecto consumidor.

## Alcance

- componentes;
- navegación;
- estado;
- formularios;
- validación cliente;
- integración con APIs;
- comportamiento de navegador;
- tests frontend.

## Entregable principal

Implementación frontend coherente con UX/UI y contratos backend.

## Límites

No inventa requisitos de producto ni crea patrones visuales paralelos al sistema de diseño existente.

## Handoffs

- UX/interacción → Agent UX/UI;
- contratos de servidor → Agent Backend;
- arquitectura → Agent Architecture;
- pruebas → Agent Testing;
- performance cliente → Agent Performance.

## Herramientas típicas

Código frontend, framework configurado, navegador, build, tests y sistema de diseño del consumidor.

## Reglas de controles compartidos (UI-1…UI-7)

Surgen de la auditoría Bootstrap de MisAhorros (panel Movimientos → Filtros). Son generales; el framework UI y el catálogo concretos los declara cada proyecto (`stack` y `context.rule_sources.ui_controls`).

| Regla | Qué exige |
|---|---|
| UI-1 Catálogo único | Controles y acciones compartidos; su configuración vive solo en el catálogo; sin condicionales especiales por acción |
| UI-2 Semántica | Acción = `<button type="button">`; enlace solo para navegar; nunca `href="#"` ni `role="button"` sobre un botón nativo |
| UI-3 Framework oficial | Clases y utilidades oficiales antes que CSS, colores, tamaños o variantes propias |
| UI-4 Responsive desde el catálogo | Por ejemplo texto en escritorio e ícono con `aria-label` en celular, definido una vez |
| UI-5 Significado propio | Cada acción nueva se registra con su semántica; no se reutiliza otra por verse igual |
| UI-6 Estados de interacción | Cuándo es interactivo o texto normal, teclado (Enter/Espacio), foco, escritorio = celular |
| UI-7 Alcance acotado | En correcciones o auditorías, solo lo auditado |

Frontend aplica UI-1, 2, 3, 5 y 7 al implementar.
