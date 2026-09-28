"""Comparação entre dois perfis para detectar deriva (drift).

A ideia e simples: guardar o perfil de uma carga que se sabe boa e comparar
as proximas contra ela. Mudança de esquema, salto no percentual de nulos e
variação brusca na média costumam aparecer aqui antes de virar reclamação
do time de negocio.
"""

from __future__ import annotations

from dataclasses import dataclass

from .formato import numero, pct
from .perfil import Perfil, PerfilColuna


@dataclass
class Divergencia:
    coluna: str
    aspecto: str
    antes: str
    agora: str
    gravidade: str  # "aviso" ou "alta"


def _variacao_relativa(antes: float, agora: float) -> float:
    if antes == 0:
        return 100.0 if agora != 0 else 0.0
    return abs(agora - antes) / abs(antes) * 100


def _comparar_coluna(
    base: PerfilColuna, atual: PerfilColuna, limite_pct: float
) -> list[Divergencia]:
    divergencias: list[Divergencia] = []

    if base.tipo_inferido != atual.tipo_inferido:
        divergencias.append(
            Divergencia(
                coluna=base.nome,
                aspecto="tipo inferido",
                antes=base.tipo_inferido,
                agora=atual.tipo_inferido,
                gravidade="alta",
            )
        )

    # Diferença em pontos percentuais, não relativa: sair de 0,1% para 2% de
    # nulos é uma variação relativa gigante, mas na prática é irrelevante.
    diferenca_nulos = abs(atual.nulos_pct - base.nulos_pct)
    if diferenca_nulos > limite_pct:
        divergencias.append(
            Divergencia(
                coluna=base.nome,
                aspecto="percentual em branco",
                antes=f"{pct(base.nulos_pct)}%",
                agora=f"{pct(atual.nulos_pct)}%",
                gravidade="alta" if diferenca_nulos > limite_pct * 3 else "aviso",
            )
        )

    if base.media is not None and atual.media is not None:
        variacao = _variacao_relativa(base.media, atual.media)
        if variacao > limite_pct:
            divergencias.append(
                Divergencia(
                    coluna=base.nome,
                    aspecto="média",
                    antes=numero(base.media),
                    agora=f"{numero(atual.media)} ({pct(variacao, 1)}% de variação)",
                    gravidade="alta" if variacao > limite_pct * 3 else "aviso",
                )
            )

    # Queda de cardinalidade é o sintoma mais comum de carga duplicada.
    # O sentido importa: mais valores distintos é crescimento normal da base,
    # menos valores distintos costuma ser defeito.
    queda_cardinalidade = base.distintos_pct - atual.distintos_pct
    if queda_cardinalidade > limite_pct:
        divergencias.append(
            Divergencia(
                coluna=base.nome,
                aspecto="valores distintos",
                antes=f"{pct(base.distintos_pct)}%",
                agora=f"{pct(atual.distintos_pct)}%",
                gravidade="alta" if queda_cardinalidade > limite_pct * 3 else "aviso",
            )
        )

    # Uma coluna que era chave e deixou de ser quase sempre indica
    # duplicação na carga.
    if base.candidata_a_chave and not atual.candidata_a_chave:
        divergencias.append(
            Divergencia(
                coluna=base.nome,
                aspecto="unicidade",
                antes="valores unicos",
                agora=f"{atual.distintos} distintos em {atual.total} linhas",
                gravidade="alta",
            )
        )

    return divergencias


def comparar(base: Perfil, atual: Perfil, limite_pct: float = 5.0) -> list[Divergencia]:
    divergencias: list[Divergencia] = []

    nomes_base = {c.nome for c in base.colunas}
    nomes_atual = {c.nome for c in atual.colunas}

    for nome in sorted(nomes_base - nomes_atual):
        divergencias.append(
            Divergencia(nome, "esquema", "presente", "ausente", "alta")
        )

    for nome in sorted(nomes_atual - nomes_base):
        divergencias.append(
            Divergencia(nome, "esquema", "ausente", "presente", "aviso")
        )

    for nome in sorted(nomes_base & nomes_atual):
        divergencias.extend(
            _comparar_coluna(base.por_nome(nome), atual.por_nome(nome), limite_pct)
        )

    variacao_linhas = _variacao_relativa(base.linhas, atual.linhas)
    if variacao_linhas > limite_pct:
        divergencias.insert(
            0,
            Divergencia(
                coluna="(dataset)",
                aspecto="volume de linhas",
                antes=f"{base.linhas}",
                agora=f"{atual.linhas} ({variacao_linhas:.1f}% de variação)",
                gravidade="alta" if variacao_linhas > limite_pct * 3 else "aviso",
            ),
        )

    return divergencias
