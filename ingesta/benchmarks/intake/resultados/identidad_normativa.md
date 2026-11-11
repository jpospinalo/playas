# Identidad de normativa (FASE 2)

Medido sobre el bronce de runA (27 PDF de normativa). Esquema `legal-metadata-3`: la identidad de la
propia norma sale solo de su encabezado (línea propia, cabecera SUIN o pie del Gestor Normativo), nunca de
una norma citada. Puerta: normativa exige tipo, número y año con evidencia; entidad emisora y fecha son
recomendados (advertencia). Jurisprudencia conserva la puerta de corporación.

**Pasan 18 de 27** (antes, 16 pasaban la puerta de corporación, que no aplica a normas).
Con los recomendados completos: 7.

| Doc | Puerta | Tipo | Número | Año | Fecha | Entidad emisora | Motivo si falla |
|---|---|---|---|---|---|---|---|
| be8f | pasa | Decreto | 415 | 2017 | — | Presidente de la república |  |
| cc7b | pasa | Decreto | 5058 | 2009 | 2009-12-30 | Presidente de la república |  |
| 2880 | pasa | Decreto | 2811 | 1974 | — | — |  |
| 5f39 | pasa | Decreto | 2106 | 2019 | — | — |  |
| c9b9 | pasa | Decreto | 1875 | 1979 | 1979-08-02 | Presidente de la republica |  |
| 05d5 | falla | — | — | — | — | — | fragmento sin encabezado propio (extracto del Código de Comercio) |
| 0be7 | pasa | Decreto | 4440 | 2008 | 2008-11-25 | Presidente de la república |  |
| cb33 | pasa | Decreto | 1766 | 2013 | — | Presidente de la república |  |
| c8e5 | pasa | Decreto | 1766 | 2013 | 2013-08-16 | Presidente de la república |  |
| d195 | pasa | Decreto | 1504 | 1998 | — | Presidente de la república |  |
| cdf2 | falla | — | — | — | — | — | fragmento sin encabezado propio (extracto desde el Art. 6) |
| 15e7 | falla | — | — | — | — | — | fragmento sin encabezado propio (extracto desde el Art. 29) |
| aeb1 | falla | — | — | — | — | — | fragmento sin encabezado propio |
| 922e | pasa | Decreto | 1436 | 1984 | 1984-06-13 | Presidente de la república |  |
| 3e80 | falla | — | — | — | — | — | fragmento sin encabezado propio (inicia en considerandos) |
| e828 | falla | — | — | — | — | — | número del decreto ilegible por OCR («DECRETO NÚMERO: > +<84») |
| e4a6 | pasa | Decreto | 1600 | 2005 | — | — |  |
| 0fec | falla | — | — | — | — | — | fragmento sin encabezado propio |
| 9c01 | falla | — | — | — | — | Alcalde del distrito turistico | número de decreto manuscrito ilegible por OCR («DECRETO No. (2) J») |
| f508 | pasa | Decreto | 1076 | 2015 | — | — |  |
| 38da | pasa | Decreto | 1074 | 2015 | — | — |  |
| 1cd3 | pasa | Decreto | 1079 | 2015 | — | — |  |
| 404e | pasa | Decreto | 1077 | 2015 | — | — |  |
| 5beb | falla | — | — | — | — | Alcalde mayor de cartagena de indias | encabezado y sello ilegibles por OCR |
| d6b7 | pasa | Decreto | 1431 | 2024 | 2024-10-15 | Alcalde del distrito portuario |  |
| 1ee0 | pasa | Decreto | 474 | 2015 | — | — |  |
| 8351 | pasa | Decreto | 376 | 2015 | 2015-12-04 | Alcalde del distrito turístico |  |

## Revisión manual (10 documentos)

Contrastados con el texto del bronce: be8f, cc7b, c9b9, c8e5, d195, 8351, d6b7, 5f39, e4a6, 1ee0.
Tipo, número y año correctos en 10/10; entidad emisora correcta donde aparece. Un error de fecha
(c9b9 tomaba la fecha del Diario Oficial, 31-08-1979, en vez de la de expedición «(agosto 2)»), corregido
con la fecha corta tras el encabezado y cubierto por test.

## Fallos restantes (razón real, no se relaja la puerta)

- 6 fragmentos de compilaciones sin el encabezado de la propia norma: la identidad no está en el texto.
  Solución propuesta: archivo lateral de metadatos (override con evidencia) o el documento completo.
- 3 escaneados con el número del decreto ilegible por OCR (El Rodadero, Cartagena, UAC): van a revisión.

Nada de esto está validado por abogados.
