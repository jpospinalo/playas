"""El prompt del agente no debe sembrar normas concretas.

Con Claude Sonnet como generador, nombrar «el Decreto 2324 de 1984» como
ejemplo en las reglas hizo que 10 de 65 respuestas lo citaran sin que estuviera
en el contexto (referencias sin respaldo: 12 % → 32 %).
"""

import re

from rag.core.prompts import AGENT_SYSTEM


def test_el_prompt_no_nombra_normas_concretas_como_ejemplo():
    assert not re.search(r"\b\d{3,4} de (19|20)\d{2}\b", AGENT_SYSTEM)
    assert "2324" not in AGENT_SYSTEM
    assert "REMAC" not in AGENT_SYSTEM


def test_lo_que_falta_se_describe_sin_nombrar_normas_ausentes():
    texto = " ".join(AGENT_SYSTEM.split())
    assert "no nombres normas, artículos ni sentencias que no estén en el contexto" in texto
