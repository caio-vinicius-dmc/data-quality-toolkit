"""Regras declarativas de qualidade e sua execução.

As regras ficam em um arquivo TOML e não no código, porque quem conhece o
dado nem sempre e quem escreve Python. O formato TOML foi escolhido por
estar na biblioteca padrão do Python 3.11 -- uma dependência a menos.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .formato import pct
from .perfil import Perfil

# Regras que aceitam tolerância caem para "alerta" em vez de "falha"
# quando o percentual de problemas fica abaixo do limite configurado.
STATUS_OK = "ok"
STATUS_ALERTA = "alerta"
STATUS_FALHA = "falha"


class RegraInvalida(Exception):
    """Arquivo de regras mal formado ou apontando para coluna inexistente."""


@dataclass
class Resultado:
    escopo: str          # "dataset" ou o nome da coluna
    regra: str
    status: str
    avaliados: int
    falhas: int
    detalhe: str

    @property
    def falhas_pct(self) -> float:
        return round(self.falhas / self.avaliados * 100, 2) if self.avaliados else 0.0


@dataclass
class Relatorio:
    origem: str
    linhas: int
    resultados: list[Resultado]

    @property
    def falhou(self) -> bool:
        return any(r.status == STATUS_FALHA for r in self.resultados)

    def contar(self, status: str) -> int:
        return sum(1 for r in self.resultados if r.status == status)


def carregar_regras(caminho: Path) -> dict:
    if not caminho.exists():
        raise RegraInvalida(f"Arquivo de regras não encontrado: {caminho}")
    try:
        return tomllib.loads(caminho.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as erro:
        raise RegraInvalida(f"TOML invalido em {caminho}: {erro}") from erro


def _classificar(falhas: int, avaliados: int, tolerancia_pct: float | None) -> str:
    if falhas == 0:
        return STATUS_OK
    if tolerancia_pct is None:
        return STATUS_FALHA
    percentual = falhas / avaliados * 100 if avaliados else 0
    return STATUS_ALERTA if percentual <= tolerancia_pct else STATUS_FALHA


def _validar_dataset(quadro: pd.DataFrame, config: dict) -> list[Resultado]:
    resultados: list[Resultado] = []

    minimo = config.get("minimo_de_linhas")
    if minimo is not None:
        falta = max(minimo - len(quadro), 0)
        resultados.append(
            Resultado(
                escopo="dataset",
                regra="minimo_de_linhas",
                status=STATUS_OK if falta == 0 else STATUS_FALHA,
                avaliados=1,
                falhas=1 if falta else 0,
                detalhe=f"{len(quadro)} linhas (mínimo esperado: {minimo})",
            )
        )

    obrigatorias = config.get("colunas_obrigatorias")
    if obrigatorias:
        ausentes = [c for c in obrigatorias if c not in quadro.columns]
        resultados.append(
            Resultado(
                escopo="dataset",
                regra="colunas_obrigatorias",
                status=STATUS_OK if not ausentes else STATUS_FALHA,
                avaliados=len(obrigatorias),
                falhas=len(ausentes),
                detalhe="todas presentes"
                if not ausentes
                else "faltando: " + ", ".join(ausentes),
            )
        )

    return resultados


def _marcar_ausentes(serie: pd.Series) -> pd.Series:
    """Nulo, string vazia e o texto 'nan' contam todos como ausentes.

    Um campo em branco no CSV não é um valor preenchido, e o 'nan' aparece
    quando a origem já passou por um pandas mal configurado antes de chegar
    aqui -- visto em produção mais de uma vez.
    """
    texto = serie.astype(str).str.strip()
    return serie.isna() | (texto == "") | (texto.str.lower() == "nan")


def _validar_coluna(serie: pd.Series, config: dict) -> list[Resultado]:
    nome = config["nome"]
    resultados: list[Resultado] = []
    tolerancia = config.get("maximo_de_falhas_pct")

    total = len(serie)
    ausentes = _marcar_ausentes(serie)
    preenchidos = serie[~ausentes]

    if config.get("nao_nulo"):
        falhas = int(ausentes.sum())
        limite = config.get("maximo_de_nulos_pct", tolerancia)
        resultados.append(
            Resultado(
                escopo=nome,
                regra="nao_nulo",
                status=_classificar(falhas, total, limite),
                avaliados=total,
                falhas=falhas,
                detalhe=f"{falhas} valores ausentes",
            )
        )
    elif "maximo_de_nulos_pct" in config:
        falhas = int(ausentes.sum())
        limite_pct = config["maximo_de_nulos_pct"]
        percentual = falhas / total * 100 if total else 0
        resultados.append(
            Resultado(
                escopo=nome,
                regra="maximo_de_nulos_pct",
                status=STATUS_OK if percentual <= limite_pct else STATUS_FALHA,
                avaliados=total,
                falhas=falhas,
                detalhe=f"{pct(percentual)}% de nulos (limite: {pct(limite_pct, 1)}%)",
            )
        )

    if config.get("unico"):
        repetidos = preenchidos[preenchidos.duplicated(keep=False)]
        falhas = int(len(repetidos))
        exemplos = ", ".join(map(str, repetidos.unique()[:3]))
        resultados.append(
            Resultado(
                escopo=nome,
                regra="unico",
                status=_classificar(falhas, len(preenchidos), tolerancia),
                avaliados=len(preenchidos),
                falhas=falhas,
                detalhe="sem repetições"
                if not falhas
                else f"{falhas} linhas repetidas (ex.: {exemplos})",
            )
        )

    if "entre" in config:
        limite_min, limite_max = config["entre"]
        numeros = pd.to_numeric(preenchidos, errors="coerce")
        # Valor não numérico numa coluna com faixa também e falha: significa
        # que o dado não é do tipo que a regra assume.
        fora = numeros.isna() | (numeros < limite_min) | (numeros > limite_max)
        falhas = int(fora.sum())
        resultados.append(
            Resultado(
                escopo=nome,
                regra="entre",
                status=_classificar(falhas, len(preenchidos), tolerancia),
                avaliados=len(preenchidos),
                falhas=falhas,
                detalhe=f"{falhas} valores fora de [{limite_min}, {limite_max}]",
            )
        )

    if "dominio" in config:
        aceitos = set(map(str, config["dominio"]))
        valores = preenchidos.astype(str).str.strip()
        fora = ~valores.isin(aceitos)
        falhas = int(fora.sum())
        inesperados = ", ".join(sorted(valores[fora].unique())[:5])
        resultados.append(
            Resultado(
                escopo=nome,
                regra="dominio",
                status=_classificar(falhas, len(preenchidos), tolerancia),
                avaliados=len(preenchidos),
                falhas=falhas,
                detalhe="todos dentro do domínio"
                if not falhas
                else f"{falhas} fora do domínio (ex.: {inesperados})",
            )
        )

    if "formato" in config:
        try:
            padrao = re.compile(config["formato"])
        except re.error as erro:
            raise RegraInvalida(
                f"Expressão regular inválida na coluna {nome}: {erro}"
            ) from erro
        valores = preenchidos.astype(str).str.strip()
        casam = valores.str.fullmatch(padrao).fillna(False)
        falhas = int((~casam).sum())
        exemplos = ", ".join(valores[~casam].head(3))
        resultados.append(
            Resultado(
                escopo=nome,
                regra="formato",
                status=_classificar(falhas, len(preenchidos), tolerancia),
                avaliados=len(preenchidos),
                falhas=falhas,
                detalhe="todos no formato"
                if not falhas
                else f"{falhas} fora do padrão (ex.: {exemplos})",
            )
        )

    if "tamanho_maximo" in config:
        limite = config["tamanho_maximo"]
        comprimentos = preenchidos.astype(str).str.len()
        falhas = int((comprimentos > limite).sum())
        resultados.append(
            Resultado(
                escopo=nome,
                regra="tamanho_maximo",
                status=_classificar(falhas, len(preenchidos), tolerancia),
                avaliados=len(preenchidos),
                falhas=falhas,
                detalhe=f"{falhas} valores com mais de {limite} caracteres",
            )
        )

    return resultados


def validar(quadro: pd.DataFrame, regras: dict, origem: str) -> Relatorio:
    resultados = _validar_dataset(quadro, regras.get("dataset", {}))

    for config in regras.get("coluna", []):
        if "nome" not in config:
            raise RegraInvalida("Todo bloco [[coluna]] precisa do campo 'nome'.")

        nome = config["nome"]
        if nome not in quadro.columns:
            # Coluna sumiu da origem. É falha, e não um aviso: as outras
            # regras dela não tem como ser avaliadas.
            resultados.append(
                Resultado(
                    escopo=nome,
                    regra="coluna_existe",
                    status=STATUS_FALHA,
                    avaliados=1,
                    falhas=1,
                    detalhe="coluna declarada nas regras mas ausente na origem",
                )
            )
            continue

        resultados.extend(_validar_coluna(quadro[nome], config))

    return Relatorio(origem=origem, linhas=len(quadro), resultados=resultados)


def sugerir(perfil: Perfil) -> str:
    """Gera um esqueleto de regras a partir do perfil observado.

    O resultado não deve ser aceito as cegas: ele transforma em regra o que o
    dado e hoje, defeitos inclusive. Serve como ponto de partida para quem
    conhece o negocio revisar.
    """
    linhas = [
        f"# Regras geradas a partir do perfil de {perfil.origem}.",
        "# Revise antes de usar: o gerador descreve o dado como ele está,",
        "# não como ele deveria estar.",
        "",
        "[dataset]",
        f"minimo_de_linhas = {max(int(perfil.linhas * 0.8), 1)}",
        "colunas_obrigatorias = ["
        + ", ".join(f'"{c.nome}"' for c in perfil.colunas)
        + "]",
        "",
    ]

    for coluna in perfil.colunas:
        linhas.append("[[coluna]]")
        linhas.append(f'nome = "{coluna.nome}"')

        if coluna.nulos == 0:
            linhas.append("nao_nulo = true")
        elif coluna.nulos_pct < 50:
            folga = min(round(coluna.nulos_pct + 5, 1), 100.0)
            linhas.append(f"maximo_de_nulos_pct = {folga}")

        if coluna.candidata_a_chave:
            linhas.append("único = true")

        if coluna.tipo_inferido in {"inteiro", "decimal"} and coluna.minimo:
            linhas.append(f"entre = [{coluna.minimo}, {coluna.maximo}]")

        if coluna.valores_frequentes and coluna.distintos <= 15:
            dominio = ", ".join(f'"{valor}"' for valor, _ in coluna.valores_frequentes)
            linhas.append(f"domínio = [{dominio}]")

        if coluna.tamanho_max:
            linhas.append(f"tamanho_maximo = {coluna.tamanho_max}")

        linhas.append("")

    return "\n".join(linhas)
