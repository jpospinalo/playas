# Product

## Register

product

## Users

ATLAS sirve a **ciudadanos colombianos sin formación legal** que tienen consultas reales sobre playas, dominio público marítimo-terrestre y normatividad costera. Tres arquetipos principales:

- **El afectado directo.** Le multaron por construir cerca a la playa, lo desalojaron de un predio costero, le prohibieron vender en la arena, le negaron un permiso. Llega con urgencia, a veces ansiedad, casi siempre fuera de horario laboral. Necesita saber qué pasó, si fue legal, y qué puede hacer ahora.
- **El curioso informado.** Periodista cubriendo un caso, estudiante (no necesariamente de derecho), ciudadano interesado en política pública costera. No tiene urgencia; busca entender el marco legal para opinar o contar.
- **El funcionario o líder local.** Alcaldía municipal pequeña, junta de acción comunal, líder gremial de pescadores u hoteleros. No es abogado pero tiene que tomar decisiones con consecuencias legales. Es intermediario entre el sistema jurídico y su comunidad.

Ninguno lee jurisprudencia profesionalmente. Ninguno sabe qué es una "sentencia de unificación" o "dominio público marítimo-terrestre" sin que alguien se lo explique. Todos merecen una respuesta clara.

## Product Purpose

ATLAS traduce la jurisprudencia colombiana sobre playas y derecho costero a respuestas comprensibles para personas sin formación legal. El corpus son sentencias del Consejo de Estado procesadas mediante un pipeline RAG híbrido. Cada respuesta combina cuatro elementos cuando el caso lo amerita: un resumen accesible, una explicación traducida del marco legal, un próximo paso concreto (a quién acudir, qué denunciar, qué documento pedir) y las fuentes verificables que respaldan lo afirmado.

Éxito: el usuario llega con una duda en lenguaje cotidiano, sale entendiendo su situación y sabiendo qué hacer, sin haber tenido que descifrar jerga legal por su cuenta.

## Brand Personality

Moderna, clara, confiable. ATLAS combina la sensación de una herramienta de IA contemporánea (minimalismo radical, luz ambiental, interacción fluida) con la autoridad de un servicio público bien hecho. Habla en segunda persona, sin paternalismo y sin condescendencia. La interfaz no compite con la respuesta: la enmarca y le da espacio.

ATLAS no es un abogado, y lo deja claro. Pero es la mejor primera puerta para alguien que necesita entender qué dice la ley antes de buscar uno.

## Anti-references

- **Legis, SUIN-Juriscol y portales jurídicos tradicionales:** densos, arcaicos, hechos para abogados que ya saben dónde buscar. ATLAS es lo opuesto.
- **ChatGPT, Gemini y wrappers genéricos de LLM:** misma plantilla en todas partes, sin identidad, sin contexto de dominio. Si ATLAS se confunde con cualquier asistente genérico, falló.
- **SaaS navy + dorado, "trust badges", azul institucional con serif clásico:** el reflejo de primer orden para "herramienta legal seria". Predecible y aburrido. La versión anterior de ATLAS cayó precisamente aquí.
- **Editorial-tipográfico oscuro (serif grande + dark mode + mucha tipografía):** el reflejo de segundo orden para "herramienta de IA que quiere verse premium". También predecible.
- **Estética "gov.co aburrido":** funcional pero sin alma. ATLAS es un servicio público, pero uno hecho con el mismo cuidado que un producto privado de calidad.

## Design Principles

1. **Hablamos como una persona, no como un código civil.** Cada palabra que aparece en la interfaz se prueba contra: ¿lo entendería alguien que nunca pisó una facultad de derecho? Si la respuesta es no, se reescribe.
2. **La respuesta es el producto; todo lo demás es marco.** El chat, las citas, la navegación existen para servir al contenido legal traducido. Ningún elemento de UI gana atención por encima de lo que el usuario vino a leer.
3. **Una sola decisión visual fuerte sostiene la identidad.** El glow ambiental bioluminiscente es la firma de ATLAS. Todo lo demás es neutro y disciplinado. No competimos contra nuestra propia firma con decoración adicional.
4. **Las fuentes son respaldo accesible, no muros académicos.** Cada cita es expandible, cada extracto es legible, cada sentencia es navegable. Pero ninguna cita aparece sin que la explicación ya haya hecho su trabajo.
5. **ATLAS no reemplaza un abogado, y se nota.** El producto es honesto sobre sus límites. Cuando una situación requiere acción legal real, ATLAS lo dice y orienta hacia el siguiente paso humano.

## Accessibility & Inclusion

Sin requisitos formales de WCAG numerados, pero con criterios concretos:

- **Tema claro, oscuro y system** (`prefers-color-scheme`) pensados con igual cuidado. Ninguno es "el bueno" y otro "el toggle de cortesía".
- **`prefers-reduced-motion` respetado globalmente.** El glow ambiental se vuelve estático bajo esa preferencia, las pulsaciones y transiciones desaparecen.
- **Foco visible en todos los elementos interactivos**, con anillo claro tanto en dark como en light.
- **Lenguaje accesible** como requisito de inclusión, no solo de tono: los términos jurídicos se definen al primer uso o se evitan.
- **Soporte para teclado completo** en chat, citas expandibles, popovers y navegación.
- **Contraste mínimo AA** verificado en ambos temas, incluyendo texto sobre el glow.
