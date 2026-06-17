# Product

## Register

product

## Users

ATLAS sirve a **abogados y profesionales del derecho** que investigan y litigan sobre playas, dominio público marítimo-terrestre y normatividad costera en Colombia. Tres arquetipos principales:

- **El litigante activo.** Lleva un caso ante la jurisdicción contencioso-administrativa y necesita identificar precedentes del Consejo de Estado, líneas jurisprudenciales consolidadas y sentencias de unificación relevantes. Llega con una teoría del caso; busca respaldo doctrinal y fáctico preciso.
- **El asesor corporativo o institucional.** Asesora a entidades territoriales, concesionarios portuarios, operadores turísticos o inmobiliarios sobre el régimen de bienes de uso público y las limitaciones al dominio privado en zonas costeras. Necesita criterios claros y citas verificables para conceptos formales.
- **El investigador o docente.** Académico de derecho administrativo, ambiental o marítimo que mapea la evolución jurisprudencial del Consejo de Estado en materia costera. Prioriza trazabilidad, cobertura del corpus y acceso directo a los textos originales.

Todos leen jurisprudencia profesionalmente. Conocen la terminología técnica — dominio público marítimo-terrestre, playa marítima, INVEMAR, DIMAR, acción de tutela, nulidad y restablecimiento del derecho, sentencia de unificación — y esperan que ATLAS la use con precisión, no que la simplifique.

## Product Purpose

ATLAS recupera y sintetiza jurisprudencia colombiana sobre playas y derecho costero para profesionales del derecho. El corpus son sentencias del Consejo de Estado procesadas mediante un pipeline RAG híbrido. Cada respuesta combina los elementos pertinentes al caso: identificación de la línea jurisprudencial aplicable, extractos textuales de las providencias relevantes, análisis de los criterios de decisión del tribunal y las fuentes verificables con acceso al texto original.

Éxito: el abogado formula una consulta en lenguaje técnico-jurídico, obtiene una respuesta igualmente técnica respaldada en jurisprudencia trazable, y puede citarla directamente en su escrito o concepto sin pasos intermedios de interpretación.

## Brand Personality

Moderna, precisa, confiable. ATLAS combina la sensación de una herramienta de IA contemporánea (minimalismo radical, luz ambiental, interacción fluida) con la rigurosidad que exige el trabajo jurídico profesional. Habla en segunda persona, en el mismo registro técnico que su usuario. La interfaz no compite con la respuesta: la enmarca y le da espacio.

ATLAS no es un sistema de razonamiento autónomo, y lo deja claro. Es un motor de recuperación y síntesis jurisprudencial: preciso, trazable y especializado en derecho costero colombiano.

## Anti-references

- **Legis, SUIN-Juriscol y portales jurídicos tradicionales:** útiles para búsquedas por número de expediente o texto exacto, pero sin capacidad de recuperación semántica ni síntesis jurisprudencial. ATLAS va más allá: entiende la consulta en lenguaje técnico-jurídico y devuelve la línea de precedentes relevante, no una lista de documentos.
- **ChatGPT, Gemini y wrappers genéricos de LLM:** misma plantilla en todas partes, sin identidad, sin contexto de dominio. Si ATLAS se confunde con cualquier asistente genérico, falló.
- **SaaS navy + dorado, "trust badges", azul institucional con serif clásico:** el reflejo de primer orden para "herramienta legal seria". Predecible y aburrido. La versión anterior de ATLAS cayó precisamente aquí.
- **Editorial-tipográfico oscuro (serif grande + dark mode + mucha tipografía):** el reflejo de segundo orden para "herramienta de IA que quiere verse premium". También predecible.
- **Estética "gov.co aburrido":** funcional pero sin alma. ATLAS es un servicio público, pero uno hecho con el mismo cuidado que un producto privado de calidad.

## Design Principles

1. **Hablamos en el idioma del derecho.** Cada respuesta usa la terminología técnica correcta — sin eufemismos, sin simplificaciones. El usuario es un profesional; se le trata como tal.
2. **La respuesta es el producto; todo lo demás es marco.** El chat, las citas, la navegación existen para servir al análisis jurisprudencial. Ningún elemento de UI gana atención por encima de lo que el abogado vino a leer.
3. **Una sola decisión visual fuerte sostiene la identidad.** El glow ambiental bioluminiscente es la firma de ATLAS. Todo lo demás es neutro y disciplinado. No competimos contra nuestra propia firma con decoración adicional.
4. **Las fuentes son el núcleo, no el apéndice.** Cada cita es expandible, cada extracto es legible, cada sentencia es navegable hasta el texto original. El profesional necesita citar fuentes primarias; ATLAS las pone a un click de distancia.
5. **ATLAS es un motor de recuperación, no un oráculo.** El producto es honesto sobre su naturaleza: sintetiza lo que el Consejo de Estado ha dicho, no interpreta lo que debería decir. El criterio jurídico sigue siendo del abogado.

## Accessibility & Inclusion

Sin requisitos formales de WCAG numerados, pero con criterios concretos:

- **Tema claro, oscuro y system** (`prefers-color-scheme`) pensados con igual cuidado. Ninguno es "el bueno" y otro "el toggle de cortesía".
- **`prefers-reduced-motion` respetado globalmente.** El glow ambiental se vuelve estático bajo esa preferencia, las pulsaciones y transiciones desaparecen.
- **Foco visible en todos los elementos interactivos**, con anillo claro tanto en dark como en light.
- **Lenguaje técnico preciso** como requisito de calidad: los términos jurídicos se usan con rigor, no se evitan ni se simplifican.
- **Soporte para teclado completo** en chat, citas expandibles, popovers y navegación.
- **Contraste mínimo AA** verificado en ambos temas, incluyendo texto sobre el glow.
