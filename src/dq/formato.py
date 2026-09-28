"""Números na convenção brasileira, só para exibição.

O que fica guardado no arquivo de perfil continua em ASCII, com ponto
decimal: é assim que o comando `comparar` consegue ler de volta o que outro
comando gravou, e é assim que qualquer outra ferramenta vai esperar
encontrar. A vírgula aparece na hora de mostrar na tela, e só ali.

Sem esse cuidado, o relatório sai com "7.75% de nulos" ao lado de
"1.517,21" -- duas convenções na mesma linha, o que faz o leitor parar para
decidir se o ponto é milhar ou decimal.
"""

from __future__ import annotations


def pct(valor: float, casas: int = 2) -> str:
    """Percentual com vírgula decimal, sem o símbolo.

    >>> pct(7.75)
    '7,75'
    >>> pct(15.0, casas=1)
    '15,0'
    """
    return f"{valor:.{casas}f}".replace(".", ",")


def numero(valor: float | int | str | None, casas: int | None = None) -> str:
    """Número com ponto no milhar e vírgula no decimal.

    Aceita texto porque o mínimo e o máximo do perfil chegam assim -- a mesma
    coluna do relatório serve para número, data e palavra. O que não for
    número volta intacto.

    Com `casas=None`, decide pela aparência do valor: inteiro sai sem casas
    decimais, o resto sai com duas.

    >>> numero("1517.21")
    '1.517,21'
    >>> numero(400)
    '400'
    >>> numero("2024-01-02")
    '2024-01-02'
    >>> numero(None)
    '-'
    """
    if valor is None or valor == "":
        return "-"

    try:
        convertido = float(valor)
    except (TypeError, ValueError):
        return str(valor)

    if casas is None:
        casas = 0 if convertido == int(convertido) else 2

    # O marcador temporário evita embaralhar os separadores no meio da troca:
    # sem ele, o ponto virava vírgula e a vírgula virava ponto de volta.
    bruto = f"{convertido:,.{casas}f}"
    return bruto.replace(",", "@").replace(".", ",").replace("@", ".")
