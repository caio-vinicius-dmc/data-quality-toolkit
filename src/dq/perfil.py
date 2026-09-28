"""Perfil das colunas: o retrato do dado antes de qualquer regra."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass
class PerfilColuna:
    nome: str
    tipo_declarado: str
    tipo_inferido: str
    total: int
    nulos: int
    nulos_pct: float
    distintos: int
    distintos_pct: float
    vazios: int
    minimo: str | None = None
    maximo: str | None = None
    media: float | None = None
    mediana: float | None = None
    tamanho_min: int | None = None
    tamanho_max: int | None = None
    valores_frequentes: list[tuple[str, int]] = field(default_factory=list)

    @property
    def constante(self) -> bool:
        """Coluna com um único valor costuma ser sobra de um ETL antigo."""
        return self.distintos <= 1 and self.total > 1

    @property
    def candidata_a_chave(self) -> bool:
        return self.nulos == 0 and self.distintos == self.total and self.total > 0


@dataclass
class Perfil:
    origem: str
    gerado_em: str
    linhas: int
    colunas: list[PerfilColuna]

    def por_nome(self, nome: str) -> PerfilColuna | None:
        return next((c for c in self.colunas if c.nome == nome), None)

    def salvar(self, destino: Path) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return destino

    @classmethod
    def carregar(cls, caminho: Path) -> "Perfil":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return cls(
            origem=dados["origem"],
            gerado_em=dados["gerado_em"],
            linhas=dados["linhas"],
            colunas=[PerfilColuna(**c) for c in dados["colunas"]],
        )


def _inferir_tipo(serie: pd.Series) -> str:
    """Descobre o tipo útil da coluna, não o que o pandas guardou.

    Ler tudo como texto é proposital, então o dtype quase sempre e 'object'.
    O que interessa e saber se aquele texto e número, data ou texto mesmo.
    """
    validos = serie.dropna()
    validos = validos[validos.astype(str).str.strip() != ""]

    if validos.empty:
        return "vazio"

    amostra = validos.astype(str)

    numericos = pd.to_numeric(amostra, errors="coerce")
    if numericos.notna().all():
        return "inteiro" if (numericos % 1 == 0).all() else "decimal"

    datas = pd.to_datetime(amostra, errors="coerce", format="mixed")
    if datas.notna().all():
        return "data"

    minusculas = amostra.str.lower().unique()
    if set(minusculas) <= {"true", "false", "0", "1", "sim", "nao"}:
        return "booleano"

    return "texto"


def _estatisticas_numericas(serie: pd.Series) -> tuple[float | None, float | None]:
    numeros = pd.to_numeric(serie, errors="coerce").dropna()
    if numeros.empty:
        return None, None
    return round(float(numeros.mean()), 4), round(float(numeros.median()), 4)


def perfilar_coluna(nome: str, serie: pd.Series) -> PerfilColuna:
    total = len(serie)
    nulos = int(serie.isna().sum())

    texto = serie.astype(str)
    vazios = int((texto.str.strip() == "").sum()) - nulos
    vazios = max(vazios, 0)

    validos = serie.dropna()
    distintos = int(validos.nunique())
    tipo = _inferir_tipo(serie)

    perfil = PerfilColuna(
        nome=nome,
        tipo_declarado=str(serie.dtype),
        tipo_inferido=tipo,
        total=total,
        nulos=nulos,
        nulos_pct=round(nulos / total * 100, 2) if total else 0.0,
        distintos=distintos,
        distintos_pct=round(distintos / total * 100, 2) if total else 0.0,
        vazios=vazios,
    )

    if not validos.empty:
        comprimentos = validos.astype(str).str.len()
        perfil.tamanho_min = int(comprimentos.min())
        perfil.tamanho_max = int(comprimentos.max())

        if tipo in {"inteiro", "decimal"}:
            numeros = pd.to_numeric(validos, errors="coerce").dropna()
            if not numeros.empty:
                perfil.minimo = str(numeros.min())
                perfil.maximo = str(numeros.max())
            perfil.media, perfil.mediana = _estatisticas_numericas(validos)
        else:
            ordenados = sorted(validos.astype(str).unique())
            perfil.minimo = ordenados[0]
            perfil.maximo = ordenados[-1]

        # So faz sentido listar os valores mais comuns quando a coluna tem
        # poucos valores distintos; em uma coluna de id isso seria ruido.
        if distintos <= 25:
            contagem = validos.astype(str).value_counts().head(10)
            perfil.valores_frequentes = [
                (str(valor), int(qtd)) for valor, qtd in contagem.items()
            ]

    return perfil


def perfilar(quadro: pd.DataFrame, origem: str) -> Perfil:
    return Perfil(
        origem=origem,
        gerado_em=datetime.now().isoformat(timespec="seconds"),
        linhas=len(quadro),
        colunas=[perfilar_coluna(nome, quadro[nome]) for nome in quadro.columns],
    )
