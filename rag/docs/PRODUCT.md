# Product

## Users

ATLAS sirve a cualquier persona que necesite orientarse en normatividad y jurisprudencia colombiana sobre playas y zonas costeras — no solo a profesionales del derecho. Arquetipos principales:

- **El profesional jurídico.** Abogados litigantes, asesores corporativos o institucionales e investigadores/docentes que necesitan identificar precedentes del Consejo de Estado, normas vigentes (decretos y su articulado) y citas verificables para un caso, un concepto o una investigación.
- **El ciudadano, pescador o miembro de una comunidad costera.** Quiere entender sus derechos de acceso y uso de la playa, qué autoridad es competente, o qué procedimiento seguir ante una restricción, un conflicto de uso o una afectación ambiental — sin formación jurídica previa.
- **El operador de turismo o la empresa con actividad en zona costera.** Necesita conocer los permisos, concesiones, requisitos y sanciones aplicables a su actividad (hospedaje, actividades náuticas, ocupación de playa) sobre bienes de uso público.
- **El funcionario público.** Consulta competencias de autoridades (DIMAR, capitanías de puerto, entes territoriales) y el marco normativo aplicable a un trámite o una actuación administrativa.

Cada consulta puede usar terminología técnica (dominio público marítimo-terrestre, playa marítima, INVEMAR, DIMAR, acción de tutela, concesión, bajamar) o lenguaje cotidiano ("¿puedo pescar aquí?", "¿quién autoriza un chiringuito en la playa?"); ATLAS responde con precisión técnica en ambos casos, sin asumir que quien pregunta ya conoce el vocabulario jurídico.

## Product Purpose

ATLAS recupera y sintetiza normatividad (decretos y su articulado) y jurisprudencia (sentencias del Consejo de Estado) colombianas sobre playas y derecho costero, mediante un pipeline RAG híbrido sobre un corpus de ambos tipos de documento. Cada respuesta depende de la evidencia recuperada para la consulta: identifica las normas o precedentes pertinentes, cita fragmentos de los documentos recuperados y muestra sus metadatos e identificadores de fuente para facilitar su contraste.

Éxito: quien consulta — profesional del derecho o no — obtiene una respuesta trazable a fuentes normativas o jurisprudenciales verificables, con las citas necesarias para contrastarlas. ATLAS apoya la orientación y la investigación; no reemplaza la verificación profesional de un abogado antes de usar la respuesta en un escrito, concepto o actuación con efectos legales.

## Brand Personality

Moderna, precisa, confiable. ATLAS combina la sensación de una herramienta de IA contemporánea (minimalismo radical, luz ambiental, interacción fluida) con la rigurosidad que exige el trabajo jurídico profesional. Habla en segunda persona, en el mismo registro técnico que su usuario. La interfaz no compite con la respuesta: la enmarca y le da espacio.

ATLAS no es un sistema de razonamiento autónomo, y lo deja claro. Es un motor de recuperación y síntesis jurisprudencial: preciso, trazable y especializado en derecho costero colombiano.

## Anti-references

- **Legis, SUIN-Juriscol y portales jurídicos tradicionales:** útiles para búsquedas por número de expediente o texto exacto, pero sin capacidad de recuperación semántica ni síntesis jurisprudencial. ATLAS va más allá: entiende la consulta en lenguaje técnico-jurídico y devuelve la línea de precedentes relevante, no una lista de documentos.
- **ChatGPT, Gemini y wrappers genéricos de LLM:** misma plantilla en todas partes, sin identidad, sin contexto de dominio. Si ATLAS se confunde con cualquier asistente genérico, falló.
- **SaaS navy + dorado, "trust badges", azul institucional con serif clásico:** el reflejo de primer orden para "herramienta legal seria". Predecible y aburrido.
- **Editorial-tipográfico oscuro (serif grande + dark mode + mucha tipografía):** el reflejo de segundo orden para "herramienta de IA que quiere verse premium". También predecible.
- **Estética "gov.co aburrido":** funcional pero sin alma. ATLAS es un servicio público, pero uno hecho con el mismo cuidado que un producto privado de calidad.

## Design Principles

1. **Hablamos en el idioma del derecho, sin exigirlo de quien pregunta.** Cada respuesta usa la terminología técnica correcta — sin eufemismos, sin simplificaciones que la desvirtúen — tanto si la consulta llegó en lenguaje técnico como si llegó en lenguaje cotidiano.
2. **La respuesta es el producto; todo lo demás es marco.** El chat, las citas, la navegación existen para servir a la orientación normativa y jurisprudencial. Ningún elemento de UI gana atención por encima de lo que la persona vino a leer.
3. **Una sola decisión visual fuerte sostiene la identidad.** El glow ambiental bioluminiscente es la firma de ATLAS. Todo lo demás es neutro y disciplinado. No competimos contra nuestra propia firma con decoración adicional.
4. **Las fuentes son el núcleo, no el apéndice.** Cada cita es expandible, cada extracto es legible, cada fuente expone su metadata e identificadores de origen. Quien consulta necesita poder contrastar la fuente primaria con la evidencia que ATLAS ya le muestra.
5. **ATLAS es un motor de recuperación, no un oráculo.** El producto es honesto sobre su naturaleza: sintetiza lo que la norma o el Consejo de Estado han dicho, no interpreta lo que deberían decir. El criterio de aplicación a un caso concreto sigue siendo de un profesional del derecho.

## Accessibility & Inclusion

Sin requisitos formales de WCAG numerados, pero con criterios concretos:

- **Tema claro, oscuro y system** (`prefers-color-scheme`) pensados con igual cuidado. Ninguno es "el bueno" y otro "el toggle de cortesía".
- **`prefers-reduced-motion` respetado globalmente.** El glow ambiental se vuelve estático bajo esa preferencia, las pulsaciones y transiciones desaparecen.
- **Lenguaje técnico preciso** como requisito de calidad: los términos jurídicos se usan con rigor, no se evitan ni se simplifican.
- La interfaz incorpora controles semánticos, navegación por teclado, foco
  visible y respeto por `prefers-reduced-motion`. No se declara conformidad con
  un nivel WCAG específico sin una auditoría formal.
