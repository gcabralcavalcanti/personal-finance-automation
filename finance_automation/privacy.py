"""Keep private individuals' names out of the API: a transfer whose counterpart looks like a person is sent as
<PERSON>. The test errs on the side of masking: a one-person business with a plain name is masked too."""

from __future__ import annotations

import re

PERSON = "<PERSON>"
TRANSFER = ("PIX", "TED", "DOC", "TRANSFERENCIA")
# words that mark a business, a trade or an institution, not a private individual
BUSINESS = {
    "LTDA",
    "ME",
    "EPP",
    "EIRELI",
    "SA",
    "S/A",
    "CIA",
    "COMERCIO",
    "SERVICOS",
    "SERVICO",
    "LOJA",
    "MERCADO",
    "SUPERMERCADO",
    "FARMACIA",
    "DROGARIA",
    "RESTAURANTE",
    "LANCHONETE",
    "PADARIA",
    "IMOBILIARIA",
    "CONDOMINIO",
    "ESCOLA",
    "COLEGIO",
    "CURSO",
    "CLINICA",
    "ODONTO",
    "HOSPITAL",
    "LABORATORIO",
    "ACADEMIA",
    "POSTO",
    "AUTO",
    "BANCO",
    "SEGUROS",
    "SEGURO",
    "ASSOCIACAO",
    "INSTITUTO",
    "IGREJA",
    "FUNDACAO",
    "DOACAO",
    "REPASSE",
    "VENDAS",
    "PAGAMENTOS",
    "DIGITAIS",
    "DIGITAL",
    "TECNOLOGIA",
    "CONSULTORIA",
    "ENGENHARIA",
    "REPAROS",
    "REFORMAS",
    "ELETRICISTA",
    "ENCANADOR",
    "CHAVEIRO",
    "MOTORISTA",
    "TRANSPORTES",
    "ENTREGAS",
    "DELIVERY",
    "PET",
    "BAR",
    "CAFE",
    "STUDIO",
    "ESTUDIO",
    "SALAO",
    "BARBEARIA",
    "OFICINA",
    "CONTABILIDADE",
    "ADVOCACIA",
    "ADVOGADOS",
}
_WORD = re.compile(r"^[A-Z]+$")


def is_person(description: str, history: str) -> bool:
    """A transfer to or from what looks like a private individual: 2 to 5 words, letters only, no business word."""
    if not any(t in history for t in TRANSFER):
        return False
    words = description.split()
    if not 2 <= len(words) <= 5:
        return False
    return all(_WORD.match(w) for w in words) and not any(w in BUSINESS for w in words)


def shown_to_model(description: str, history: str) -> str:
    return PERSON if is_person(description, history) else description
