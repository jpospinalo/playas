"""Portable selection contracts with deduplicated, readable document fixtures.

The 37 preregistered external contracts preserve their original bodies, metadata,
questions and expected selections. Gold-derived examples and invented plans are
labelled separately: these tests do not demonstrate generated-answer quality or
positive generalization to other real norms. Mixed-role history is synthetic,
not a replay of the earlier browser conversation or a warm checkpoint.

Only fixture data is embedded here; no corpus, personal paths, clients, models,
external helpers or runtime evidence files are read. Provenance checks below use
independent copies of the snapshot and candidate objects.
"""

from __future__ import annotations

import copy
import socket
from typing import Any

import pytest
from langchain_core.documents import Document

# Full metadata and bodies are retained; repeated rows are represented once.
_DOCUMENT_ROWS: tuple[dict[str, Any], ...] = (
    {
        "id": "AP Felipe José Campo Fernández VS Corpamag y otros_s3_c30",
        "text": "127. Por medio de la Resolución No. 00751 del 30 de junio de 2017  la ANLA "
        "estableció el Plan de Manejo Ambiental a cargo de PROMIGAS S.A. E.S.P. para el "
        "proyecto Sistema de Gasoductos de la Costa Atlántica , con una extensión "
        "aproximada  de 990  km  entre La Guajira y Sucre, comprendiendo  varios  "
        "departamentos  y  municipios,  entre  ellos  Ciénaga, Puebloviejo y Sitionuevo en "
        "el Magdalena. La resolución integra obligaciones  ambientales  de  actos  previos,  "
        "salvo  aquellas  expresamente excluidas,  y  fija  compromisos  en  materia  de  "
        "uso  de  agua,  manejo  de residuos domésticos, industriales y peligrosos, "
        "disposición de escombros y materiales de construcción, así como la obligación de "
        "allegar certificados, permisos y licencias de terceros autorizados.",
        "metadata": {
            "Archivo": "AP Felipe José Campo Fernández VS Corpamag y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-03",
            "Partes procesales": "Actor: Felipe José Campo Fernández. Demandados: "
            "Departamento del Magdalena y municipio de Ciénaga. "
            "Vinculados: DIMAR, CORPAMAG, UNGRD, ANLA, INVEMAR, "
            "Ministerio de Ambiente, entre otros.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "470012333000202000687-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Erosión costera en playas del municipio de Ciénaga y "
            "responsabilidad institucional frente al riesgo ambiental y "
            "territorial.",
            "chunk_id": "AP Felipe José Campo Fernández VS Corpamag y otros_s3_c30",
            "chunk_index": 30,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "ANLA"}, {"type": '
            '"ORGANIZATION", "text": "PROMIGAS S.A. E.S.P."}, {"type": "DATE", '
            '"text": "junio de 2017"}, {"type": "LOCATION", "text": "La '
            'Guajira"}, {"type": "LOCATION", "text": "Sucre"}, {"type": '
            '"LOCATION", "text": "Ciénaga"}, {"type": "LOCATION", "text": '
            '"Puebloviejo"}, {"type": "LOCATION", "text": "Sitionuevo"}, '
            '{"type": "LOCATION", "text": "Magdalena"}]',
            "keywords": '["ANLA", "PROMIGAS", "gasoducto", "ambiental", "La Guajira", '
            '"Sucre", "manejo ambiental", "resolución"]',
            "keywords_str": "ANLA, PROMIGAS, gasoducto, ambiental, La Guajira, Sucre, "
            "manejo ambiental, resolución",
            "section_heading": "4. CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP Felipe José Campo Fernández VS Corpamag y otros.md",
            "summary": "La ANLA asignó a PROMIGAS S.A. E.S.P. el Plan de Manejo Ambiental "
            "para el Sistema de Gasoductos de la Costa Atlántica (990 km) entre "
            "La Guajira y Sucre en 2017.",
            "title": "AP Felipe José Campo Fernández VS Corpamag y otros",
            "total_chunks_in_section": 111,
        },
    },
    {
        "id": "AP Felipe José Campo Fernández VS Corpamag y otros_s3_c105",
        "text": "194. El departamento del Magdalena deberá coadyuvar técnica y financieramente  a  "
        "dichas  iniciativas  y,  en  coordinación  con  la  Unidad Nacional para la Gestión "
        "del Riesgo de Desastres y el Ministerio de Ambiente y Desarrollo Sostenible, "
        "formular un plan integral que articule los estudios existentes, los lineamientos "
        "del Plan Maestro de Erosión Costera (artículo 323 de la Ley 1955 de 2019) y los "
        "instrumentos de ordenación y manejo integrado  de  las  Unidades  Ambientales  "
        "Costeras  (POMIUAC).  Dicho  plan deberá  contener  metas  verificables  y  un  "
        "cronograma  estricto  de  corto, mediano y largo plazo.",
        "metadata": {
            "Archivo": "AP Felipe José Campo Fernández VS Corpamag y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-03",
            "Partes procesales": "Actor: Felipe José Campo Fernández. Demandados: "
            "Departamento del Magdalena y municipio de Ciénaga. "
            "Vinculados: DIMAR, CORPAMAG, UNGRD, ANLA, INVEMAR, "
            "Ministerio de Ambiente, entre otros.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "470012333000202000687-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Erosión costera en playas del municipio de Ciénaga y "
            "responsabilidad institucional frente al riesgo ambiental y "
            "territorial.",
            "chunk_id": "AP Felipe José Campo Fernández VS Corpamag y otros_s3_c105",
            "chunk_index": 105,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "LOCATION", "text": "Magdalena"}, {"type": '
            '"ORGANIZATION", "text": "Unidad Nacional para la Gestión del '
            'Riesgo de Desastres"}, {"type": "ORGANIZATION", "text": '
            '"Ministerio de Ambiente y Desarrollo Sostenible"}, {"type": "LAW", '
            '"text": "Ley 1955 de 2019"}, {"type": "MISC", "text": "Plan '
            'Maestro de Erosión Costera"}, {"type": "MISC", "text": "POMIUAC"}]',
            "keywords": '["Magdalena", "erosión costera", "plan integral", "UNGRD", "riesgo '
            'de desastres", "ambiente", "Ley 1955", "POMIUAC"]',
            "keywords_str": "Magdalena, erosión costera, plan integral, UNGRD, riesgo de "
            "desastres, ambiente, Ley 1955, POMIUAC",
            "section_heading": "4. CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP Felipe José Campo Fernández VS Corpamag y otros.md",
            "summary": "El Magdalena debe colaborar técnica y financieramente en "
            "iniciativas de gestión del riesgo y formular un plan integral para "
            "la erosión costera, coordinado con la UNGRD y el Ministerio de "
            "Ambiente.",
            "title": "AP Felipe José Campo Fernández VS Corpamag y otros",
            "total_chunks_in_section": 111,
        },
    },
    {
        "id": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS_s3_c210",
        "text": "Asimismo, a través de Resolución No. 313 del 9 de noviembre de 2011 el DADMA aprobó "
        "el Plan de Manejo Ambiental a la precitada sociedad para la construcción de la EDA "
        "Estación de Servicio de Combustible, estableciéndose en cabeza de la  sociedad  "
        "INVERSIONES  MARINA TURÍSTICA  S.A.  la  obligación  de  presentar  estudio  "
        "hidrobiológico  en  el período  de  funcionamiento;  crear  una  guía  para  el  "
        "monitoreo  de  fugas  y derrames de combustibles durante la operación normal, entre "
        "otras acciones de  seguimiento;  y  precisándose  que,  en  caso  de  ocasionarse  "
        "perjuicios ambientales  y/o  sociales  en  la  ejecución  del  proyecto,  por  "
        "parte  de  los contratistas de la Marina Internacional de Santa Marta, responderán "
        "por los daños y perjuicios ocasionados y la autoridad ambiental aplicaría las "
        "medidas correspondientes. 60",
        "metadata": {
            "Archivo": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS.pdf",
            "CATEGORIA ANALISIS": "No Aplica",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "Adonay Ferrari Padilla",
            "Nº": "SM-01",
            "Partes procesales": "Accionante: Procuraduría General de la Nación – "
            "Procuraduría Delegada para Asuntos Ambientales. "
            "Demandados: Nación – ANLA, Ministerio de Defensa, DIMAR, "
            "CORPAMAG, Distrito de Santa Marta, DADSA, Proactiva Santa "
            "Marta S.A. E.S.P.",
            "RELACIÓN PLAYAS": "Indirecta",
            "Radicado": "47-001-2333-000-2018-00368-00",
            "TEMÁTICA": "Ambiental",
            "Tema principal": "Protección del ambiente marino en la Bahía de Santa Marta "
            "frente a vertimientos contaminantes y omisiones "
            "institucionales.",
            "chunk_id": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS_s3_c210",
            "chunk_index": 210,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "DADMA"}, {"type": '
            '"ORGANIZATION", "text": "INVERSIONES MARINA TURÍSTICA S.A."}, '
            '{"type": "LOCATION", "text": "Santa Marta"}, {"type": "DATE", '
            '"text": "noviembre de 2011"}, {"type": "LAW", "text": "Resolución '
            'No. 313"}]',
            "keywords": '["DADMA", "Plan de Manejo Ambiental", "estación de servicio", '
            '"INVERSIONES MARINA TURÍSTICA S.A.", "estudio hidrobiológico", '
            '"fugas de combustibles", "Santa Marta", "perjuicios ambientales"]',
            "keywords_str": "DADMA, Plan de Manejo Ambiental, estación de servicio, "
            "INVERSIONES MARINA TURÍSTICA S.A., estudio hidrobiológico, "
            "fugas de combustibles, Santa Marta, perjuicios ambientales",
            "section_heading": "4. CONSIDERACIONES DEL TRIBUNAL.",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS.md",
            "summary": "La Resolución 313 de 2011 aprobó el Plan de Manejo Ambiental para "
            "la construcción de una estación de servicio, exigiendo estudios y "
            "medidas de seguimiento ambiental a INVERSIONES MARINA TURÍSTICA "
            "S.A.",
            "title": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS",
            "total_chunks_in_section": 264,
        },
    },
    {
        "id": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS_s3_c216",
        "text": ". Entonces digamos que, pues durante el tiempo que estuve allí, si entre relación "
        "a  vertimiento  puedo  dar  fe  de. Preguntado señor  Magistrado: ¿Y entonces,  "
        "¿dónde  se  vierten  esas  aguas  por  parte  de  la  marina? Responde el "
        "interrogado Bueno, como le decía, las aguas domésticas tienen un sistema de "
        "colección y llega hasta el alcantarillado público, pues bajo la en estos momentos, "
        "infiero que bajo el  mar. Y las aguas que se generan por las actividades del taller "
        "se",
        "metadata": {
            "Archivo": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS.pdf",
            "CATEGORIA ANALISIS": "No Aplica",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "Adonay Ferrari Padilla",
            "Nº": "SM-01",
            "Partes procesales": "Accionante: Procuraduría General de la Nación – "
            "Procuraduría Delegada para Asuntos Ambientales. "
            "Demandados: Nación – ANLA, Ministerio de Defensa, DIMAR, "
            "CORPAMAG, Distrito de Santa Marta, DADSA, Proactiva Santa "
            "Marta S.A. E.S.P.",
            "RELACIÓN PLAYAS": "Indirecta",
            "Radicado": "47-001-2333-000-2018-00368-00",
            "TEMÁTICA": "Ambiental",
            "Tema principal": "Protección del ambiente marino en la Bahía de Santa Marta "
            "frente a vertimientos contaminantes y omisiones "
            "institucionales.",
            "chunk_id": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS_s3_c216",
            "chunk_index": 216,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "marina"}, {"type": "PERSON", '
            '"text": "Magistrado"}]',
            "keywords": '["aguas residuales", "alcantarillado", "marina", "vertimiento", '
            '"taller", "aguas domésticas", "tribunal"]',
            "keywords_str": "aguas residuales, alcantarillado, marina, vertimiento, taller, "
            "aguas domésticas, tribunal",
            "section_heading": "4. CONSIDERACIONES DEL TRIBUNAL.",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS.md",
            "summary": "El fragmento describe el destino de las aguas residuales de la "
            "marina, distinguiendo entre aguas domésticas (alcantarillado "
            "público) y aguas del taller, que parecen desembocar en el mar.",
            "title": "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS",
            "total_chunks_in_section": 264,
        },
    },
    {
        "id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c228",
        "text": "14. Planes Integrales de Gestión Del Cambio Climático Territoriales. Los Planes "
        "Integrales de Gestión del Cambio Climático Territoriales (PIGCCT) son los "
        "instrumentos a través de los cuales las entidades territoriales y autoridades "
        "ambientales regionales identifican, evalúan, priorizan, y definen medidas y "
        "acciones de adaptación y de mitigación de emisiones de gases efecto invernadero, "
        'para ser implementados en el territorio para el cual han sido formulados".\n'
        "- iii) El Plan de Ordenación y Manejo Integrado de las Unidades Ambientales "
        'Costeras (POMIUAC), consagrado en el artículo 5º del Decreto 1120 de 2013, "por el '
        "cual se reglamentan las Unidades Ambientales Costeras (UAC) y las comisiones "
        "conjuntas, se establecen las reglas de procedimiento y criterios para reglamentar "
        "la restricción de ciertas actividades en pastos marinos, y se dictan otras "
        'disposiciones.", que dispone:',
        "metadata": {
            "Archivo": "AP Rodrigo Martínez Silva VS Minambiente y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-06",
            "Partes procesales": "Actores: Rodrigo Martínez Silva y Yulín Yasira Serbousse "
            "Castro. Demandados: Nación – Ministerio de Ambiente, "
            "Ministerio de Defensa, DIMAR, Distrito de Santa Marta, "
            "DADSA, CORPAMAG.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "47-001-2333-000-2016-00482-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Acción popular por erosión costera y desaparición de la "
            "playa Salguero en Santa Marta.",
            "chunk_id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c228",
            "chunk_index": 228,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "entidades territoriales"}, '
            '{"type": "ORGANIZATION", "text": "autoridades ambientales '
            'regionales"}, {"type": "OTHER", "text": "PIGCCT"}, {"type": '
            '"OTHER", "text": "POMIUAC"}, {"type": "OTHER", "text": "Unidades '
            'Ambientales Costeras (UAC)"}, {"type": "OTHER", "text": "Decreto '
            '1120 de 2013"}]',
            "keywords": '["Planes Integrales de Gestión del Cambio Climático", "PIGCCT", '
            '"adaptación", "mitigación de emisiones", "gases efecto '
            'invernadero", "gestión territorial", "Plan de Ordenación y Manejo '
            'Integrado", "Unidades Ambientales Costeras", "Decreto 1120 de '
            '2013", "POMIUAC"]',
            "keywords_str": "Planes Integrales de Gestión del Cambio Climático, PIGCCT, "
            "adaptación, mitigación de emisiones, gases efecto invernadero, "
            "gestión territorial, Plan de Ordenación y Manejo Integrado, "
            "Unidades Ambientales Costeras, Decreto 1120 de 2013, POMIUAC",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP Rodrigo Martínez Silva VS Minambiente y otros.md",
            "summary": "El chunk describe los PIGCCT como instrumentos para que entidades "
            "territoriales y autoridades ambientales definan medidas de "
            "adaptación y mitigación frente al cambio climático en su "
            "territorio. También menciona el POMIUAC del Decreto 1120 de 2013 "
            "relacionado con unidades ambientales costeras.",
            "title": "AP Rodrigo Martínez Silva VS Minambiente y otros",
            "total_chunks_in_section": 251,
        },
    },
    {
        "id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c229",
        "text": '"Artículo 5. Plan de Ordenación y Manejo Integrado de las Unidades Ambientales '
        "Costeras (Pomiuac). Es el instrumento de Radicación número: "
        "47-001-2333-000-2016-0482-00 Actor: Rodrigo Martinez Silva y otro planificación "
        "mediante el cual la Comisión Conjunta o la autoridad ambiental competente, según el "
        "caso, definen y orienta la ordenación y manejo ambiental de las unidades "
        "ambientales costeras.\n"
        "\n"
        "El Pomiuac se constituye en norma de superior jerarquía y determinante ambiental "
        "para la elaboración y adopción de los planes de ordenamiento territorial, de "
        "conformidad con lo dispuesto en el artículo 10 de la Ley 388 de 1997 y orienta la "
        'planeación de los demás sectores en la zona costera".',
        "metadata": {
            "Archivo": "AP Rodrigo Martínez Silva VS Minambiente y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-06",
            "Partes procesales": "Actores: Rodrigo Martínez Silva y Yulín Yasira Serbousse "
            "Castro. Demandados: Nación – Ministerio de Ambiente, "
            "Ministerio de Defensa, DIMAR, Distrito de Santa Marta, "
            "DADSA, CORPAMAG.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "47-001-2333-000-2016-00482-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Acción popular por erosión costera y desaparición de la "
            "playa Salguero en Santa Marta.",
            "chunk_id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c229",
            "chunk_index": 229,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "PERSON", "text": "Rodrigo Martinez Silva"}, {"type": '
            '"ORGANIZATION", "text": "Comisión Conjunta"}, {"type": '
            '"ORGANIZATION", "text": "autoridad ambiental competente"}, '
            '{"type": "DATE", "text": "2016"}, {"type": "ORGANIZATION", "text": '
            '"Minambiente"}, {"type": "OTHER", "text": "Ley 388 de 1997"}, '
            '{"type": "OTHER", "text": "Radicación '
            '47-001-2333-000-2016-0482-00"}, {"type": "OTHER", "text": '
            '"Artículo 5"}, {"type": "OTHER", "text": "Artículo 10"}]',
            "keywords": '["POMIUAC", "plan de ordenación", "manejo integrado", "unidades '
            'ambientales costeras", "Comisión Conjunta", "autoridad ambiental '
            'competente", "norma de superior jerarquía", "Ley 388 de 1997", '
            '"ordenamiento territorial", "planeación sectorial costera"]',
            "keywords_str": "POMIUAC, plan de ordenación, manejo integrado, unidades "
            "ambientales costeras, Comisión Conjunta, autoridad ambiental "
            "competente, norma de superior jerarquía, Ley 388 de 1997, "
            "ordenamiento territorial, planeación sectorial costera",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP Rodrigo Martínez Silva VS Minambiente y otros.md",
            "summary": "El chunk describe el Plan de Ordenación y Manejo Integrado de las "
            "Unidades Ambientales Costeras (POMIUAC) como instrumento "
            "determinante de la autoridad ambiental para orientar la ordenación "
            "y manejo costero, con jerarquía superior según la Ley 388 de 1997.",
            "title": "AP Rodrigo Martínez Silva VS Minambiente y otros",
            "total_chunks_in_section": 251,
        },
    },
    {
        "id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c249",
        "text": 'descentralizadas, fomentando la inclusión del privado". (Negrillas de la Sala) '
        "sector\n"
        "\n"
        "74. En desarrolio de las mencionadas disposiciones, el Gobierno nacional expidió el "
        'Decreto 1120 de 31 de mayo de 2013, "por el cual se reglamentan las Unidades '
        'Ambientales Costeras (UAC) (...) y se dictan otras disposiciones".\n'
        "\n"
        "El artículo 5º de la norma ibidem define el Plan de Ordenación y Manejo Integrado "
        'de las Unidades Ambientales Costeras (POMIUAC) como "el instrumento de '
        "planificación mediante el cual la Comisión Conjunta o la autoridad ambiental "
        "competente, según el caso, definen y orienta la ordenación y manejo ambiental de "
        'las unidades ambientales costeras".\n'
        "\n"
        "En cuanto a la adopción del mencionado instrumento, de conformidad con lo dispuesto "
        "en el articulo 207 de la Ley 1450 de 2011 y en los artículos y 40 del Decreto Ley "
        "3570, el Decreto 1120, en su artículo 80, prevé lo siguiente:",
        "metadata": {
            "Archivo": "AP Rodrigo Martínez Silva VS Minambiente y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-06",
            "Partes procesales": "Actores: Rodrigo Martínez Silva y Yulín Yasira Serbousse "
            "Castro. Demandados: Nación – Ministerio de Ambiente, "
            "Ministerio de Defensa, DIMAR, Distrito de Santa Marta, "
            "DADSA, CORPAMAG.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "47-001-2333-000-2016-00482-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Acción popular por erosión costera y desaparición de la "
            "playa Salguero en Santa Marta.",
            "chunk_id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c249",
            "chunk_index": 249,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "DATE", "text": "mayo de 2013"}, {"type": '
            '"ORGANIZATION", "text": "Gobierno nacional"}, {"type": '
            '"ORGANIZATION", "text": "Comisión Conjunta"}, {"type": '
            '"ORGANIZATION", "text": "autoridad ambiental competente"}, '
            '{"type": "OTHER", "text": "Ley 1450 de 2011"}, {"type": '
            '"ORGANIZATION", "text": "Decreto Ley 3570"}, {"type": "OTHER", '
            '"text": "Decreto 1120"}, {"type": "OTHER", "text": "Unidades '
            'Ambientales Costeras (UAC)"}]',
            "keywords": '["Decreto 1120 de 2013", "Unidades Ambientales Costeras UAC", '
            '"POMIUAC", "Plan de Ordenación y Manejo Integrado", "Comisión '
            'Conjunta", "Ley 1450 de 2011", "Decreto Ley 3570", "autoridad '
            'ambiental competente"]',
            "keywords_str": "Decreto 1120 de 2013, Unidades Ambientales Costeras UAC, "
            "POMIUAC, Plan de Ordenación y Manejo Integrado, Comisión "
            "Conjunta, Ley 1450 de 2011, Decreto Ley 3570, autoridad "
            "ambiental competente",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP Rodrigo Martínez Silva VS Minambiente y otros.md",
            "summary": "El chunk describe el Decreto 1120 de 2013 que reglamenta las "
            "Unidades Ambientales Costeras (UAC) y define el POMIUAC como "
            "instrumento de planificación para ordenar y manejar ambientalmente "
            "dichas unidades, según competencias de la Comisión Conjunta o "
            "autoridad ambiental.",
            "title": "AP Rodrigo Martínez Silva VS Minambiente y otros",
            "total_chunks_in_section": 251,
        },
    },
    {
        "id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c251",
        "text": "Parágrafo 2°. La modificación del Pomiuac se sujetará al procedimiento previsto "
        "para las fases de caracterización y diagnóstico, prospectiva y zonificación y "
        'formulación y adopción del Plan".". Finalmente, es de mencionar que el MADS, '
        'mediante Resolución 0768 de 17 de abril de 2017, adoptó "la Guía Técnica para la '
        "Ordenación y Manejo Integrado de la Zona Costera. Este insumo básico permite "
        'clasificar las zonas costeras y agotar las distintas fases del POMIUAC?"\n'
        "\n"
        "- (Negrillas del original).\n"
        "\n"
        '91 Ibid., "Artículo 2.2.4.2.1.1. Tipos de zonas costeras. La zona costera se '
        "clasifica en: [...]. Los demás criterios fijados en la Guía Técnica para la "
        "Ordenación y Manejo Integrado de la Zona Costera que adoptará el Ministerio de "
        'Ambiente y Desarrollo Sostenible. [..]".',
        "metadata": {
            "Archivo": "AP Rodrigo Martínez Silva VS Minambiente y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-06",
            "Partes procesales": "Actores: Rodrigo Martínez Silva y Yulín Yasira Serbousse "
            "Castro. Demandados: Nación – Ministerio de Ambiente, "
            "Ministerio de Defensa, DIMAR, Distrito de Santa Marta, "
            "DADSA, CORPAMAG.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "47-001-2333-000-2016-00482-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Acción popular por erosión costera y desaparición de la "
            "playa Salguero en Santa Marta.",
            "chunk_id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s3_c251",
            "chunk_index": 251,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "MADS"}, {"type": '
            '"ORGANIZATION", "text": "Ministerio de Ambiente y Desarrollo '
            'Sostenible"}, {"type": "ORGANIZATION", "text": "Minambiente"}, '
            '{"type": "DATE", "text": "abril de 2017"}, {"type": "OTHER", '
            '"text": "Resolución 0768 de abril de 2017"}, {"type": "OTHER", '
            '"text": "POMIUAC"}, {"type": "OTHER", "text": "Guía Técnica para '
            'la Ordenación y Manejo Integrado de la Zona Costera"}, {"type": '
            '"OTHER", "text": "Artículo 2.2.4.2.1.1"}]',
            "keywords": '["modificación POMIUAC", "fases de caracterización y diagnóstico", '
            '"zonificación costera", "guía técnica zona costera", "MADS", '
            '"Resolución 0768 de 2017", "ordenación y manejo integrado", '
            '"clasificación de zonas costeras"]',
            "keywords_str": "modificación POMIUAC, fases de caracterización y diagnóstico, "
            "zonificación costera, guía técnica zona costera, MADS, "
            "Resolución 0768 de 2017, ordenación y manejo integrado, "
            "clasificación de zonas costeras",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "AP Rodrigo Martínez Silva VS Minambiente y otros.md",
            "summary": "El chunk indica que la modificación del POMIUAC debe seguir fases "
            "de caracterización, diagnóstico, prospectiva, zonificación y "
            "formulación. Además menciona que el MADS adoptó una guía técnica "
            "para ordenar y manejar la zona costera, que soporta la "
            "clasificación de zonas.",
            "title": "AP Rodrigo Martínez Silva VS Minambiente y otros",
            "total_chunks_in_section": 251,
        },
    },
    {
        "id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s4_c8",
        "text": "Integrales de Gestión del Cambio Climático Sectoriales y Territoriales y POMIUAC.\n"
        "\n"
        "La definición y adopción del Plan Maestro de Erosión Costera para Playa Salguero, "
        "deberá realizarse en un plazo de meses a partir de la ejecutoria de la sentencia, "
        "dentro de los términos específicos que para el efecto determine el comité de "
        "verificación, a efecto de que las entidades vinculadas puedan comprometer sus "
        "recursos y adaptar sus planes, programas y proyectos para la prevención, control y "
        "manejo de los efectos de dicho fenómeno.\n"
        "\n"
        "SEXTO. ORDENAR la integración de un Comité para la verificación del cumplimiento de "
        "la sentencia, el cual estará integrado por este Tribunal a través de la magistrada "
        "ponente, quien lo presidirá, la parte demandante, la Procuraduría Delegada ante "
        "esta Corporación, la Procuraduría Agraria y Ambiental del Magdalena, CORPAMAG, "
        "DIMAR, la Alcaldesa Distrital de Santa Marta, el Gobernador del Departamento del "
        "Magdalena, la Curaduría Urbana y la Defensoría del Pueblo.",
        "metadata": {
            "Archivo": "AP Rodrigo Martínez Silva VS Minambiente y otros.pdf",
            "Corporación": "Tribunal Administrativo del Magdalena",
            "Magistrado ponente": "María Victoria Quiñones Triana",
            "Nº": "SM-06",
            "Partes procesales": "Actores: Rodrigo Martínez Silva y Yulín Yasira Serbousse "
            "Castro. Demandados: Nación – Ministerio de Ambiente, "
            "Ministerio de Defensa, DIMAR, Distrito de Santa Marta, "
            "DADSA, CORPAMAG.",
            "RELACIÓN PLAYAS": "Directa",
            "Radicado": "47-001-2333-000-2016-00482-00",
            "TEMÁTICA": "Gestión del riesgo",
            "Tema principal": "Acción popular por erosión costera y desaparición de la "
            "playa Salguero en Santa Marta.",
            "chunk_id": "AP Rodrigo Martínez Silva VS Minambiente y otros_s4_c8",
            "chunk_index": 8,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "LOCATION", "text": "Playa Salguero"}, {"type": '
            '"LOCATION", "text": "Santa Marta"}, {"type": "LOCATION", "text": '
            '"Departamento del Magdalena"}, {"type": "ORGANIZATION", "text": '
            '"CORPAMAG"}, {"type": "ORGANIZATION", "text": "DIMAR"}, {"type": '
            '"ORGANIZATION", "text": "Procuraduría Delegada ante esta '
            'Corporación"}, {"type": "ORGANIZATION", "text": "Procuraduría '
            'Agraria y Ambiental del Magdalena"}, {"type": "PERSON", "text": '
            '"la Alcaldesa Distrital de Santa Marta"}, {"type": "PERSON", '
            '"text": "el Gobernador del Departamento del Magdalena"}, {"type": '
            '"ORGANIZATION", "text": "Curaduría Urbana"}, {"type": '
            '"ORGANIZATION", "text": "Defensoría del Pueblo"}]',
            "keywords": '["gestión del cambio climático", "plan maestro de erosión '
            'costera", "Playa Salguero", "comité de verificación", "ejecutoria '
            'de la sentencia", "Santa Marta", "CORPAMAG", "DIMAR", '
            '"Procuraduría Agraria y Ambiental del Magdalena"]',
            "keywords_str": "gestión del cambio climático, plan maestro de erosión costera, "
            "Playa Salguero, comité de verificación, ejecutoria de la "
            "sentencia, Santa Marta, CORPAMAG, DIMAR, Procuraduría Agraria "
            "y Ambiental del Magdalena",
            "section_heading": "FALLA",
            "section_index": 4,
            "section_name": "Decisión",
            "source": "AP Rodrigo Martínez Silva VS Minambiente y otros.md",
            "summary": "Se ordena integrar un comité de verificación del cumplimiento de "
            "una sentencia y se define que el Plan Maestro de Erosión Costera "
            "para Playa Salguero debe adoptarse en meses tras la ejecutoria, con "
            "ajustes por entidades vinculadas.",
            "title": "AP Rodrigo Martínez Silva VS Minambiente y otros",
            "total_chunks_in_section": 18,
        },
    },
    {
        "id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c59",
        "text": "14. Planes Integrales de Gestión Del Cambio Climático Territoriales .  Los Planes "
        "Integrales de Gestión del Cambio Climático Territoriales (PIGCCT) son los "
        "instrumentos a través de los cuales las entidades territoriales y autoridades "
        "ambientales  regionales  identifican,  evalúan,  priorizan,  y  definen  medidas  y "
        "acciones  de  adaptación  y  de  mitigación  de  emisiones  de  gases  efecto "
        "invernadero,  para  ser  implementados  en  el  territorio  para  el  cual  han  "
        "sido formulados.'\n"
        "\n"
        "- iii. El  Plan  de  Ordenación  y  Manejo  Integrado  de  las  Unidades  "
        "Ambientales Costeras (POMIUAC), consagrado en el artículo 5º del Decreto 1120 de "
        "2013, ' por el cual se reglamentan las Unidades Ambientales Costeras (UAC) y las "
        "comisiones conjuntas, se establecen las reglas de procedimiento y criterios para "
        "reglamentar la restricción de  ciertas actividades en  pastos  marinos,  y  se  "
        "dictan  otras disposiciones. ', el cual es del siguiente tenor:",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c59",
            "chunk_index": 148,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "otro", "text": "Planes Integrales de Gestión del Cambio '
            'Climático Territoriales (PIGCCT)"}, {"type": "otro", "text": "Plan '
            "de Ordenación y Manejo Integrado de las Unidades Ambientales "
            'Costeras (POMIUAC)"}, {"type": "OTHER", "text": "Decreto 1120 de '
            '2013"}, {"type": "otro", "text": "Unidades Ambientales Costeras '
            '(UAC)"}, {"type": "otro", "text": "comisiones conjuntas"}, '
            '{"type": "otro", "text": "pastos marinos"}]',
            "keywords": '["Planes Integrales de Gestión del Cambio Climático", "PIGCCT", '
            '"adaptación", "mitigación de emisiones", "gases efecto '
            'invernadero", "Ordenación y Manejo Integrado", "Unidades '
            'Ambientales Costeras", "POMIUAC", "Decreto 1120 de 2013", "pastos '
            'marinos"]',
            "keywords_str": "Planes Integrales de Gestión del Cambio Climático, PIGCCT, "
            "adaptación, mitigación de emisiones, gases efecto invernadero, "
            "Ordenación y Manejo Integrado, Unidades Ambientales Costeras, "
            "POMIUAC, Decreto 1120 de 2013, pastos marinos",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.md",
            "summary": "El fragmento describe los PIGCCT como instrumentos para que "
            "entidades territoriales y autoridades ambientales definan medidas "
            "de adaptación y mitigación frente al cambio climático, y menciona "
            "el POMIUAC regulado por el Decreto 1120 de 2013 para la gestión "
            "integrada costera.",
            "title": "CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c60",
        "text": "' Artículo  5. Plan  de  Ordenación  y  Manejo  Integrado  de  las  Unidades "
        "Ambientales Costeras (Pomiuac). Es el instrumento de planificación mediante el cual "
        "la Comisión Conjunta o la autoridad ambiental competente, según  el  caso,  "
        "definen  y  orienta  la  ordenación  y  manejo  ambiental  de  las unidades "
        "ambientales costeras.\n"
        "\n"
        "El  Pomiuac  se  constituye  en  norma  de  superior  jerarquía  y  determinante "
        "ambiental  para  la  elaboración  y  adopción  de  los  planes  de  ordenamiento "
        "territorial, de conformidad con lo dispuesto en el artículo 10 de la Ley 388 de "
        "1997 y orienta la planeación de los demás sectores en la zona costera.'",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c60",
            "chunk_index": 149,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "MISC", "text": "Plan de Ordenación y Manejo Integrado '
            'de las Unidades Ambientales Costeras (POMIUAC)"}, {"type": '
            '"ORGANIZATION", "text": "Comisión Conjunta"}, {"type": "OTHER", '
            '"text": "autoridad ambiental competente"}, {"type": "OTHER", '
            '"text": "Ley 388 de 1997"}, {"type": "OTHER", "text": "artículo 10 '
            'de la Ley 388 de 1997"}, {"type": "OTHER", "text": "artículo 5"}]',
            "keywords": '["POMIUAC", "Plan de Ordenación y Manejo Integrado", "unidades '
            'ambientales costeras", "Comisión Conjunta", "autoridad ambiental '
            'competente", "norma de superior jerarquía", "ordenamiento '
            'territorial", "Ley 388 de 1997", "planeación sectorial costera", '
            '"gestión ambiental"]',
            "keywords_str": "POMIUAC, Plan de Ordenación y Manejo Integrado, unidades "
            "ambientales costeras, Comisión Conjunta, autoridad ambiental "
            "competente, norma de superior jerarquía, ordenamiento "
            "territorial, Ley 388 de 1997, planeación sectorial costera, "
            "gestión ambiental",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.md",
            "summary": "El chunk define el Plan de Ordenación y Manejo Integrado de las "
            "Unidades Ambientales Costeras (POMIUAC) como instrumento de "
            "planificación que guía la ordenación y gestión ambiental, con "
            "jerarquía superior y efecto sobre planes territoriales y demás "
            "sectores en la zona costera.",
            "title": "CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c81",
        "text": "El  artículo  5º  de  la  norma  ibidem  define  el  Plan  de  Ordenación  y  "
        "Manejo Integrado  de  las  Unidades  Ambientales  Costeras  (POMIUAC)  como  'el "
        "instrumento  de  planificación  mediante  el  cual  la  Comisión  Conjunta  o  la "
        "autoridad ambiental competente, según el caso, definen y orienta la ordenación y "
        "manejo ambiental de las unidades ambientales costeras'.\n"
        "\n"
        "En cuanto a la adopción del mencionado instrumento, de conformidad con lo dispuesto "
        "en el artículo 207 de la Ley 1450 de 2011 y en los artículos y 40 del Decreto Ley "
        "3570, el Decreto 1120, en su artículo 8º, prevé lo siguiente:",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c81",
            "chunk_index": 170,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "Comisión Conjunta"}, {"type": '
            '"ORGANIZATION", "text": "autoridad ambiental competente"}, '
            '{"type": "DATE", "text": "2011"}, {"type": "OTHER", "text": "Ley '
            '1450 de 2011"}, {"type": "OTHER", "text": "Decreto Ley 3570"}, '
            '{"type": "OTHER", "text": "Decreto 1120"}, {"type": "OTHER", '
            '"text": "artículo 5º"}, {"type": "OTHER", "text": "artículo 207"}, '
            '{"type": "OTHER", "text": "artículos 39 y 40"}]',
            "keywords": '["POMIUAC", "Plan de Ordenación y Manejo Integrado", "unidades '
            'ambientales costeras", "Comisión Conjunta", "autoridad ambiental '
            'competente", "artículo 5", "Ley 1450 de 2011", "Decreto 3570", '
            '"Decreto 1120", "adopción del instrumento"]',
            "keywords_str": "POMIUAC, Plan de Ordenación y Manejo Integrado, unidades "
            "ambientales costeras, Comisión Conjunta, autoridad ambiental "
            "competente, artículo 5, Ley 1450 de 2011, Decreto 3570, "
            "Decreto 1120, adopción del instrumento",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.md",
            "summary": "El artículo 5º define el POMIUAC como instrumento de planificación "
            "para ordenar y orientar el manejo ambiental de unidades costeras. "
            "Luego se indica que su adopción se rige por normas como la Ley 1450 "
            "de 2011 y el Decreto 3570, incluyendo el Decreto 1120.",
            "title": "CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c84",
        "text": "Parágrafo 2°. La modificación del Pomiuac se sujetará al procedimiento previsto "
        "para las fases de caracterización y diagnóstico, prospectiva y zonificación y "
        "formulación y adopción del Plan'.'. Finalmente, es de mencionar que el MADS, "
        "mediante Resolución 0768 de  17 de  abril  de  2017,  adoptó  'la  Guía  Técnica  "
        "para  la  Ordenación  y  Manejo Integrado de la Zona Costera. Este insumo básico "
        "permite clasificar las zonas costeras 86 y agotar las distintas fases del POMIUAC "
        "87 .'\n"
        "\n"
        "Conforme a lo expuesto,  para  la  Sala  es  claro  que  el  Plan  Maestro  de  "
        "erosión costera  es  el  instrumento  de  planificación  que  permite  desarrollar  "
        "una  visión  y estrategia a largo plazo, con  un apropiado sustento técnico, "
        "financiero e institucional, encaminado a prevenir, mitigar y controlar las causas y "
        "consecuencias del fenómeno erosivo, ofreciendo a los entes gubernamentales y demás "
        "actores interesados las herramientas que permitan adoptar acciones efectivas.",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c84",
            "chunk_index": 173,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZACIÓN", "text": "MADS"}, {"type": '
            '"ORGANIZACIÓN", "text": "Sala"}, {"type": "OTRO", "text": '
            '"POMIUAC"}, {"type": "OTRO", "text": "Plan Maestro de erosión '
            'costera"}, {"type": "FECHA", "text": "2017"}, {"type": "OTRO", '
            '"text": "Resolución 0768 de 2017"}, {"type": "OTRO", "text": "Guía '
            "Técnica para la Ordenación y Manejo Integrado de la Zona "
            'Costera"}]',
            "keywords": '["POMIUAC", "modificación del plan", "fases de caracterización '
            'diagnóstico", "zonificación y formulación", "prospectiva", "MADS", '
            '"Resolución 0768 de 2017", "Guía Técnica ordenación zona costera", '
            '"plan maestro de erosión costera", "prevención y mitigación '
            'erosión"]',
            "keywords_str": "POMIUAC, modificación del plan, fases de caracterización "
            "diagnóstico, zonificación y formulación, prospectiva, MADS, "
            "Resolución 0768 de 2017, Guía Técnica ordenación zona costera, "
            "plan maestro de erosión costera, prevención y mitigación "
            "erosión",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.md",
            "summary": "El chunk describe la modificación del POMIUAC según un "
            "procedimiento por fases (caracterización/diagnóstico, prospectiva, "
            "zonificación y formulación). Además, menciona la Guía Técnica del "
            "MADS (Res. 0768/2017) y destaca que el Plan Maestro de erosión "
            "costera planifica a largo plazo para prevenir, mitigar y controlar "
            "la erosión.",
            "title": "CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c85",
        "text": "En esa medida, es menester que las entidades vinculadas por pasiva a esta acción "
        "aseguren que dicho plan sea adoptado y ejecutado, por tanto, se modificarán los "
        "párrafos cuatro y cinco del ordinal tercero de la sentencia de primera instancia "
        "con esa finalidad. Exhortándolos para que, al momento de cumplir las órdenes dadas "
        "y desplegar las acciones tendientes a resolver la problemática ambiental, apliquen "
        "y articulen  los  demás  instrumentos  de  planeación  dispuestos  para  atender  "
        "la ocurrencia e impacto de procesos erosivos, tales como: los Planes Integrales de "
        "Gestión del Cambio Climático Sectoriales y Territoriales y POMIUAC.\n"
        "\n"
        "## 6.4.7. Comité de verificación\n"
        "\n"
        "86 Ibíd., 'Artículo 2.2.4.2.1.1. Tipos de zonas costeras. La zona costera se "
        "clasifica en: […]. Los demás criterios fijados en la Guía Técnica para la "
        "Ordenación y Manejo Integrado de la Zona Costera que adoptará el Ministerio de "
        "Ambiente y Desarrollo Sostenible. […]'.",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c85",
            "chunk_index": 174,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZACION", "text": "Ministerio de Ambiente y '
            'Desarrollo Sostenible"}, {"type": "OTRO", "text": "Plan Integral '
            'de Gestión del Cambio Climático Sectoriales y Territoriales"}, '
            '{"type": "OTRO", "text": "POMIUAC"}, {"type": "OTRO", "text": '
            '"Guía Técnica para la Ordenación y Manejo Integrado de la Zona '
            'Costera"}, {"type": "OTRO", "text": "Comité de verificación"}]',
            "keywords": '["erosión costera", "plan de ejecución", "modificación sentencia", '
            '"planeación ambiental", "POMIUAC", "planes integrales gestión '
            'cambio climático", "comité de verificación", "zona costera", '
            '"ordenación y manejo integrado"]',
            "keywords_str": "erosión costera, plan de ejecución, modificación sentencia, "
            "planeación ambiental, POMIUAC, planes integrales gestión "
            "cambio climático, comité de verificación, zona costera, "
            "ordenación y manejo integrado",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.md",
            "summary": "Se ordena modificar la sentencia de primera instancia para exigir "
            "que las entidades demandadas adopten y ejecuten un plan, "
            "articulando instrumentos de planeación para atender la erosión "
            "costera, como planes de cambio climático y POMIUAC. Se introduce el "
            "comité de verificación.",
            "title": "CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico_s2_c35",
        "text": ". Dentro de las unidades costeras, se encuentra  la  Unidad  Ambiental  Costera  "
        "Estuarina  del  rio  Sinú  y  el  Golfo  de Morrosquillo. Dijo que esta disposición "
        "trajo como consecuencia, el desarrollo de una función en cabeza de las "
        "Corporaciones Autónomas Regionales y les impuso ejercer  como máximas autoridades "
        "en las zonas marinas hasta el límite de las líneas base recta establecidas en el "
        "Decreto 1436 de 1984, salvo las competencias que de manera privativa corresponden "
        "al Ministerio y a -CORALINA-.",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "23001233300020150005501",
            "chunk_id": "CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico_s2_c35",
            "chunk_index": 35,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "LOCATION", "text": "río Sinú"}, {"type": "LOCATION", '
            '"text": "Golfo de Morrosquillo"}, {"type": "ORGANIZATION", "text": '
            '"Corporaciones Autónomas Regionales"}, {"type": "ORGANIZATION", '
            '"text": "CORALINA"}, {"type": "OTHER", "text": "Decreto 1436 de '
            '1984"}, {"type": "ORGANIZATION", "text": "Ministerio"}]',
            "keywords": '["Unidad Ambiental Costera Estuarina", "río Sinú", "Golfo de '
            'Morrosquillo", "Corporaciones Autónomas Regionales", "autoridad en '
            'zonas marinas", "líneas base recta", "Decreto 1436 de 1984", '
            '"Ministerio", "CORALINA"]',
            "keywords_str": "Unidad Ambiental Costera Estuarina, río Sinú, Golfo de "
            "Morrosquillo, Corporaciones Autónomas Regionales, autoridad en "
            "zonas marinas, líneas base recta, Decreto 1436 de 1984, "
            "Ministerio, CORALINA",
            "section_heading": "TRÁMITE DE LA ACCIÓN",
            "section_index": 2,
            "section_name": "Desarrollo procesal",
            "source": "CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico.md",
            "summary": "El fragmento describe unidades costeras, destacando la Unidad "
            "Ambiental Costera Estuarina del río Sinú y el Golfo de "
            "Morrosquillo, y explica cómo su disposición asigna a las "
            "Corporaciones Autónomas Regionales funciones y máximas autoridades "
            "en zonas marinas hasta líneas base del Decreto 1436 de 1984.",
            "title": "CE 2da AP 2015 550 Angela Muñoz VS Dpto Cordoba Bienes De Uso Publico",
            "total_chunks_in_section": 43,
        },
    },
    {
        "id": "CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico_s2_c36",
        "text": "Aunado a lo anterior, señaló que dentro de las pruebas del proceso estaba el Plan "
        "de Ordenación y Manejo de la Unidad Ambiental Costera Estuarina del Río Sinú y el "
        "Golfo de Morrosquillo, con una temporalidad de 20 años desde el 2016 y hasta el "
        "2036 y que ese sería precisamente el instrumento técnico ambiental del cual se "
        "debían definir las acciones concretas que permitan determinar las inversiones que "
        "la corporación, los entes territoriales -el departamento de Córdoba y el municipio "
        "de  Moñitos-  debían  gestionar  los  recursos  económicos  para  lograr  ejecutar  "
        "las actividades y medidas de prevención, mitigación y control necesarias para "
        "atender el fenómeno de la erosión costera ordenada por el fallo.\n"
        "\n"
        "## IV.II La Corporación Autónoma Regional de los Valles del Sinú y San Jorge",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "23001233300020150005501",
            "chunk_id": "CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico_s2_c36",
            "chunk_index": 36,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "LOCATION", "text": "Río Sinú"}, {"type": "LOCATION", '
            '"text": "Golfo de Morrosquillo"}, {"type": "LOCATION", "text": '
            '"Moñitos"}, {"type": "LOCATION", "text": "Departamento de '
            'Córdoba"}, {"type": "ORGANIZATION", "text": "Corporación Autónoma '
            'Regional de los Valles del Sinú y San Jorge"}, {"type": "DATE", '
            '"text": "2016"}, {"type": "DATE", "text": "2036"}]',
            "keywords": '["Plan de Ordenación y Manejo", "Unidad Ambiental Costera", '
            '"erosión costera", "Río Sinú", "Golfo de Morrosquillo", '
            '"Corporación Autónoma Regional", "Departamento de Córdoba", '
            '"Municipio de Moñitos", "medidas de prevención mitigación y '
            'control"]',
            "keywords_str": "Plan de Ordenación y Manejo, Unidad Ambiental Costera, erosión "
            "costera, Río Sinú, Golfo de Morrosquillo, Corporación Autónoma "
            "Regional, Departamento de Córdoba, Municipio de Moñitos, "
            "medidas de prevención mitigación y control",
            "section_heading": "TRÁMITE DE LA ACCIÓN",
            "section_index": 2,
            "section_name": "Desarrollo procesal",
            "source": "CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico.md",
            "summary": "El chunk indica que, según las pruebas del proceso, el Plan de "
            "Ordenación y Manejo de la Unidad Ambiental Costera Estuarina del "
            "Río Sinú y el Golfo de Morrosquillo (2016-2036) debe definir "
            "acciones e inversiones para ejecutar medidas contra la erosión "
            "costera ordenadas por el fallo, gestionadas por la corporación y "
            "entidades territoriales.",
            "title": "CE 2da AP 2015 550 Angela Muñoz VS Dpto Cordoba Bienes De Uso Publico",
            "total_chunks_in_section": 43,
        },
    },
    {
        "id": "CE_2da_AP_2021_041_Edgar_Stephengs_VS_Archipielago_San_Andres_Desarrollo_Urbanistico_s3_c43",
        "text": "91. Respecto de esa área protegida, Coralina advirtió en el escrito de contestación "
        "de la demanda que el muelle objeto del litigio hace parte del Distrito de Manejo "
        "Integrado del Área Marina Protegida de la Reserva de Biosfera Seaflower, de "
        "conformidad con el ' Informe No. 1669-2021 de la Procuraduría General de la Nación "
        "'VISITA IN SITU AL  PROYECTO  DE  CONSTRUCCIÓN  DE  LA  ESTACIÓN  DE  CONTROL  DE "
        "TRÁFICO  MARÍTIMO  EN  LA  ISLA  DE  PROVIDENCIA ' y  la  actual  regulación "
        "(Acuerdo 002 de 2019) '. Esos documentos señalan que ' el muelle se encuentra en "
        "una Zona de Conservación (No Take) del Distrito de Manejo Integrado del Área Marina "
        "Protegida de la Reserva de Biosfera Seaflower '  (negrilla fuera  de texto).\n"
        "\n"
        "92. En ese sentido, desde el punto de vista de la viabilidad jurídica del proyecto "
        "de construcción de la Estación de Control de Tráfico Marítimo, se debe considerar "
        "que la Autoridad Nacional de Licencias Ambientales, conforme al Decreto 2041 de "
        "2014 ,",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Germán Eduardo Osorio Cifuentes",
            "Radicado": "88001-23-33-000-2021-00041-02",
            "chunk_id": "CE_2da_AP_2021_041_Edgar_Stephengs_VS_Archipielago_San_Andres_Desarrollo_Urbanistico_s3_c43",
            "chunk_index": 43,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "Coralina"}, {"type": '
            '"ORGANIZATION", "text": "Procuraduría General de la Nación"}, '
            '{"type": "ORGANIZATION", "text": "Autoridad Nacional de Licencias '
            'Ambientales"}, {"type": "LOCATION", "text": "Isla de '
            'Providencia"}, {"type": "LOCATION", "text": "Reserva de Biosfera '
            'Seaflower"}, {"type": "OTHER", "text": "Distrito de Manejo '
            'Integrado del Área Marina Protegida"}, {"type": "DATE", "text": '
            '"2021"}, {"type": "DATE", "text": "2019"}, {"type": "OTHER", '
            '"text": "Decreto 2041 de 2014"}, {"type": "OTHER", "text": '
            '"Acuerdo 002 de 2019"}, {"type": "OTHER", "text": "Informe No. '
            '1669-2021"}]',
            "keywords": '["Coralina", "Distrito de Manejo Integrado", "Reserva de Biosfera '
            'Seaflower", "Zona de Conservación No Take", "muelle objeto del '
            'litigio", "Estación de Control de Tráfico Marítimo", "Autoridad '
            'Nacional de Licencias Ambientales", "Acuerdo 002 de 2019", '
            '"Decreto 2041 de 2014"]',
            "keywords_str": "Coralina, Distrito de Manejo Integrado, Reserva de Biosfera "
            "Seaflower, Zona de Conservación No Take, muelle objeto del "
            "litigio, Estación de Control de Tráfico Marítimo, Autoridad "
            "Nacional de Licencias Ambientales, Acuerdo 002 de 2019, "
            "Decreto 2041 de 2014",
            "section_heading": "57. CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "CE_2da_AP_2021_041_Edgar_Stephengs_VS_Archipielago_San_Andres_Desarrollo_Urbanistico.md",
            "summary": "Coralina indica que el muelle del litigio está dentro del Distrito "
            "de Manejo Integrado de la Reserva de Biosfera Seaflower, "
            "específicamente en una Zona de Conservación No Take, citando "
            "informes de Procuraduría y regulación de 2019 para evaluar la "
            "viabilidad jurídica del proyecto.",
            "title": "CE 2da AP 2021 041 Edgar Stephengs VS Archipielago San Andres "
            "Desarrollo Urbanistico",
            "total_chunks_in_section": 152,
        },
    },
    {
        "id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s3_c115",
        "text": "- Copia del Oficio de 12 de abril de 2011 mediante el cual la Administradora del "
        "Condominio Lagomar Marina Club solicitó al Capitán de Fragata de la Capitanía de "
        "Puertos de Santa Marta realizar una inspección con ingeniero oceanógrafo y solicita "
        "que se pronuncie sobre la posibilidad de recuperación de la playa, la realización "
        "de obras que prevengan el impacto del mar en el litoral e indique quién debe "
        "realizarlos (fs. 12-13).\n"
        "-  Concepto  Técnico  N°  01  de  30 de  mayo  de  2011,  suscrito  por  el  Perito "
        "Marítimo experto en Oceanográfica Física de la Capitanía de Puerto de Santa Marta, "
        "en el que rinde informe sobre la problemática de erosión costera que se están  "
        "presentando (Sic) en  el  sector  de  Lagomar  (Pozos  Colorados)  y,  en especial, "
        "con las obras oceánicas y de protección Costera instaladas vecinas al proyecto "
        "urbanístico (f.15-29).",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- "
            "GABRIEL CARRERO_s3_c115",
            "chunk_index": 115,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "Administradora del Condominio '
            'Lagomar Marina Club"}, {"type": "PERSON", "text": "Capitán de '
            'Fragata"}, {"type": "ORGANIZATION", "text": "Capitanía de Puertos '
            'de Santa Marta"}, {"type": "ORGANIZATION", "text": "Perito '
            'Marítimo"}, {"type": "LOCATION", "text": "Santa Marta"}, {"type": '
            '"LOCATION", "text": "Lagomar Marina Club"}, {"type": "LOCATION", '
            '"text": "Pozos Colorados"}, {"type": "DATE", "text": "abril de '
            '2011"}, {"type": "DATE", "text": "mayo de 2011"}, {"type": '
            '"OTHER", "text": "Concepto Técnico N° 01"}]',
            "keywords": '["erosión costera", "Lagomar Marina Club", "Pozos Colorados", '
            '"Capitanía de Puertos de Santa Marta", "inspección marítima", '
            '"recuperación de la playa", "obras de protección costera", '
            '"peritaje oceanográfico", "Concepto Técnico N° 01"]',
            "keywords_str": "erosión costera, Lagomar Marina Club, Pozos Colorados, "
            "Capitanía de Puertos de Santa Marta, inspección marítima, "
            "recuperación de la playa, obras de protección costera, "
            "peritaje oceanográfico, Concepto Técnico N° 01",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL "
            "CARRERO.md",
            "summary": "El tribunal analiza solicitudes y peritajes técnicos sobre erosión "
            "costera en Lagomar Marina Club (Pozos Colorados). Se incluye copia "
            "de un oficio de 2011 y un Concepto Técnico N° 01 de mayo de 2011 "
            "que evalúa obras de protección y recuperación de la playa.",
            "title": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c60",
        "text": "' Artículo  5. Plan  de  Ordenación  y  Manejo  Integrado  de  las  Unidades "
        "Ambientales Costeras (Pomiuac). Es el instrumento de planificación mediante el cual "
        "la Comisión Conjunta o la autoridad ambiental competente, según  el  caso,  "
        "definen  y  orienta  la  ordenación  y  manejo  ambiental  de  las unidades "
        "ambientales costeras.\n"
        "\n"
        "El  Pomiuac  se  constituye  en  norma  de  superior  jerarquía  y  determinante "
        "ambiental  para  la  elaboración  y  adopción  de  los  planes  de  ordenamiento "
        "territorial, de conformidad con lo dispuesto en el artículo 10 de la Ley 388 de "
        "1997 y orienta la planeación de los demás sectores en la zona costera.'",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- "
            "GABRIEL CARRERO_s4_c60",
            "chunk_index": 149,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "Comisión Conjunta"}, {"type": '
            '"OTHER", "text": "Unidades Ambientales Costeras"}, {"type": '
            '"OTHER", "text": "POMIUAC"}, {"type": "DATE", "text": "1997"}, '
            '{"type": "OTHER", "text": "Ley 388 de 1997"}, {"type": "OTHER", '
            '"text": "artículo 10 de la Ley 388 de 1997"}]',
            "keywords": '["POMIUAC", "Plan de Ordenación y Manejo Integrado", "Unidades '
            'Ambientales Costeras", "Comisión Conjunta", "autoridad ambiental '
            'competente", "ordenamiento territorial", "norma de superior '
            'jerarquía", "Ley 388 de 1997", "planeación sectorial costera"]',
            "keywords_str": "POMIUAC, Plan de Ordenación y Manejo Integrado, Unidades "
            "Ambientales Costeras, Comisión Conjunta, autoridad ambiental "
            "competente, ordenamiento territorial, norma de superior "
            "jerarquía, Ley 388 de 1997, planeación sectorial costera",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL "
            "CARRERO.md",
            "summary": "El chunk explica el Plan de Ordenación y Manejo Integrado de las "
            "Unidades Ambientales Costeras (POMIUAC), como instrumento de "
            "planificación de la Comisión Conjunta o la autoridad ambiental. "
            "Además, establece su jerarquía superior y su papel en planes "
            "territoriales según la Ley 388 de 1997.",
            "title": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c81",
        "text": "El  artículo  5º  de  la  norma  ibidem  define  el  Plan  de  Ordenación  y  "
        "Manejo Integrado  de  las  Unidades  Ambientales  Costeras  (POMIUAC)  como  'el "
        "instrumento  de  planificación  mediante  el  cual  la  Comisión  Conjunta  o  la "
        "autoridad ambiental competente, según el caso, definen y orienta la ordenación y "
        "manejo ambiental de las unidades ambientales costeras'.\n"
        "\n"
        "En cuanto a la adopción del mencionado instrumento, de conformidad con lo dispuesto "
        "en el artículo 207 de la Ley 1450 de 2011 y en los artículos y 40 del Decreto Ley "
        "3570, el Decreto 1120, en su artículo 8º, prevé lo siguiente:",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- "
            "GABRIEL CARRERO_s4_c81",
            "chunk_index": 170,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZATION", "text": "Comisión Conjunta"}, {"type": '
            '"OTHER", "text": "Ley 1450 de 2011"}, {"type": "OTHER", "text": '
            '"Decreto Ley 3570"}, {"type": "OTHER", "text": "Decreto 1120"}, '
            '{"type": "DATE", "text": "2011"}, {"type": "OTHER", "text": '
            '"artículo 5º"}, {"type": "OTHER", "text": "artículo 207"}, '
            '{"type": "OTHER", "text": "artículo 8º"}]',
            "keywords": '["POMIUAC", "Plan de Ordenación y Manejo Integrado", "Unidades '
            'Ambientales Costeras", "Comisión Conjunta", "autoridad ambiental '
            'competente", "Ley 1450 de 2011", "artículo 207", "Decreto Ley '
            '3570", "Decreto 1120", "artículo 8"]',
            "keywords_str": "POMIUAC, Plan de Ordenación y Manejo Integrado, Unidades "
            "Ambientales Costeras, Comisión Conjunta, autoridad ambiental "
            "competente, Ley 1450 de 2011, artículo 207, Decreto Ley 3570, "
            "Decreto 1120, artículo 8",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL "
            "CARRERO.md",
            "summary": "El fragmento define el POMIUAC como instrumento de planificación "
            "para ordenar y manejar ambientalmente las unidades costeras, y "
            "relaciona su adopción con disposiciones de la Ley 1450 de 2011 y "
            "normas del Decreto Ley 3570 y el Decreto 1120.",
            "title": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c84",
        "text": "Parágrafo 2°. La modificación del Pomiuac se sujetará al procedimiento previsto "
        "para las fases de caracterización y diagnóstico, prospectiva y zonificación y "
        "formulación y adopción del Plan'.'. Finalmente, es de mencionar que el MADS, "
        "mediante Resolución 0768 de  17 de  abril  de  2017,  adoptó  'la  Guía  Técnica  "
        "para  la  Ordenación  y  Manejo Integrado de la Zona Costera. Este insumo básico "
        "permite clasificar las zonas costeras 86 y agotar las distintas fases del POMIUAC "
        "87 .'\n"
        "\n"
        "Conforme a lo expuesto,  para  la  Sala  es  claro  que  el  Plan  Maestro  de  "
        "erosión costera  es  el  instrumento  de  planificación  que  permite  desarrollar  "
        "una  visión  y estrategia a largo plazo, con  un apropiado sustento técnico, "
        "financiero e institucional, encaminado a prevenir, mitigar y controlar las causas y "
        "consecuencias del fenómeno erosivo, ofreciendo a los entes gubernamentales y demás "
        "actores interesados las herramientas que permitan adoptar acciones efectivas.",
        "metadata": {
            "Corporación": "Consejo de Estado — Sala de lo Contencioso Administrativo — "
            "Sección Primera",
            "Magistrado ponente": "Oswaldo Giraldo López",
            "Radicado": "4700123310002011-08425-02(AP)",
            "chunk_id": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- "
            "GABRIEL CARRERO_s4_c84",
            "chunk_index": 173,
            "doc_type": "jurisprudencia",
            "entities": '[{"type": "ORGANIZACION", "text": "MADS"}, {"type": "DATE", '
            '"text": "abril de 2017"}, {"type": "OTHER", "text": "Resolución '
            '0768 de 2017"}, {"type": "OTHER", "text": "POMIUAC"}, {"type": '
            '"OTHER", "text": "Plan Maestro de erosión costera"}, {"type": '
            '"OTHER", "text": "Guía Técnica para la Ordenación y Manejo '
            'Integrado de la Zona Costera"}, {"type": "OTHER", "text": "Zona '
            'costera"}]',
            "keywords": '["POMIUAC", "modificación del plan", "fases de caracterización y '
            'diagnóstico", "zonificación costera", "MADS", "Guía Técnica zona '
            'costera", "ordenación y manejo integrado", "plan maestro de '
            'erosión costera", "prevención y mitigación", "planificación a '
            'largo plazo"]',
            "keywords_str": "POMIUAC, modificación del plan, fases de caracterización y "
            "diagnóstico, zonificación costera, MADS, Guía Técnica zona "
            "costera, ordenación y manejo integrado, plan maestro de "
            "erosión costera, prevención y mitigación, planificación a "
            "largo plazo",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "section_index": 3,
            "section_name": "Análisis del tribunal",
            "source": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL "
            "CARRERO.md",
            "summary": "El chunk describe que la modificación del POMIUAC debe seguir las "
            "fases de caracterización, diagnóstico, prospectiva, zonificación y "
            "formulación; además, menciona la Guía Técnica del MADS para la zona "
            "costera y destaca que el Plan Maestro de erosión costera orienta "
            "acciones a largo plazo.",
            "title": "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO",
            "total_chunks_in_section": 186,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s1_c0",
        "text": "## DECRETO 415 DE 2017\n"
        "\n"
        "## (Marzo 13)\n"
        "\n"
        "'Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de "
        "2015, Decreto Único Reglamentario del Sector Ambiente y Desarrollo Sostenible, un "
        "Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUACCaribe Insular, en el Departamento Archipiélago de "
        "San Andrés, Providencia y Santa Catalina'\n"
        "\n"
        "## EL PRESIDENTE DE LA REPÚBLICA DE\n"
        "\n"
        "En ejercicio de sus facultades constitucionales y legales, en especial las que le "
        "confiere el numeral 11 del artículo 189 de la Constitución Política, el artículo "
        "2°, los numerales 1 y 24 del artículo 5° y parágrafo 3° del artículo 33 de la Ley "
        "99 de 1993 y en desarrollo del parágrafo 3 del artículo 207 de la Ley 1450 de 2011 "
        "modificado por el artículo 17 del Decreto número 3570 de 2011 y,\n"
        "\n"
        "## CONSIDERANDO",
        "metadata": {
            "articulo_titulo": "",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s1_c0",
            "chunk_index": 0,
            "doc_type": "normativa",
            "entities": '[{"type": "NORM", "text": "Decreto 415 de 2017"}, {"type": "DATE", '
            '"text": "Marzo"}, {"type": "NORM", "text": "Decreto 1076 de '
            '2015"}, {"type": "NORM", "text": "Ley 99 de 1993"}, {"type": '
            '"NORM", "text": "Ley 1450 de 2011"}, {"type": "NORM", "text": '
            '"Decreto 3570 de 2011"}, {"type": "PERSON", "text": "Presidente de '
            'la República de Colombia"}, {"type": "NORM", "text": "Constitución '
            'Política de Colombia, artículo 189 numeral 11"}, {"type": '
            '"LOCATION", "text": "Departamento Archipiélago de San Andrés, '
            'Providencia y Santa Catalina"}, {"type": "NORM", "text": "POMIUAC '
            'Caribe Insular"}]',
            "keywords": '["POMIUAC Caribe Insular", "Decreto 1076 de 2015", "Decreto 415 de '
            '2017", "Ordenación y manejo integrado", "Unidad Ambiental '
            'Costera", "San Andrés Providencia Santa Catalina", "Ley 99 de '
            '1993", "Ley 1450 de 2011", "Decreto 3570 de 2011", "facultades '
            'presidenciales artículo 189"]',
            "keywords_str": "POMIUAC Caribe Insular, Decreto 1076 de 2015, Decreto 415 de "
            "2017, Ordenación y manejo integrado, Unidad Ambiental Costera, "
            "San Andrés Providencia Santa Catalina, Ley 99 de 1993, Ley "
            "1450 de 2011, Decreto 3570 de 2011, facultades presidenciales "
            "artículo 189",
            "norma": "Decreto 415 de 2017",
            "section_index": 1,
            "section_name": "Preámbulo",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "El preámbulo del Decreto 415 de 2017 establece la base jurídica "
            "para adicionar al Decreto 1076 de 2015 un capítulo que define el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera (POMIUAC) Caribe Insular, en San Andrés, Providencia y "
            "Santa Catalina.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 14,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s1_c6",
        "text": "Que el numeral 10 del artículo 17 del Decreto número 3570 de 2011 modificó la parte "
        "final del parágrafo 3° del artículo 207 de la Ley 1450 de 2011, en el sentido que "
        "la Dirección de Asuntos Marinos, Costeros y Recursos Acuáticos del Ministerio de "
        "Ambiente y Desarrollo Sostenible le corresponde 'Emitir concepto previo a la "
        "aprobación de los planes de manejo integrado de las unidades ambientales costeras "
        "que deben ser adoptados por las corporaciones autónomas regionales'.\n"
        "\n"
        "Que la Política de Gestión Integral de Recurso Hídrico (2010) estableció que 'en "
        "relación con la planificación de las cuencas con zonas marinocosteras, se deberá "
        "considerar como unidad de análisis la unidad ambiental costera y los lineamientos "
        "definidos para su manejo, asimismo, se deberán articular a las acciones del POMCA "
        "las medidas adoptadas en las cuencas adyacentes incluidas en la unidad ambiental "
        "costera'.",
        "metadata": {
            "articulo_titulo": "",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s1_c6",
            "chunk_index": 6,
            "doc_type": "normativa",
            "entities": '[{"type": "NORMA", "text": "Decreto 1076 de 2015"}, {"type": '
            '"NORMA", "text": "Decreto 3570 de 2011"}, {"type": "NORMA", '
            '"text": "Ley 1450 de 2011"}, {"type": "NORMA", "text": "Política '
            'de Gestión Integral de Recurso Hídrico (2010"}, {"type": '
            '"ENTIDAD", "text": "Dirección de Asuntos Marinos, Costeros y '
            "Recursos Acuáticos del Ministerio de Ambiente y Desarrollo "
            'Sostenible"}, {"type": "ENTIDAD", "text": "Corporaciones autónomas '
            'regionales"}, {"type": "ENTIDAD", "text": "Unidad Ambiental '
            'Costera"}, {"type": "ENTIDAD", "text": "POMCA"}, {"type": "CITA '
            'NORMATIVA", "text": "artículo 17 del Decreto 3570 de 2011"}, '
            '{"type": "CITA NORMATIVA", "text": "parágrafo 3° del artículo 207 '
            'de la Ley 1450 de 2011"}]',
            "keywords": '["concepto previo", "planes de manejo integrado", "unidad '
            'ambiental costera", "Dirección de Asuntos Marinos", "corporaciones '
            'autónomas regionales", "articulación POMCA", "gestión integral del '
            'recurso hídrico", "cuencas marinocosteras", "Ley 1450 de 2011", '
            '"Decreto 3570 de 2011"]',
            "keywords_str": "concepto previo, planes de manejo integrado, unidad ambiental "
            "costera, Dirección de Asuntos Marinos, corporaciones autónomas "
            "regionales, articulación POMCA, gestión integral del recurso "
            "hídrico, cuencas marinocosteras, Ley 1450 de 2011, Decreto "
            "3570 de 2011",
            "norma": "Decreto 415 de 2017",
            "section_index": 1,
            "section_name": "Preámbulo",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "El preámbulo precisa competencias y lineamientos: la Dirección de "
            "Asuntos Marinos, Costeros y Recursos Acuáticos debe emitir concepto "
            "previo sobre planes de manejo integrado de unidades ambientales "
            "costeras; además, la política hídrica ordena articular acciones de "
            "planificación con POMCA y medidas en cuencas adyacentes.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 14,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s1_c13",
        "text": "Que así las cosas, dadas las particularidades del Departamento Archipiélago, se ha "
        "vislumbrado la necesidad de reglamentar y compilar de manera especial y con enfoque "
        "diferencial, en cuanto a los alcances de las fases de formulación, adopción y otros "
        "aspectos en el Plan de Ordenación y Manejo integrado de la Unidad Ambiental Costera "
        "Caribe Insular -POMIUAC Insular-, de tal manera que responda adecuadamente a las "
        "especialidades y necesidades ambientales de esta jurisdicción, como un único "
        "instrumento articulador de las regulaciones y ordenaciones del territorio del "
        "Departamento Archipiélago de San Andrés, Providencia y Santa Catalina.\n"
        "\n"
        "En mérito de lo expuesto,\n"
        "\n"
        "## DECRETA:",
        "metadata": {
            "articulo_titulo": "",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s1_c13",
            "chunk_index": 13,
            "doc_type": "normativa",
            "entities": '[{"type": "LOCATION", "text": "Departamento Archipiélago de San '
            'Andrés, Providencia y Santa Catalina"}, {"type": "LOCATION", '
            '"text": "Caribe Insular"}, {"type": "OTHER", "text": "Plan de '
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            '-POMIUAC- Caribe Insular"}]',
            "keywords": '["POMIUAC Caribe Insular", "enfoque diferencial", "fases de '
            'formulación", "adopción del plan", "ordenación territorial", '
            '"instrumento articulador", "Departamento Archipiélago", '
            '"reglamentación y compilación"]',
            "keywords_str": "POMIUAC Caribe Insular, enfoque diferencial, fases de "
            "formulación, adopción del plan, ordenación territorial, "
            "instrumento articulador, Departamento Archipiélago, "
            "reglamentación y compilación",
            "norma": "Decreto 415 de 2017",
            "section_index": 1,
            "section_name": "Preámbulo",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Se sustenta la necesidad de reglamentar y compilar, con enfoque "
            "diferencial, las fases de formulación y adopción del POMIUAC Caribe "
            "Insular, como un instrumento articulador para la ordenación "
            "territorial del Archipiélago.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 14,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s3_art2-2-4-2-3-1_c0",
        "text": "ARTÍCULO 2.2.4.2.3.1. Ámbito de aplicación. - El presente capítulo aplicará de "
        "manera exclusiva para el Departamento Archipiélago de San Andrés, Providencia y "
        "Santa Catalina.",
        "metadata": {
            "articulo": "2.2.4.2.3.1",
            "articulo_titulo": "Ámbito de aplicación",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s3_art2-2-4-2-3-1_c0",
            "chunk_index": 0,
            "doc_type": "normativa",
            "entities": '[{"type": "LOCATION", "text": "Departamento Archipiélago de San '
            'Andrés, Providencia y Santa Catalina"}, {"type": "OTHER", "text": '
            '"POMIUAC Caribe"}, {"type": "DATE", "text": "2.2.4.2.3.1"}, '
            '{"type": "NORMATIVE", "text": "Decreto 1076 de 2015"}]',
            "keywords": '["ámbito de aplicación", "aplicación exclusiva", "Departamento '
            'Archipiélago", "San Andrés", "Providencia", "Santa Catalina", '
            '"POMIUAC Caribe", "capítulo normativo"]',
            "keywords_str": "ámbito de aplicación, aplicación exclusiva, Departamento "
            "Archipiélago, San Andrés, Providencia, Santa Catalina, POMIUAC "
            "Caribe, capítulo normativo",
            "norma": "Decreto 415 de 2017",
            "section_index": 3,
            "section_name": "Ámbito de aplicación",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "El artículo define el ámbito de aplicación exclusivo del capítulo "
            "que desarrolla el Plan de Ordenación y Manejo Integrado de la "
            "Unidad Ambiental Costera (POMIUAC), limitándolo al Departamento "
            "Archipiélago de San Andrés, Providencia y Santa Catalina.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s4_art2-2-4-2-3-2_c0",
        "text": "ARTÍCULO 2.2.4.2.3.2. Unificación   de   instrumentos. -   Para   todos   los   "
        "efectos   del   ordenamiento   ambiental,   el   POMIUAC   INSULAR,   será   el   "
        "único instrumento para el manejo, ordenamiento y planificación ambiental de la "
        "Unidad Ambiental Costera -UAC-Caribe Insular, el cual no incorporara' las áreas del "
        "Sistema de Parques Nacionales Naturales de Colombia, las cuales continuarán su "
        "gestión a través de los instrumentos de manejo establecidos para dichas áreas.\n"
        "\n"
        "El POMIUAC INSULAR, incorporará y subsumirá los siguientes instrumentos actualmente "
        "vigentes o exigibles para el Departamento Archipiélago de San Andrés, Providencia y "
        "Santa Catalina en su territorio emergido y sumergido:",
        "metadata": {
            "articulo": "2.2.4.2.3.2",
            "articulo_titulo": "Unificación de instrumentos",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s4_art2-2-4-2-3-2_c0",
            "chunk_index": 0,
            "doc_type": "normativa",
            "entities": '[{"type": "NORMA", "text": "Decreto 1076 de 2015"}, {"type": '
            '"NORMA", "text": "Decreto 1076 de 2015, Título 4 de la Parte 2 del '
            'Libro 2"}, {"type": "NORMA", "text": "Artículo 2.2.4.2.3.2"}, '
            '{"type": "OTRO", "text": "Plan de Ordenación y Manejo Integrado de '
            'la Unidad Ambiental Costera -POMIUAC-"}, {"type": "OTRO", "text": '
            '"POMIUAC INSULAR"}, {"type": "OTRO", "text": "Unidad Ambiental '
            'Costera -UAC-Caribe Insular"}, {"type": "NORMA", "text": "Sistema '
            'de Parques Nacionales Naturales de Colombia"}, {"type": "LUGAR", '
            '"text": "Departamento Archipiélago de San Andrés, Providencia y '
            'Santa Catalina"}]',
            "keywords": '["POMIUAC Insular", "Unificación de instrumentos", "ordenamiento '
            'ambiental", "Unidad Ambiental Costera UAC", "manejo y '
            'planificación ambiental", "exclusión Parques Nacionales '
            'Naturales", "Departamento Archipiélago de San Andrés", "territorio '
            'emergido y sumergido"]',
            "keywords_str": "POMIUAC Insular, Unificación de instrumentos, ordenamiento "
            "ambiental, Unidad Ambiental Costera UAC, manejo y "
            "planificación ambiental, exclusión Parques Nacionales "
            "Naturales, Departamento Archipiélago de San Andrés, territorio "
            "emergido y sumergido",
            "norma": "Decreto 415 de 2017",
            "section_index": 4,
            "section_name": "Unificación de instrumentos",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Establece la unificación de instrumentos para el ordenamiento "
            "ambiental: el POMIUAC Insular será el único instrumento de manejo, "
            "ordenamiento y planificación de la UAC Caribe Insular, excluyendo "
            "áreas de Parques Nacionales. Además, incorpora y subsume "
            "instrumentos vigentes para el Archipiélago en emergido y sumergido.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 3,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s4_art2-2-4-2-3-2_c1",
        "text": "1. Plan de Manejo de la Reserva de Biosfera Seaflower.\n"
        "2. Plan o planes de Ordenación y Manejo de Cuencas Hidrográficas - POMCA. 3. Plan o "
        "planes de Zonificación de los Manglares. 4. Plan de Manejo de Acuíferos y Aguas "
        "Subterráneas. 5. Planes de Manejo de Áreas Protegidas: (Área Marina Protegida de la "
        "Reserva de Biosfera Seaflower, el Parque Regional 'Old Point Regional Mangrove "
        "Park', el Parque Regional Johnny Cay, El Parque Regional 'The Peak').\n"
        "\n"
        "PARÁGRAFO 1°.- El POMIUAC INSULAR se constituye en norma de superior jerarquía y "
        "determinante ambiental para la elaboración y adopción de los planes o esquemas de "
        "ordenamiento territorial o plan de ordenamiento departamental, en el Departamento "
        "Archipiélago de San Andrés, Providencia y Santa Catalina.\n"
        "\n"
        "PARÁGRAFO 2°.- El POMIUAC INSULAR tendrá en consideración, como estrategia "
        "complementaria para la conservación de la diversidad biológica, a la Reserva de "
        "Biosfera Seaflower.",
        "metadata": {
            "articulo": "2.2.4.2.3.2",
            "articulo_titulo": "Unificación de instrumentos",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s4_art2-2-4-2-3-2_c1",
            "chunk_index": 1,
            "doc_type": "normativa",
            "entities": '[{"type": "other", "text": "POMIUAC INSULAR"}, {"type": '
            '"LOCATION", "text": "Departamento Archipiélago de San Andrés, '
            'Providencia y Santa Catalina"}, {"type": "LOCATION", "text": '
            '"Reserva de Biosfera Seaflower"}, {"type": "other", "text": "Plan '
            "o planes de Ordenación y Manejo de Cuencas Hidrográficas "
            '(POMCA)"}, {"type": "other", "text": "Planes de Zonificación de '
            'los Manglares"}, {"type": "other", "text": "Plan de Manejo de '
            'Acuíferos y Aguas Subterráneas"}, {"type": "other", "text": "Área '
            'Marina Protegida de la Reserva de Biosfera Seaflower"}, {"type": '
            '"other", "text": "Parque Regional \'Old Point Regional Mangrove '
            'Park\'"}, {"type": "other", "text": "Parque Regional Johnny Cay"}, '
            '{"type": "other", "text": "Parque Regional \'The Peak\'"}]',
            "keywords": '["POMIUAC insular", "norma de superior jerarquía", "determinante '
            'ambiental", "ordenamiento territorial departamental", "San Andrés '
            'Providencia y Santa Catalina", "POMCA", "zonificación manglares", '
            '"planes de áreas protegidas", "Reserva de Biosfera Seaflower", '
            '"conservación diversidad biológica"]',
            "keywords_str": "POMIUAC insular, norma de superior jerarquía, determinante "
            "ambiental, ordenamiento territorial departamental, San Andrés "
            "Providencia y Santa Catalina, POMCA, zonificación manglares, "
            "planes de áreas protegidas, Reserva de Biosfera Seaflower, "
            "conservación diversidad biológica",
            "norma": "Decreto 415 de 2017",
            "section_index": 4,
            "section_name": "Unificación de instrumentos",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Define componentes de planificación (planes POMCA, manglares, "
            "acuíferos, áreas protegidas) y establece que el POMIUAC insular es "
            "norma de superior jerarquía y determinante ambiental para ordenar "
            "territorialmente en San Andrés y archipiélago, con estrategia "
            "complementaria para conservar la diversidad biológica (Reserva "
            "Seaflower).",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 3,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s5_art2-2-4-2-3-3_c0",
        "text": "ARTÍCULO 2.2.4.2.3.3. Formulación y adopción del POMIUAC INSULAR. - La formulación "
        "del POMIUAC INSULAR, estará a cargo de la Dirección General de la Corporación para "
        "el Desarrollo Sostenible del Archipiélago de San Andrés, Providencia y Santa "
        "Catalina - CORALINA y su adopción estará en cabeza del consejo Directivo de dicha "
        "entidad.\n"
        "\n"
        "El Director General y el consejo Directivo contarán con un tiempo máximo de cuatro "
        "(4) años para la formulación y adopción que se contarán a partir de la expedición "
        "de la Guía Técnica para la Ordenación, Ordenamiento y Planificación Ambiental.",
        "metadata": {
            "articulo": "2.2.4.2.3.3",
            "articulo_titulo": "Formulación y adopción del POMIUAC INSULAR",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s5_art2-2-4-2-3-3_c0",
            "chunk_index": 0,
            "doc_type": "normativa",
            "entities": '[{"type": "PERSON", "text": "Director General"}, {"type": '
            '"ORGANIZATION", "text": "CORALINA"}, {"type": "ORGANIZATION", '
            '"text": "Consejo Directivo de CORALINA"}, {"type": "LOCATION", '
            '"text": "Archipiélago de San Andrés, Providencia y Santa '
            'Catalina"}, {"type": "OTHER", "text": "POMIUAC INSULAR"}, {"type": '
            '"OTHER", "text": "Guía Técnica para la Ordenación, Ordenamiento y '
            'Planificación Ambiental"}, {"type": "DATE", "text": "cuatro (4) '
            'años"}]',
            "keywords": '["POMIUAC Insular", "formulación", "adopción", "CORALINA", '
            '"Consejo Directivo", "Dirección General", "plazo máximo cuatro '
            'años", "Guía Técnica", "ordenación y planificación ambiental"]',
            "keywords_str": "POMIUAC Insular, formulación, adopción, CORALINA, Consejo "
            "Directivo, Dirección General, plazo máximo cuatro años, Guía "
            "Técnica, ordenación y planificación ambiental",
            "norma": "Decreto 415 de 2017",
            "section_index": 5,
            "section_name": "Formulación y adopción del POMIUAC INSULAR",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Regula quién formula y quién adopta el POMIUAC INSULAR: CORALINA lo "
            "formula y su Consejo Directivo lo adopta. Establece un plazo máximo "
            "de cuatro años, contado desde la expedición de la Guía Técnica "
            "correspondiente.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c3",
        "text": "Como resultado de la prospectiva se elaborará la zonificación ambiental.\n"
        "\n"
        "Las categorías de uso y manejo, así como los criterios técnicos para la elaboración "
        "de la zonificación ambiental se desarrollarán con base en los parámetros que se "
        "definan en la Guía Técnica para la Ordenación, Ordenamiento y Planificación "
        "Ambiental de la Unidad Ambiental Costera Caribe Insular,",
        "metadata": {
            "articulo": "2.2.4.2.3.4",
            "articulo_titulo": "Fases para la formulación, adopción e implementación del "
            "POMIUAC INSULAR",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c3",
            "chunk_index": 3,
            "doc_type": "normativa",
            "entities": '[{"type": "OTHER", "text": "zonificación ambiental"}, {"type": '
            '"OTHER", "text": "prospectiva"}, {"type": "OTHER", "text": "Guía '
            "Técnica para la Ordenación, Ordenamiento y Planificación Ambiental "
            'de la Unidad Ambiental Costera Caribe Insular"}, {"type": "OTHER", '
            '"text": "Unidad Ambiental Costera Caribe Insular"}]',
            "keywords": '["zonificación ambiental", "prospectiva", "categorías de uso y '
            'manejo", "criterios técnicos", "Guía Técnica", "Unidad Ambiental '
            'Costera Caribe Insular", "ordenación y planificación ambiental", '
            '"ordenamiento"]',
            "keywords_str": "zonificación ambiental, prospectiva, categorías de uso y "
            "manejo, criterios técnicos, Guía Técnica, Unidad Ambiental "
            "Costera Caribe Insular, ordenación y planificación ambiental, "
            "ordenamiento",
            "norma": "Decreto 415 de 2017",
            "section_index": 6,
            "section_name": "Fases para la formulación, adopción e implementación del "
            "POMIUAC INSULAR",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Indica que, como resultado de la prospectiva, se elaborará la "
            "zonificación ambiental; y que las categorías de uso y manejo y los "
            "criterios técnicos se definirán con base en la Guía Técnica de la "
            "Unidad Ambiental Costera Caribe Insular.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 6,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
        "text": "4. Formulación y Adopción: Con base en los resultados de las fases anteriores, se "
        "establecerán los objetivos, metas, programas, proyectos, estrategias y las medidas "
        "para la administración y manejo sostenible de los recursos naturales renovables y "
        "se procederá a su adopción.\n"
        "5. Implementación o Ejecución: Corresponde a CORALINA coordinar la ejecución del "
        "POMIUAC INSULAR; sin perjuicio de las competencias concurrentes de las demás "
        "autoridades con jurisdicción y competencia en el Departamento Archipiélago.\n"
        "6. Seguimiento y Evaluación: CORALINA realizará el seguimiento y la evaluación del "
        "POMIUAC INSULAR, con base en lo definido en el dicho plan en concordancia con la "
        "Guía Técnica para la Ordenación, Ordenamiento y Planificación Ambiental de la "
        "Unidad Ambiental Costera Caribe Insular.",
        "metadata": {
            "articulo": "2.2.4.2.3.4",
            "articulo_titulo": "Fases para la formulación, adopción e implementación del "
            "POMIUAC INSULAR",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "chunk_index": 4,
            "doc_type": "normativa",
            "entities": '[{"type": "ORGANIZATION", "text": "CORALINA"}, {"type": '
            '"OTHER_NORM", "text": "Decreto 1076 de 2015"}, {"type": '
            '"OTHER_NORM", "text": "Guía Técnica para la Ordenación, '
            "Ordenamiento y Planificación Ambiental de la Unidad Ambiental "
            'Costera Caribe Insular"}, {"type": "LOCATION", "text": '
            '"Departamento Archipiélago"}, {"type": "OTHER", "text": "POMIUAC '
            'INSULAR"}, {"type": "OTHER", "text": "Unidad Ambiental Costera '
            'Caribe Insular"}]',
            "keywords": '["POMIUAC INSULAR", "formulación y adopción", "objetivos y metas", '
            '"implementación o ejecución", "CORALINA", "seguimiento y '
            'evaluación", "administración sostenible", "recursos naturales '
            'renovables", "Guía Técnica Unidad Ambiental Costera Caribe '
            'Insular", "ordenación y planificación ambiental"]',
            "keywords_str": "POMIUAC INSULAR, formulación y adopción, objetivos y metas, "
            "implementación o ejecución, CORALINA, seguimiento y "
            "evaluación, administración sostenible, recursos naturales "
            "renovables, Guía Técnica Unidad Ambiental Costera Caribe "
            "Insular, ordenación y planificación ambiental",
            "norma": "Decreto 415 de 2017",
            "section_index": 6,
            "section_name": "Fases para la formulación, adopción e implementación del "
            "POMIUAC INSULAR",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Define las fases para formular y adoptar el POMIUAC INSULAR "
            "(objetivos, metas, programas, proyectos, estrategias y medidas), "
            "asigna a CORALINA la coordinación de la ejecución, y establece "
            "seguimiento y evaluación con base en una Guía Técnica.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 6,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        "text": "PARÁGRAFO. Cada una de las fases de que trata el presente artículo se desarrollará "
        "de acuerdo con lo que establezca la Guía Técnica para la Ordenación, Ordenamiento y "
        "Planificación Ambiental de la Unidad Ambiental Costera Caribe Insular en su "
        "territorio emergido y sumergido; que adoptará el Ministerio de Ambiente y "
        "Desarrollo Sostenible-",
        "metadata": {
            "articulo": "2.2.4.2.3.4",
            "articulo_titulo": "Fases para la formulación, adopción e implementación del "
            "POMIUAC INSULAR",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
            "chunk_index": 5,
            "doc_type": "normativa",
            "entities": '[{"type": "ORGANIZATION", "text": "Ministerio de Ambiente y '
            'Desarrollo Sostenible"}, {"type": "OTHER", "text": "Guía Técnica '
            "para la Ordenación, Ordenamiento y Planificación Ambiental de la "
            'Unidad Ambiental Costera Caribe Insular"}, {"type": "LOCATION", '
            '"text": "Unidad Ambiental Costera Caribe Insular"}, {"type": '
            '"OTHER", "text": "territorio emergido y sumergido"}]',
            "keywords": '["fases POMIUAC", "Guía Técnica", "ordenación y ordenamiento", '
            '"planificación ambiental", "Unidad Ambiental Costera Caribe '
            'Insular", "territorio emergido y sumergido", "Ministerio de '
            'Ambiente y Desarrollo Sostenible"]',
            "keywords_str": "fases POMIUAC, Guía Técnica, ordenación y ordenamiento, "
            "planificación ambiental, Unidad Ambiental Costera Caribe "
            "Insular, territorio emergido y sumergido, Ministerio de "
            "Ambiente y Desarrollo Sostenible",
            "norma": "Decreto 415 de 2017",
            "section_index": 6,
            "section_name": "Fases para la formulación, adopción e implementación del "
            "POMIUAC INSULAR",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Establece que las fases del POMIUAC para la Unidad Ambiental "
            "Costera Caribe Insular (territorio emergido y sumergido) se "
            "desarrollarán conforme a la Guía Técnica que adopte el Ministerio "
            "de Ambiente y Desarrollo Sostenible.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 6,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
        "text": "ARTÍCULO 2.2.4.2.3.5. Guía técnica para la ordenación, ordenamiento y planificación "
        "ambiental de la Unidad Ambiental Costera Caribe Insular. La Guía Técnica para la "
        "Ordenación, Ordenamiento y Planificación Ambiental de la Unidad Ambiental Costera "
        "Caribe Insular en su territorio emergido y sumergido* será expedida por el "
        "Ministerio de Ambiente y Desarrollo Sostenible, dentro de los tres (3) meses "
        "siguientes a la expedición del presente decreto, la cual determinará los aspectos "
        "técnicos y metodológicos necesarios para la adecuada formulación del POMIUAC   "
        "INSULAR,   garantizando   que   este   nuevo   y   único   instrumento,   recoja   "
        "y   responda   integralmente   a   la   filosofía,   principios,   bases, "
        "fundamentos,   políticas   y   finalidad   de   los   instrumentos   que   "
        "incorpora   o   subsume.",
        "metadata": {
            "articulo": "2.2.4.2.3.5",
            "articulo_titulo": "",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "chunk_index": 0,
            "doc_type": "normativa",
            "entities": '[{"type": "PERSON", "text": "Ministerio de Ambiente y Desarrollo '
            'Sostenible"}, {"type": "LOCATION", "text": "Caribe Insular"}, '
            '{"type": "OTHER", "text": "Unidad Ambiental Costera Caribe '
            'Insular"}, {"type": "OTHER", "text": "POMIUAC Insular"}, {"type": '
            '"DATE", "text": "tres (3) meses"}, {"type": "OTHER", "text": '
            '"Decreto 1076 de 2015"}, {"type": "OTHER", "text": "Artículo '
            '2.2.4.2.3.5"}]',
            "keywords": '["Guía técnica", "Unidad Ambiental Costera Caribe Insular", '
            '"ordenación y ordenamiento", "planificación ambiental", "POMIUAC '
            'Insular", "Ministerio de Ambiente y Desarrollo Sostenible", "tres '
            'meses", "aspectos técnicos y metodológicos"]',
            "keywords_str": "Guía técnica, Unidad Ambiental Costera Caribe Insular, "
            "ordenación y ordenamiento, planificación ambiental, POMIUAC "
            "Insular, Ministerio de Ambiente y Desarrollo Sostenible, tres "
            "meses, aspectos técnicos y metodológicos",
            "norma": "Decreto 415 de 2017",
            "section_index": 7,
            "section_name": "Artículo 2.2.4.2.3.5",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Establece que el Ministerio de Ambiente y Desarrollo Sostenible "
            "expedirá, en tres meses, la Guía Técnica para la ordenación y "
            "planificación ambiental de la Unidad Ambiental Costera Caribe "
            "Insular, definiendo aspectos técnicos para formular el POMIUAC "
            "Insular.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, "
        "un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera -POMIUAC- Caribe In_s9_art2-2-4-2-3-7_c0",
        "text": "ARTÍCULO 2.2.4.2.3.7. Apoyo técnico y científico. Los   Institutos   de   "
        "Investigación   de   Hidrología,   Meteorología   y   Estudios   Ambientales   "
        "-IDEAM, Marinas y Costeras 'José Benito Vives de Andreis' - C INVEMAR y de Recursos "
        "Biológicos 'Alexander von Humboldt, a que se refiere el artículo 16 de la Ley 99 de "
        "1993 y el artículo 3 del Decreto 3570 de 2011 prestarán el apoyo técnico y "
        "científico que requiera Dirección General de la Corporación para el Desarrollo "
        "Sostenible del Archipiélago de San Andrés, Providencia y Santa Catalina - CORALINA "
        "para la formulación del instrumento que en el presente decreto se establece.",
        "metadata": {
            "articulo": "2.2.4.2.3.7",
            "articulo_titulo": "Apoyo técnico y científico",
            "capitulo": "",
            "chunk_id": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el "
            "Plan de Ordenación y Manejo Integrado de la Unidad Ambiental "
            "Costera -POMIUAC- Caribe In_s9_art2-2-4-2-3-7_c0",
            "chunk_index": 0,
            "doc_type": "normativa",
            "entities": '[{"type": "ORGANIZATION", "text": "IDEAM"}, {"type": '
            '"ORGANIZATION", "text": "INVEMAR"}, {"type": "ORGANIZATION", '
            '"text": "Instituto de Recursos Biológicos \'Alexander von '
            'Humboldt\'"}, {"type": "ORGANIZATION", "text": "CORALINA"}, '
            '{"type": "ORGANIZATION", "text": "Dirección General de la '
            "Corporación para el Desarrollo Sostenible del Archipiélago de San "
            'Andrés, Providencia y Santa Catalina"}, {"type": "LAW", "text": '
            '"Ley 99 de 1993"}, {"type": "LAW", "text": "Decreto 3570 de '
            '2011"}, {"type": "LOCATION", "text": "Archipiélago de San Andrés, '
            'Providencia y Santa Catalina"}]',
            "keywords": '["apoyo técnico y científico", "IDEAM", "INVEMAR", "Instituto '
            'Humboldt", "CORALINA", "Dirección General", "formulación del '
            'instrumento", "Ley 99 de 1993", "Decreto 3570 de 2011"]',
            "keywords_str": "apoyo técnico y científico, IDEAM, INVEMAR, Instituto "
            "Humboldt, CORALINA, Dirección General, formulación del "
            "instrumento, Ley 99 de 1993, Decreto 3570 de 2011",
            "norma": "Decreto 415 de 2017",
            "section_index": 9,
            "section_name": "Apoyo técnico y científico",
            "source": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In.md",
            "summary": "Determina que IDEAM, INVEMAR y el Instituto Alexander von Humboldt "
            "prestarán apoyo técnico y científico a CORALINA, para la "
            "formulación del instrumento de planificación previsto en el "
            "decreto, dirigido por la Dirección General de CORALINA.",
            "title": "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan "
            "de Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In",
            "titulo": "",
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "Por el cual se reglamentan las Unidades Ambientales Costeras - UAC- y las comisiones "
        "conjuntas, se establecen las reglas de procedimiento y criterios para reglamentar la "
        "restricción de ciertas actividades en_s2_art3_c2",
        "text": "c) Subzona terrestre-costera o franja de tierra adentro: Es la franja comprendida "
        "desde la Línea de Marea Alta Promedio (LMAP) hasta una línea paralela localizada a "
        "2 kilómetros de distancia tierra adentro, que se fijará a partir del borde externo "
        "de:\n"
        "\n"
        "- Los ecosistemas de manglar y del bosque de transición en el Pacífico.\n"
        "- De la cota máxima de inundación de las lagunas costeras que no posee bosques de "
        "manglar asociados.\n"
        "- Las áreas declaradas como protegidas (marino-costeras) de carácter ambiental, "
        "nacionales, regionales y locales.\n"
        "- El perímetro urbano de los centros poblados costeros.\n"
        "- Los demás criterios fijados en la Guía Técnica para la Ordenación y Manejo "
        "Integrado de la Zona Costera que adoptará el Ministerio de Ambiente y Desarrollo "
        "Sostenible.\n"
        "\n"
        "2. Zona Costera Insular: Es la unidad espacial que corresponde al Departamento "
        "Archipiélago de San Andrés, Providencia y Santa Catalina, incluyendo su territorio "
        "emergido y sumergido.",
        "metadata": {
            "articulo": "3",
            "articulo_titulo": "Tipos de Zonas Costeras",
            "capitulo": "",
            "chunk_id": "Por el cual se reglamentan las Unidades Ambientales Costeras - "
            "UAC- y las comisiones conjuntas, se establecen las reglas de "
            "procedimiento y criterios para reglamentar la restricción de "
            "ciertas actividades en_s2_art3_c2",
            "chunk_index": 2,
            "doc_type": "normativa",
            "entities": '[{"type": "LOCATION", "text": "Departamento Archipiélago de San '
            'Andrés, Providencia y Santa Catalina"}, {"type": "LOCATION", '
            '"text": "Pacífico"}, {"type": "LOCATION", "text": "centros '
            'poblados costeros"}, {"type": "OTHER", "text": "Línea de Marea '
            'Alta Promedio (LMAP)"}, {"type": "OTHER", "text": "cota máxima de '
            'inundación"}, {"type": "OTHER", "text": "Guía Técnica para la '
            'Ordenación y Manejo Integrado de la Zona Costera"}, {"type": '
            '"ORGANIZATION", "text": "Ministerio de Ambiente y Desarrollo '
            'Sostenible"}, {"type": "OTHER", "text": "ecosistemas de manglar"}, '
            '{"type": "OTHER", "text": "bosque de transición"}, {"type": '
            '"OTHER", "text": "lagunas costeras"}, {"type": "OTHER", "text": '
            '"áreas declaradas como protegidas (marino-costeras)"}, {"type": '
            '"OTHER", "text": "perímetro urbano"}]',
            "keywords": '["subzona terrestre-costera", "Línea de Marea Alta Promedio", '
            '"zona costera insular", "2 kilómetros tierra adentro", '
            '"ecosistemas de manglar", "cota máxima de inundación", "áreas '
            'protegidas marino-costeras", "perímetro urbano", "Guía Técnica '
            'ordenación zona costera"]',
            "keywords_str": "subzona terrestre-costera, Línea de Marea Alta Promedio, zona "
            "costera insular, 2 kilómetros tierra adentro, ecosistemas de "
            "manglar, cota máxima de inundación, áreas protegidas "
            "marino-costeras, perímetro urbano, Guía Técnica ordenación "
            "zona costera",
            "section_index": 2,
            "section_name": "Tipos de Zonas Costeras",
            "source": "Por el cual se reglamentan las Unidades Ambientales Costeras - UAC- "
            "y las comisiones conjuntas, se establecen las reglas de "
            "procedimiento y criterios para reglamentar la restricción de "
            "ciertas actividades en.md",
            "summary": "El artículo define la “subzona terrestre-costera” como una franja "
            "desde la Línea de Marea Alta Promedio hasta 2 km tierra adentro "
            "según límites de ecosistemas, cota de inundación, áreas protegidas, "
            "perímetros urbanos y la Guía Técnica; además define la Zona Costera "
            "Insular del archipiélago.",
            "title": "Por el cual se reglamentan las Unidades Ambientales Costeras - UAC- y "
            "las comisiones conjuntas, se establecen las reglas de procedimiento y "
            "criterios para reglamentar la restricción de ciertas actividades en",
            "titulo": "",
            "total_chunks_in_section": 3,
        },
    },
    {
        "id": "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)_s198_art5-3-4-5_c2",
        "text": "4. Licencia ambiental o Plan de Manejo Ambiental, según sea el caso, expedida\n"
        "por la Autoridad Ambiental competente, a nombre del nuevo titular de la\n"
        "autorización y/o concesión .\n"
        "PARÁGRAFO 1. Las concesiones, permisos y autorizaciones otorgadas por la\n"
        "Dirección General Marítima son  intuito personae  y por ningún motivo puede ser\n"
        "objeto de negocio jurídico alguno.\n"
        "PARÁGRAFO 2. La Capitanía de Puerto emitirá un concepto respecto al\n"
        "cumplimiento de las obligaciones para el análisis de la solicitud.\n"
        "PARÁGRAFO 3. Recibida la solicitud, la Dirección General Marítima (DIMAR) hará\n"
        "la verificación de carencia de informes por tráfico de estupefacientes\n"
        "relacionada con comportamientos referid os a delitos de tráfico de\n"
        "estupefacientes y conexos, lavado de activos, testaferrato y enriquecimiento\n"
        "ilícito, así como frente a procesos de extinción del derecho de dominio.\n"
        "Tratándose de personas jurídicas, la verificación de carencia de informes por",
        "metadata": {
            "articulo": "5.3.4.5",
            "articulo_titulo": "Modificación del titular de la concesión, permiso o autorización",
            "capitulo": "",
            "chunk_id": "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)_s198_art5-3-4-5_c2",
            "chunk_index": 2,
            "doc_type": "normativa",
            "entities": '[{"type": "ORGANIZATION", "text": "Dirección General Marítima '
            '(DIMAR)"}, {"type": "ORGANIZATION", "text": "Capitanía de '
            'Puerto"}, {"type": "ORGANIZATION", "text": "Autoridad Ambiental '
            'competente"}, {"type": "OTHER", "text": "licencia ambiental"}, '
            '{"type": "OTHER", "text": "Plan de Manejo Ambiental (PMA)"}, '
            '{"type": "OTHER", "text": "tráfico de estupefacientes y conexos"}, '
            '{"type": "OTHER", "text": "lavado de activos"}, {"type": "OTHER", '
            '"text": "testaferrato"}, {"type": "OTHER", "text": '
            '"enriquecimiento ilícito"}, {"type": "OTHER", "text": "extinción '
            'del derecho de dominio"}]',
            "keywords": '["licencia ambiental", "Plan de Manejo Ambiental (PMA)", "nuevo '
            'titular", "concesiones intuito personae", "prohibición de negocio '
            'jurídico", "concepto Capitanía de Puerto", "verificación carencia '
            'de informes", "tráfico de estupefacientes", "lavado de activos", '
            '"extinción del derecho de dominio"]',
            "keywords_str": "licencia ambiental, Plan de Manejo Ambiental (PMA), nuevo "
            "titular, concesiones intuito personae, prohibición de negocio "
            "jurídico, concepto Capitanía de Puerto, verificación carencia "
            "de informes, tráfico de estupefacientes, lavado de activos, "
            "extinción del derecho de dominio",
            "section_index": 198,
            "section_name": "Modificación del titular de la concesión, permiso o autorización",
            "source": "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103).md",
            "summary": "Establece que, para el cambio del titular de una "
            "concesión/permiso/autorización, debe existir licencia ambiental o "
            "PMA expedida a nombre del nuevo titular; además, fija que dichos "
            "actos son intuito personae, exige concepto de Capitanía y "
            "verificaciones DIMAR sobre carencia de informes por delitos conexos "
            "y procesos de extinción del dominio.",
            "title": "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)",
            "titulo": "TÍTULO 4",
            "total_chunks_in_section": 4,
        },
    },
    {
        "id": "Por medio del cual se expide el Decreto Único Reglamentario del Sector Comercio, "
        "Industria y Turismo_s2_art2-2-4-8-1-3_c2",
        "text": "Estudios de capacidad: estudios realizados por el administrador del atractivo "
        "turístico con el fin de establecer la capacidad del atractivo turístico.\n"
        "\n"
        "Factores de corrección: aspectos susceptibles de valoración cuantitativa que "
        "intervienen en los procedimientos técnicos de determinación de la capacidad del "
        "atractivo turístico y que recaen sobre las condiciones físicas, ambientales, "
        "biológicas y sociales del atractivo turístico.\n"
        "\n"
        "Plan de mejoramiento: documento elaborado por el administrador del atractivo "
        "turístico con acciones para mejorar la sostenibilidad del atractivo o para "
        "incrementar las medidas de manejo del mismo.\n"
        "\n"
        "Plan de monitoreo: plan adoptado por la autoridad competente para medir "
        "periódicamente los impactos negativos ocasionados por la cantidad de visitantes que "
        "ingresan a un atractivo turístico y por sus comportamientos en el mismo, así como "
        "para monitorear el cumplimiento de su capacidad determinada por el estudio de "
        "capacidad del atractivo.",
        "metadata": {
            "articulo": "2.2.4.8.1.3",
            "articulo_titulo": "Definiciones",
            "capitulo": "",
            "chunk_id": "Por medio del cual se expide el Decreto Único Reglamentario del "
            "Sector Comercio, Industria y Turismo_s2_art2-2-4-8-1-3_c2",
            "chunk_index": 2,
            "doc_type": "normativa",
            "entities": '[{"type": "OTHER", "text": "Decreto Único Reglamentario del Sector '
            'Comercio, Industria y Turismo"}, {"type": "OTHER", "text": '
            '"2.2.4.8.1.3"}, {"type": "OTHER", "text": "autoridad competente"}, '
            '{"type": "OTHER", "text": "administrador del atractivo '
            'turístico"}, {"type": "OTHER", "text": "atractivo turístico"}]',
            "keywords": '["estudio de capacidad", "capacidad del atractivo turístico", '
            '"factores de corrección", "plan de mejoramiento", "plan de '
            'monitoreo", "sostenibilidad turística", "medición de impactos", '
            '"autoridad competente", "condiciones físicas y ambientales"]',
            "keywords_str": "estudio de capacidad, capacidad del atractivo turístico, "
            "factores de corrección, plan de mejoramiento, plan de "
            "monitoreo, sostenibilidad turística, medición de impactos, "
            "autoridad competente, condiciones físicas y ambientales",
            "section_index": 2,
            "section_name": "Definiciones",
            "source": "Por medio del cual se expide el Decreto Único Reglamentario del "
            "Sector Comercio, Industria y Turismo.md",
            "summary": "Define conceptos clave para la gestión de atractivos turísticos: "
            "estudios de capacidad, factores de corrección, plan de mejoramiento "
            "y plan de monitoreo, estableciendo finalidades y alcances para "
            "determinar y controlar la capacidad y sus impactos.",
            "title": "Por medio del cual se expide el Decreto Único Reglamentario del "
            "Sector Comercio, Industria y Turismo",
            "titulo": "",
            "total_chunks_in_section": 3,
        },
    },
    {
        "id": "Por medio del cual se implementa el Reglamento de Playas del Distrito Portuario, "
        "Logístico, Industrial, Turístico y Comercial de Turbo – Antioquia_s20_art16_c19",
        "text": "- h. Plan de gestión del riesgo o plan de emergencia y contingencias: La Alcaldía "
        "Distrital de Turbo-Antioquia deberá diseñar un plan de gestión del riesgo o plan de "
        "emergencia y contingencia para las playas del Distrito. Este plan de gestión podrá "
        "ser general o particular, según lo estime el Comité Local de Organización de "
        "Playas. El plan de gestión del riesgo deberá articularse dentro del plan de gestión "
        "de la ciudad y será de conocimiento de todas las autoridades pertinentes, "
        "socializándose adecuadamente con la comunidad de la playa.",
        "metadata": {
            "articulo": "17",
            "articulo_titulo": "",
            "capitulo": "CAPÍTULO VI.",
            "chunk_id": "Por medio del cual se implementa el Reglamento de Playas del "
            "Distrito Portuario, Logístico, Industrial, Turístico y Comercial "
            "de Turbo – Antioquia_s20_art16_c19",
            "chunk_index": 11,
            "doc_type": "normativa",
            "entities": '[{"type": "PERSON", "text": "Comité Local de Organización de '
            'Playas"}, {"type": "LOCATION", "text": "Alcaldía Distrital de '
            'Turbo (Antioquia)"}, {"type": "LOCATION", "text": '
            '"Turbo-Antioquia"}, {"type": "LOCATION", "text": "playas del '
            'Distrito"}, {"type": "OTHER", "text": "Plan de gestión de la '
            'ciudad"}, {"type": "OTHER", "text": "plan de gestión del riesgo o '
            'plan de emergencia y contingencias"}]',
            "keywords": '["plan de gestión del riesgo", "plan de emergencia y '
            'contingencias", "Alcaldía Distrital de Turbo", "Comité Local de '
            'Organización de Playas", "articulación con plan de la ciudad", '
            '"socialización con la comunidad", "gestión del riesgo en playas", '
            '"autoridades pertinentes"]',
            "keywords_str": "plan de gestión del riesgo, plan de emergencia y "
            "contingencias, Alcaldía Distrital de Turbo, Comité Local de "
            "Organización de Playas, articulación con plan de la ciudad, "
            "socialización con la comunidad, gestión del riesgo en playas, "
            "autoridades pertinentes",
            "norma": "Decreto 1431 de 2024",
            "section_index": 21,
            "section_name": "Artículo 17",
            "source": "Por medio del cual se implementa el Reglamento de Playas del "
            "Distrito Portuario, Logístico, Industrial, Turístico y Comercial "
            "de Turbo – Antioquia.md",
            "summary": "Establece que la Alcaldía Distrital de Turbo debe diseñar un plan "
            "de gestión del riesgo o de emergencia y contingencias para las "
            "playas; puede ser general o particular según el Comité Local, y "
            "debe articularse al plan de la ciudad, socializándose con la "
            "comunidad y compartiéndose con autoridades.",
            "title": "Por medio del cual se implementa el Reglamento de Playas del Distrito "
            "Portuario, Logístico, Industrial, Turístico y Comercial de Turbo – "
            "Antioquia",
            "titulo": "",
            "total_chunks_in_section": 20,
        },
    },
    {
        "id": "fixture_prd.md-identity",
        "text": "Se establece el Plan de Restauración de Dunas -PRD-, como instrumento de "
        "ordenación.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_prd.md",
            "norma": "Decreto sintético 901 de 2099",
            "chunk_id": "fixture_prd.md-identity",
            "id": "fixture_prd.md-identity",
        },
    },
    {
        "id": "fixture_prd.md-related",
        "text": "Fases del PRD. Se establecerán objetivos y programas para su implementación.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_prd.md",
            "norma": "Decreto sintético 901 de 2099",
            "chunk_id": "fixture_prd.md-related",
            "id": "fixture_prd.md-related",
        },
    },
    {
        "id": "fixture_prd.md-proof",
        "text": "La formulación del PRD estará a cargo de la Oficina de Restauración Litoral y su "
        "adopción estará en cabeza de el Consejo de Restauración.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_prd.md",
            "norma": "Decreto sintético 901 de 2099",
            "chunk_id": "fixture_prd.md-proof",
            "id": "fixture_prd.md-proof",
        },
    },
    {
        "id": "fixture_pmhu.md-identity",
        "text": "Se establece el Plan de Manejo de Humedales Urbanos -PMHU-, como instrumento de "
        "ordenación.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_pmhu.md",
            "norma": "Decreto sintético 902 de 2099",
            "chunk_id": "fixture_pmhu.md-identity",
            "id": "fixture_pmhu.md-identity",
        },
    },
    {
        "id": "fixture_pmhu.md-related",
        "text": "Fases del PMHU. Se establecerán objetivos y programas para su implementación.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_pmhu.md",
            "norma": "Decreto sintético 902 de 2099",
            "chunk_id": "fixture_pmhu.md-related",
            "id": "fixture_pmhu.md-related",
        },
    },
    {
        "id": "fixture_pmhu.md-proof",
        "text": "La formulación del PMHU estará a cargo de la Dirección de Humedales y su adopción "
        "estará en cabeza de la Junta de Conservación.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_pmhu.md",
            "norma": "Decreto sintético 902 de 2099",
            "chunk_id": "fixture_pmhu.md-proof",
            "id": "fixture_pmhu.md-proof",
        },
    },
    {
        "id": "fixture_prd-coordination",
        "text": "Corresponde a la Agencia de Obras coordinar la ejecución del PRD; sin perjuicio de "
        "las competencias de otras autoridades.",
        "metadata": {
            "doc_type": "normativa",
            "source": "fixture_prd.md",
            "norma": "Decreto sintético 901 de 2099",
            "chunk_id": "fixture_prd-coordination",
            "id": "fixture_prd-coordination",
        },
    },
    {
        "id": "syn-guia",
        "text": "ARTÍCULO 5. Una guía establecerá aspectos técnicos y metodológicos para la adecuada "
        "formulación del PMI BAHIA.",
        "metadata": {
            "id": "syn-guia",
            "chunk_id": "syn-guia",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "5",
            "articulo_titulo": "Guía técnica",
            "section_index": 5,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-preambulo",
        "text": "Se requiere un instrumento de ordenación ambiental para la zona costera y las fases "
        "del PMI BAHIA.",
        "metadata": {
            "id": "syn-preambulo",
            "chunk_id": "syn-preambulo",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "2",
            "articulo_titulo": "Consideraciones",
            "section_index": 2,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-fases",
        "text": "ARTÍCULO 4. En la formulación del PMI BAHIA se fijarán objetivos, metas y programas "
        "para el manejo de los recursos.",
        "metadata": {
            "id": "syn-fases",
            "chunk_id": "syn-fases",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "4",
            "articulo_titulo": "Fases",
            "section_index": 4,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-coordinacion",
        "text": "ARTÍCULO 6. Corresponde al Instituto Costero Alfa coordinar la ejecución del PMI "
        "BAHIA.",
        "metadata": {
            "id": "syn-coordinacion",
            "chunk_id": "syn-coordinacion",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "6",
            "articulo_titulo": "Coordinación de ejecución",
            "section_index": 6,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-identidad",
        "text": "ARTÍCULO 1. Se establece el Plan de Manejo Integral de la Zona Costera Bahía Clara "
        "—PMI BAHIA— como instrumento de ordenación costera.",
        "metadata": {
            "id": "syn-identidad",
            "chunk_id": "syn-identidad",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "1",
            "articulo_titulo": "Objeto",
            "section_index": 1,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. Formulación y adopción del PMI BAHIA. La formulación del PMI BAHIA "
        "estará a cargo de la Dirección Técnica del Instituto Costero Alfa y su adopción "
        "estará en cabeza del Consejo de dicho instituto.",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-identidad-otra",
        "text": "ARTÍCULO 1. Se establece el Plan de Manejo Integral de la Zona Costera Bahía Clara "
        "—PMI BAHIA— como instrumento de ordenación costera.",
        "metadata": {
            "id": "syn-identidad-otra",
            "chunk_id": "syn-identidad-otra",
            "doc_type": "normativa",
            "source": "sintetico-instituto-beta.md",
            "norma": "Decreto 72 de 2041",
            "articulo": "1",
            "articulo_titulo": "Objeto",
            "section_index": 1,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion-otra",
        "text": "ARTÍCULO 3. Formulación y adopción del PMI BAHIA. La formulación del PMI BAHIA "
        "estará a cargo de la Dirección Técnica del Instituto Costero Beta y su adopción "
        "estará en cabeza del Consejo de dicho instituto.",
        "metadata": {
            "id": "syn-atribucion-otra",
            "chunk_id": "syn-atribucion-otra",
            "doc_type": "normativa",
            "source": "sintetico-instituto-beta.md",
            "norma": "Decreto 72 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-identidad-alias-duplicado",
        "text": "ARTÍCULO 7. Se establece el Plan de Recuperación de la Zona Costera Punta Nítida "
        "—PMI BAHIA—.",
        "metadata": {
            "id": "syn-identidad-alias-duplicado",
            "chunk_id": "syn-identidad-alias-duplicado",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "7",
            "articulo_titulo": "Objeto",
            "section_index": 7,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. La formulación del PMI BAHIA seguirá las fases y criterios de la guía. "
        "El Instituto Costero Alfa coordinará su ejecución.",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. Formulación y adopción del PMI BAHIA. La formulación del PMI BAHIA "
        "estará a cargo de la Dirección Técnica del Instituto Costero Alfa y su adopción "
        "estará en cabeza del Consejo de dicho instituto.",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "normativa",
            "source": "otra-fuente-no-vinculada.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. Formulación y adopción del PMI BAHIA. La formulación del PMI BAHIA "
        "estará a cargo de la Dirección Técnica del Instituto Costero Alfa. La formulación "
        "del PMI BAHIA estará a cargo de la Secretaría Costera Beta.",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. Formulación y adopción del PMI BAHIA. La formulación del PMI BAHIA "
        "estará a cargo de",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
            "summary": "La Dirección Técnica del Instituto Costero Alfa formula el plan.",
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. Formulación y adopción del PMI BAHIA. La formulación del PMI BAHIA "
        "estará a cargo de la Dirección Técnica del Instituto Costero Alfa y su adopción "
        "estará en cabeza del Consejo de dicho instituto.",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "jurisprudencia",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
    {
        "id": "syn-atribucion",
        "text": "ARTÍCULO 3. Fases del PMI BAHIA. Respecto del Plan de Ordenamiento de la Zona "
        "Interior, su adopción estará en cabeza de la Junta Regional Beta.",
        "metadata": {
            "id": "syn-atribucion",
            "chunk_id": "syn-atribucion",
            "doc_type": "normativa",
            "source": "sintetico-instituto-alfa.md",
            "norma": "Decreto 71 de 2041",
            "articulo": "3",
            "articulo_titulo": "Formulación y adopción del PMI BAHIA",
            "section_index": 3,
            "chunk_index": 0,
            "total_chunks_in_section": 1,
        },
    },
)

# Expected selections are test oracles, never inputs to the production selector.
_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "R01_Q2_FORMULAR",
        "evidence_kind": "actual_capture",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Y quién debe formular el Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "history": [
            {
                "role": "user",
                "content": "Contexto de prueba: me refiero al Plan de Ordenación y Manejo "
                "Integrado de la Unidad Ambiental Costera Caribe Insular.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto "
            "1076 de 2015, un Capítulo 3 en el que se establece el Plan de Ordenación "
            "y Manejo Integrado de la Unidad Ambiental Costera -POMIUAC- Caribe "
            "In_s5_art2-2-4-2-3-3_c0",
        ),
        "preserve_selected": False,
        "actor_quote": "La formulación del POMIUAC INSULAR, estará a cargo de la Dirección General",
    },
    {
        "case_id": "R02_Q1_ADOPTAR_NOOP",
        "evidence_kind": "actual_Q1_DOM_order",
        "question": "¿Qué autoridad debe adoptar ese Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera Caribe Insular?",
        "standalone_question": "¿Qué autoridad debe adoptar ese Plan de Ordenación y Manejo "
        "Integrado de la Unidad Ambiental Costera Caribe Insular?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (23, 27),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s5_art2-2-4-2-3-3_c0",
        ),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": "su adopción estará en cabeza del consejo Directivo de dicha entidad",
    },
    {
        "case_id": "R03_ADOPTAR_CANDIDATOS_REALES",
        "evidence_kind": "counterfactual_question_real_candidates",
        "question": "¿Quién debe adoptar el Plan de Ordenación y Manejo Integrado de la Unidad "
        "Ambiental Costera Caribe Insular?",
        "standalone_question": "¿Quién debe adoptar el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera Caribe Insular?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto "
            "1076 de 2015, un Capítulo 3 en el que se establece el Plan de Ordenación "
            "y Manejo Integrado de la Unidad Ambiental Costera -POMIUAC- Caribe "
            "In_s5_art2-2-4-2-3-3_c0",
        ),
        "preserve_selected": False,
        "actor_quote": "su adopción estará en cabeza del consejo Directivo de dicha entidad",
    },
    {
        "case_id": "R04_COORDINAR_EJECUCION_NOOP",
        "evidence_kind": "counterfactual_question_real_candidates",
        "question": "¿Quién debe coordinar la ejecución del Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "standalone_question": "¿Quién debe coordinar la ejecución del Plan de Ordenación y Manejo "
        "Integrado de la Unidad Ambiental Costera Caribe Insular?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": "Corresponde a CORALINA coordinar la ejecución del POMIUAC INSULAR",
    },
    {
        "case_id": "R05_EJECUTAR_NO_ES_COORDINAR",
        "evidence_kind": "counterfactual_question_real_candidates",
        "question": "¿Quién debe ejecutar el Plan de Ordenación y Manejo Integrado de la Unidad "
        "Ambiental Costera Caribe Insular?",
        "standalone_question": "¿Quién debe ejecutar el Plan de Ordenación y Manejo Integrado de la "
        "Unidad Ambiental Costera Caribe Insular?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "R06_FORMULAR_SIN_PRUEBA_EN_POOL",
        "evidence_kind": "removed_target_fixture",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Y quién debe formular el Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "history": [
            {
                "role": "user",
                "content": "Contexto de prueba: me refiero al Plan de Ordenación y Manejo "
                "Integrado de la Unidad Ambiental Costera Caribe Insular.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "R07_FILTRO_JURISPRUDENCIA",
        "evidence_kind": "original_filter_fixture",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Y quién debe formular el Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "history": [
            {
                "role": "user",
                "content": "Contexto de prueba: me refiero al Plan de Ordenación y Manejo "
                "Integrado de la Unidad Ambiental Costera Caribe Insular.",
            }
        ],
        "original_doc_types": ["jurisprudencia"],
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "R08_FILTRO_NORMATIVA",
        "evidence_kind": "original_filter_fixture",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Y quién debe formular el Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "history": [
            {
                "role": "user",
                "content": "Contexto de prueba: me refiero al Plan de Ordenación y Manejo "
                "Integrado de la Unidad Ambiental Costera Caribe Insular.",
            }
        ],
        "original_doc_types": ["normativa"],
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto "
            "1076 de 2015, un Capítulo 3 en el que se establece el Plan de Ordenación "
            "y Manejo Integrado de la Unidad Ambiental Costera -POMIUAC- Caribe "
            "In_s5_art2-2-4-2-3-3_c0",
        ),
        "preserve_selected": False,
        "actor_quote": "La formulación del POMIUAC INSULAR, estará a cargo de la Dirección General",
    },
    {
        "case_id": "R09_OTRA_NORMA_MONITOREO_METADATO_VACIO",
        "evidence_kind": "independent_Gold_A_reserve",
        "question": "¿Quién adopta el Plan de monitoreo del atractivo turístico?",
        "standalone_question": "¿Quién adopta el Plan de monitoreo del atractivo turístico?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (35,),
        "current_selected": (),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": "Plan de monitoreo: plan adoptado por la autoridad competente",
    },
    {
        "case_id": "R10_OTRA_NORMA_MEJORAMIENTO_GRAMATICA_FUERA",
        "evidence_kind": "independent_Gold_A_reserve",
        "question": "¿Quién elabora el Plan de mejoramiento del atractivo turístico?",
        "standalone_question": "¿Quién elabora el Plan de mejoramiento del atractivo turístico?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (35,),
        "current_selected": (),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": "Plan de mejoramiento: documento elaborado por el administrador del atractivo "
        "turístico",
    },
    {
        "case_id": "R11_OTRO_PLAN_DISENAR_NO_FORMULAR",
        "evidence_kind": "independent_Gold_A_negative",
        "question": "¿Quién debe formular el plan de gestión del riesgo de las playas de Turbo?",
        "standalone_question": "¿Quién debe formular el plan de gestión del riesgo de las playas de "
        "Turbo?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (36,),
        "current_selected": (),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "R12_OTRO_PLAN_DISENAR_FUERA_ALCANCE",
        "evidence_kind": "independent_Gold_A_reserve",
        "question": "¿Quién deberá diseñar el plan de gestión del riesgo de las playas de Turbo?",
        "standalone_question": "¿Quién deberá diseñar el plan de gestión del riesgo de las playas de "
        "Turbo?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (36,),
        "current_selected": (),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": "La Alcaldía Distrital de Turbo-Antioquia deberá diseñar un plan de gestión "
        "del riesgo",
    },
    {
        "case_id": "S01_FORMULAR",
        "evidence_kind": "synthetic_positive_unseen_plan",
        "question": "¿Quién debe formular el Plan de Restauración de Dunas?",
        "standalone_question": "¿Quién debe formular el Plan de Restauración de Dunas?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (37, 38, 39),
        "current_selected": ("fixture_prd.md-identity", "fixture_prd.md-related"),
        "promote_ids": ("fixture_prd.md-proof",),
        "preserve_selected": False,
        "actor_quote": "La formulación del PRD estará a cargo de la Oficina de Restauración Litoral",
    },
    {
        "case_id": "S01_ADOPTAR",
        "evidence_kind": "synthetic_positive_unseen_plan",
        "question": "¿Quién debe adoptar el Plan de Restauración de Dunas?",
        "standalone_question": "¿Quién debe adoptar el Plan de Restauración de Dunas?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (37, 38, 39),
        "current_selected": ("fixture_prd.md-identity", "fixture_prd.md-related"),
        "promote_ids": ("fixture_prd.md-proof",),
        "preserve_selected": False,
        "actor_quote": "su adopción estará en cabeza de el Consejo de Restauración",
    },
    {
        "case_id": "S02_FORMULAR",
        "evidence_kind": "synthetic_positive_unseen_plan",
        "question": "¿Quién debe formular el Plan de Manejo de Humedales Urbanos?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo de Humedales Urbanos?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (40, 41, 42),
        "current_selected": ("fixture_pmhu.md-identity", "fixture_pmhu.md-related"),
        "promote_ids": ("fixture_pmhu.md-proof",),
        "preserve_selected": False,
        "actor_quote": "La formulación del PMHU estará a cargo de la Dirección de Humedales",
    },
    {
        "case_id": "S02_ADOPTAR",
        "evidence_kind": "synthetic_positive_unseen_plan",
        "question": "¿Quién debe adoptar el Plan de Manejo de Humedales Urbanos?",
        "standalone_question": "¿Quién debe adoptar el Plan de Manejo de Humedales Urbanos?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (40, 41, 42),
        "current_selected": ("fixture_pmhu.md-identity", "fixture_pmhu.md-related"),
        "promote_ids": ("fixture_pmhu.md-proof",),
        "preserve_selected": False,
        "actor_quote": "su adopción estará en cabeza de la Junta de Conservación",
    },
    {
        "case_id": "S03_COORDINACION_EXPLICITA",
        "evidence_kind": "synthetic_positive_unseen_plan",
        "question": "¿Quién debe coordinar la ejecución del Plan de Restauración de Dunas?",
        "standalone_question": "¿Quién debe coordinar la ejecución del Plan de Restauración de "
        "Dunas?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (37, 38, 43),
        "current_selected": ("fixture_prd.md-identity", "fixture_prd.md-related"),
        "promote_ids": ("fixture_prd-coordination",),
        "preserve_selected": False,
        "actor_quote": "Corresponde a la Agencia de Obras coordinar la ejecución del PRD",
    },
    {
        "case_id": "S04_EJECUCION_NO_COORDINACION",
        "evidence_kind": "synthetic_negative",
        "question": "¿Quién debe ejecutar el Plan de Restauración de Dunas?",
        "standalone_question": "¿Quién debe ejecutar el Plan de Restauración de Dunas?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (37, 38, 43),
        "current_selected": ("fixture_prd.md-identity", "fixture_prd.md-related"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A01",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49, 50, 51),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A02",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49, 52),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A03",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 53),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A04",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": ["jurisprudencia"],
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A05",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 54),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A06",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 55),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A07",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Compara el Plan de Manejo Integral de la Zona Costera Bahía Clara y "
                "el Plan de Recuperación de la Zona Costera Punta Nítida.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A08",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A09",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Cumbre Inexistente?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Cumbre "
                "Inexistente.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A10",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 56),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A11",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Quién NO debe formular el Plan de Manejo Integral de la Zona Costera Bahía "
        "Clara?",
        "standalone_question": "¿Quién NO debe formular el Plan de Manejo Integral de la Zona "
        "Costera Bahía Clara?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A12",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Quién debe ejecutar el Plan de Manejo Integral de la Zona Costera Bahía Clara?",
        "standalone_question": "¿Quién debe ejecutar el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A13",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 3,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A14",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-identidad", "syn-atribucion", "syn-guia", "syn-fases"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A15",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Quién debe formular el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [
            {
                "role": "user",
                "content": "Me refiero al Plan de Manejo Integral de la Zona Costera Bahía Clara.",
            }
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 57),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A16",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Qué autoridad debe adoptar el Plan de Manejo Integral de la Zona Costera Bahía "
        "Clara?",
        "standalone_question": "¿Qué autoridad debe adoptar el Plan de Manejo Integral de la Zona "
        "Costera Bahía Clara?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 49),
        "current_selected": ("syn-identidad", "syn-atribucion", "syn-guia", "syn-fases"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "A17",
        "evidence_kind": "adversarial_synthetic",
        "question": "¿Quién debe adoptar el Plan de Manejo Integral de la Zona Costera Bahía Clara?",
        "standalone_question": "¿Quién debe adoptar el Plan de Manejo Integral de la Zona Costera "
        "Bahía Clara?",
        "history": [],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (44, 45, 46, 47, 48, 58),
        "current_selected": ("syn-guia", "syn-preambulo", "syn-fases", "syn-coordinacion"),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
    {
        "case_id": "H01_USUARIO_IDENTIFICA_PLAN_AI_NO_AUTORIDAD",
        "evidence_kind": "synthesized_visible_not_checkpoint_or_SQL",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Y quién debe formular el Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "history": [
            {
                "role": "user",
                "content": "¿Qué autoridad debe adoptar ese Plan de Ordenación y Manejo "
                "Integrado de la Unidad Ambiental Costera Caribe Insular?",
            },
            {
                "role": "assistant",
                "content": "La autoridad que debe adoptar el Plan de Ordenación y Manejo "
                "Integrado de la Unidad Ambiental Costera Caribe Insular (POMIUAC "
                "INSULAR) es el Consejo Directivo de CORALINA [doc2].",
            },
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto "
            "1076 de 2015, un Capítulo 3 en el que se establece el Plan de Ordenación "
            "y Manejo Integrado de la Unidad Ambiental Costera -POMIUAC- Caribe "
            "In_s5_art2-2-4-2-3-3_c0",
        ),
        "preserve_selected": False,
        "actor_quote": "La formulación del POMIUAC INSULAR, estará a cargo de la Dirección General",
    },
    {
        "case_id": "H02_PLAN_SOLO_EN_ASSISTANT",
        "evidence_kind": "synthetic_negative_AI_only_referent",
        "question": "¿Y quién debe formularlo?",
        "standalone_question": "¿Y quién debe formular el Plan de Ordenación y Manejo Integrado de "
        "la Unidad Ambiental Costera Caribe Insular?",
        "history": [
            {"role": "user", "content": "Quiero consultar ese instrumento."},
            {
                "role": "assistant",
                "content": "Podrías referirte al Plan de Ordenación y Manejo Integrado de la "
                "Unidad Ambiental Costera Caribe Insular. Su adopción corresponde al "
                "Consejo Directivo de CORALINA [doc2].",
            },
        ],
        "original_doc_types": None,
        "k": 4,
        "candidate_pool": (
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
        ),
        "current_selected": (
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s7_art2-2-4-2-3-5_c0",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s1_c13",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c4",
            "Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del "
            "Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de "
            "Ordenación y Manejo Integrado de la Unidad Ambiental Costera "
            "-POMIUAC- Caribe In_s6_art2-2-4-2-3-4_c5",
        ),
        "promote_ids": None,
        "preserve_selected": True,
        "actor_quote": None,
    },
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Plan attribution contracts must not connect to services")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def _materialize(case: dict[str, Any]):
    pool = []
    for index in case["candidate_pool"]:
        row = _DOCUMENT_ROWS[index]
        metadata = copy.deepcopy(row["metadata"])
        # BM25 may add metadata.id while leaving Document.id unset; the REST
        # vector path can carry the same identifier in Document.id instead.
        pool.append(
            Document(
                id=None if "id" in metadata else row["id"],
                page_content=row["text"],
                metadata=metadata,
            )
        )
    by_id = {doc.metadata.get("chunk_id", doc.id): doc for doc in pool}
    current = [by_id[ident] for ident in case["current_selected"]]
    verified = tuple(doc.model_copy(deep=True) for doc in pool)
    return pool, current, verified


def _invoke(case, pool, current, verified):
    # The module is introduced in P2. Collecting this contract file beforehand
    # must not turn a missing implementation into a misleading collection error.
    from rag.core.plan_attribution_context import select_plan_attribution_context

    return select_plan_attribution_context(
        question=case["question"],
        history=copy.deepcopy(case["history"]),
        standalone_question=case["standalone_question"],
        original_doc_types=copy.deepcopy(case["original_doc_types"]),
        current_selected=current,
        candidate_pool=pool,
        verified_documents=verified,
        k=case["k"],
    )


def _q2():
    return next(case for case in _CASES if case["case_id"] == "R01_Q2_FORMULAR")


def _decisive(pool, kind):
    suffix = "_s1_c13" if kind == "identity" else "_s5_art2-2-4-2-3-3_c0"
    return next(doc for doc in pool if doc.metadata["chunk_id"].endswith(suffix))


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["case_id"])
def test_preregistered_selection_contracts(case):
    pool, current, verified = _materialize(case)
    before_current = list(current)
    before_pool = [doc.model_dump() for doc in pool]
    before_snapshot = [doc.model_dump() for doc in verified]

    selected = _invoke(case, pool, current, verified)

    if case["preserve_selected"]:
        # Includes real Q1, whose wording may deliberately fall outside the
        # narrow grammar: preservation is not semantic recognition of its act.
        assert selected is current
    else:
        assert selected is not current
        assert [doc.metadata["chunk_id"] for doc in selected[: len(case["promote_ids"])]] == list(
            case["promote_ids"]
        )
        remaining = [
            doc for doc in before_current if doc.metadata["chunk_id"] not in case["promote_ids"]
        ]
        expected_tail = remaining[: case["k"] - len(case["promote_ids"])]
        assert len(selected) == len(case["promote_ids"]) + len(expected_tail)
        assert all(
            actual is expected
            for actual, expected in zip(
                selected[len(case["promote_ids"]) :], expected_tail, strict=True
            )
        )
        if case["actor_quote"]:
            assert any(
                case["actor_quote"].casefold() in doc.page_content.casefold() for doc in selected
            )
    if case["k"] == 4:
        assert len(selected) <= 4
    assert len({doc.metadata["chunk_id"] for doc in selected}) == len(selected)
    assert all(any(doc is original for original in pool) for doc in selected)
    assert len(current) == len(before_current)
    assert all(actual is expected for actual, expected in zip(current, before_current, strict=True))
    assert [doc.model_dump() for doc in pool] == before_pool
    assert [doc.model_dump() for doc in verified] == before_snapshot


@pytest.mark.parametrize("kind", ["identity", "proof"])
def test_changed_candidate_body_preserves_original_selection(kind):
    case = _q2()
    pool, current, verified = _materialize(case)
    _decisive(pool, kind).page_content += " Contenido agregado fuera del snapshot."
    assert _invoke(case, pool, current, verified) is current


@pytest.mark.parametrize(
    ("kind", "field"),
    [("identity", "source"), ("proof", "norma"), ("proof", "summary")],
)
def test_changed_candidate_metadata_preserves_original_selection(kind, field):
    case = _q2()
    pool, current, verified = _materialize(case)
    _decisive(pool, kind).metadata[field] = "Valor distinto del snapshot verificado"
    # Even descriptive metadata unrelated to matching must not be silently
    # ignored by the canonical provenance comparison.
    assert _invoke(case, pool, current, verified) is current


@pytest.mark.parametrize(
    "variant",
    [
        "document_id_conflict",
        "chunk_id_missing",
        "metadata_id_conflict",
        "snapshot_missing",
        "snapshot_duplicate",
    ],
)
def test_invalid_candidate_or_snapshot_identity_preserves_selection(variant):
    case = _q2()
    pool, current, verified = _materialize(case)
    proof = _decisive(pool, "proof")
    ident = proof.metadata["chunk_id"]
    if variant == "document_id_conflict":
        proof.id = "another-record"
    elif variant == "chunk_id_missing":
        del proof.metadata["chunk_id"]
    elif variant == "metadata_id_conflict":
        proof.metadata["id"] = "another-record"
    elif variant == "snapshot_missing":
        verified = tuple(doc for doc in verified if doc.metadata["chunk_id"] != ident)
    else:
        snapshot_proof = next(doc for doc in verified if doc.metadata["chunk_id"] == ident)
        verified = (*verified, snapshot_proof.model_copy(deep=True))
    assert _invoke(case, pool, current, verified) is current


@pytest.mark.parametrize(
    ("candidate_loader_id", "snapshot_loader_id", "document_id_none"),
    [(True, False, True), (False, True, True), (True, True, False), (False, False, True)],
)
def test_only_matching_loader_id_normalization_is_allowed(
    candidate_loader_id, snapshot_loader_id, document_id_none
):
    case = _q2()
    pool, current, verified = _materialize(case)
    proof = _decisive(pool, "proof")
    ident = proof.metadata["chunk_id"]
    snapshot_proof = next(doc for doc in verified if doc.metadata["chunk_id"] == ident)
    for doc, present in ((proof, candidate_loader_id), (snapshot_proof, snapshot_loader_id)):
        doc.metadata.pop("id", None)
        if present:
            doc.metadata["id"] = ident
    proof.id = None if document_id_none else ident
    snapshot_proof.id = None

    selected = _invoke(case, tuple(pool), current, verified)

    assert selected is not current
    assert selected[0] is proof
    assert len(selected) <= 4
    assert all(any(doc is original for original in pool) for doc in selected)


def _parenthetical_alias_case():
    case = copy.deepcopy(next(case for case in _CASES if case["case_id"] == "S01_FORMULAR"))
    case["question"] = "¿Y quién debe formularlo?"
    case["standalone_question"] = "¿Quién debe formular el Plan de Restauración de Dunas (PRD)?"
    case["history"] = [
        {
            "role": "user",
            "content": "¿Qué autoridad debe adoptar el Plan de Restauración de Dunas?",
        },
        {"role": "assistant", "content": "La adopción corresponde al Consejo de Restauración."},
    ]
    return case


def _assert_parenthetical_promotion(case, pool, current, verified):
    original = list(current)
    before_pool = [document.model_dump() for document in pool]
    before_snapshot = [document.model_dump() for document in verified]
    selected = _invoke(case, pool, current, verified)
    proof = next(
        document for document in pool if document.metadata["chunk_id"] in case["promote_ids"]
    )
    assert selected is not current and selected[0] is proof
    tail = original[: case["k"] - 1]
    assert len(selected) == 1 + len(tail)
    assert all(actual is expected for actual, expected in zip(selected[1:], tail, strict=True))
    assert all(actual is expected for actual, expected in zip(current, original, strict=True))
    assert [document.model_dump() for document in pool] == before_pool
    assert [document.model_dump() for document in verified] == before_snapshot


def test_parenthetical_alias_reproduces_captured_question_and_real_prefix():
    # Exact public texts from the diagnostic; the pool remains the portable
    # Gold-derived fixture above, not a replay of the remote process or ranking.
    case = copy.deepcopy(_q2())
    case["standalone_question"] = (
        "¿Quién debe formular el Plan de Ordenación y Manejo Integrado de la Unidad "
        "Ambiental Costera Caribe Insular (POMIUAC INSULAR)?"
    )
    case["history"] = [
        {
            "role": "user",
            "content": "¿Qué autoridad debe adoptar ese Plan de Ordenación y Manejo Integrado "
            "de la Unidad Ambiental Costera Caribe Insular?",
        },
        {
            "role": "assistant",
            "content": "La autoridad que debe adoptar el Plan de Ordenación y Manejo Integrado "
            "de la Unidad Ambiental Costera Caribe Insular (POMIUAC INSULAR) es el Consejo "
            "Directivo de la Corporación para el Desarrollo Sostenible del Archipiélago "
            "de San Andrés, Providencia y Santa Catalina, conocida como CORALINA [doc2].",
        },
    ]
    _assert_parenthetical_promotion(case, *_materialize(case))


def test_parenthetical_alias_is_supported_by_another_plan_body():
    case = _parenthetical_alias_case()
    _assert_parenthetical_promotion(case, *_materialize(case))


def test_parenthetical_meaningful_literal_name_keeps_the_existing_exact_path():
    case = copy.deepcopy(next(case for case in _CASES if case["case_id"] == "S01_FORMULAR"))
    name = "Plan de Restauración de Dunas (Sector Norte)"
    case["question"] = case["standalone_question"] = f"¿Quién debe formular el {name}?"
    pool, current, _ = _materialize(case)
    identity = next(
        document for document in pool if document.metadata["chunk_id"].endswith("-identity")
    )
    identity.page_content = f"Se establece el {name} -PRD-, como instrumento de ordenación."
    verified = tuple(document.model_copy(deep=True) for document in pool)
    _assert_parenthetical_promotion(case, pool, current, verified)


@pytest.mark.parametrize(
    "variant",
    [
        "wrong_alias",
        "meaningful_qualifier",
        "double_parenthetical",
        "nested_parenthetical",
        "truncated_name_with_later_qualifier",
        "AI_only_identity",
        "two_plans",
        "ambiguous_sources",
        "metadata_mismatch",
        "proof_absent_from_pool",
        "no_body_alias_declaration",
    ],
)
def test_parenthetical_alias_keeps_unproven_or_ambiguous_identity_as_fallback(variant):
    case = _parenthetical_alias_case()
    pool, current, verified = _materialize(case)
    identity = next(
        document for document in pool if document.metadata["chunk_id"].endswith("-identity")
    )
    proof = next(document for document in pool if document.metadata["chunk_id"].endswith("-proof"))
    if variant == "wrong_alias":
        case["standalone_question"] = case["standalone_question"].replace("(PRD)", "(OTRO)")
    elif variant == "meaningful_qualifier":
        case["standalone_question"] = case["standalone_question"].replace("(PRD)", "(Sector Norte)")
    elif variant == "double_parenthetical":
        case["standalone_question"] = case["standalone_question"].replace(
            "(PRD)", "(PRD) (Sector Norte)"
        )
    elif variant == "nested_parenthetical":
        case["standalone_question"] = case["standalone_question"].replace(
            "(PRD)", "(PRD (Sector Norte))"
        )
    elif variant == "truncated_name_with_later_qualifier":
        # The bounded name ends at the apparent alias, while the question still
        # has a meaningful qualifier. It must not identify only that prefix.
        base = "Plan " + "D" * 214
        case["standalone_question"] = f"¿Quién debe formular el {base} (PRD) del Sector Norte?"
        case["history"][0]["content"] = f"¿Qué autoridad debe adoptar el {base}?"
        identity.page_content = f"Se establece el {base} -PRD-, como instrumento de ordenación."
        verified = tuple(document.model_copy(deep=True) for document in pool)
    elif variant == "AI_only_identity":
        case["history"] = [
            {"role": "user", "content": "Quiero consultar ese instrumento."},
            {"role": "assistant", "content": "Se trata del Plan de Restauración de Dunas (PRD)."},
        ]
    elif variant == "two_plans":
        case["history"][0]["content"] = (
            "Compara el Plan de Restauración de Dunas y el Plan de Manejo de Humedales Urbanos."
        )
    elif variant == "ambiguous_sources":
        other = identity.model_copy(deep=True)
        other.id = other.metadata["chunk_id"] = other.metadata["id"] = "other-identity"
        other.metadata["source"] = "another_norm.md"
        pool.append(other)
        verified = (*verified, other.model_copy(deep=True))
    elif variant == "metadata_mismatch":
        proof.metadata["summary"] = "Descripción que no figura en el snapshot verificado."
    elif variant == "proof_absent_from_pool":
        pool.remove(proof)
    else:
        identity.page_content = identity.page_content.replace("-PRD-", "")
        verified = tuple(document.model_copy(deep=True) for document in pool)
    before_current = list(current)
    before_pool = [document.model_dump() for document in pool]
    before_snapshot = [document.model_dump() for document in verified]

    assert _invoke(case, pool, current, verified) is current

    assert all(actual is expected for actual, expected in zip(current, before_current, strict=True))
    assert [document.model_dump() for document in pool] == before_pool
    assert [document.model_dump() for document in verified] == before_snapshot
