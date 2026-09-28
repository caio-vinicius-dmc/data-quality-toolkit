"""Leitura das origens suportadas: CSV, Parquet e tabela no PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


class FonteInvalida(Exception):
    """Levantada quando a origem não pode ser lida da forma pedida."""


def ler_arquivo(caminho: Path, separador: str = ",", limite: int | None = None) -> pd.DataFrame:
    if not caminho.exists():
        raise FonteInvalida(f"Arquivo não encontrado: {caminho}")

    sufixo = caminho.suffix.lower()

    if sufixo in {".csv", ".txt"}:
        # dtype=str porque a inferência do pandas esconde problema: uma coluna
        # de idade com um valor vazio vira float e o "18" já não é mais
        # inteiro. A conversão fica por conta de quem valida.
        return pd.read_csv(
            caminho, sep=separador, dtype=str, keep_default_na=True, nrows=limite
        )

    if sufixo == ".parquet":
        try:
            quadro = pd.read_parquet(caminho)
        except ImportError as erro:
            raise FonteInvalida(
                "Ler Parquet exige o pyarrow. Instale com: pip install pyarrow"
            ) from erro
        return quadro.head(limite) if limite else quadro

    raise FonteInvalida(
        f"Extensão '{sufixo}' não suportada. Use .csv, .txt ou .parquet."
    )


def ler_tabela(tabela: str, limite: int | None = None) -> pd.DataFrame:
    """Le uma tabela do PostgreSQL usando as credenciais do ambiente.

    Nenhuma credencial fica no código nem em arquivo versionado. Se as
    variáveis não estiverem definidas, a função diz exatamente o que falta.
    """
    try:
        import psycopg
        from dotenv import load_dotenv
    except ImportError as erro:
        raise FonteInvalida(
            "Validar tabela exige os extras de banco. "
            "Instale com: pip install 'data-quality-toolkit[postgres]'"
        ) from erro

    load_dotenv()

    obrigatorias = ["POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    faltando = [nome for nome in obrigatorias if not os.getenv(nome)]
    if faltando:
        raise FonteInvalida(
            "Faltam variáveis de ambiente: " + ", ".join(faltando) + ". "
            "Copie o .env.example para .env e preencha."
        )

    dsn = (
        f"host={os.getenv('POSTGRES_HOST')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB')} "
        f"user={os.getenv('POSTGRES_USER')} "
        f"password={os.getenv('POSTGRES_PASSWORD')}"
    )

    # O nome da tabela e validado aqui porque vai concatenado no SQL.
    # Aceita apenas identificadores simples, com schema opcional.
    if not all(parte.isidentifier() for parte in tabela.split(".")):
        raise FonteInvalida(
            f"'{tabela}' não parece um nome de tabela valido. "
            "Use o formato schema.tabela."
        )

    consulta = f"SELECT * FROM {tabela}"
    if limite:
        consulta += f" LIMIT {int(limite)}"

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(consulta)
            colunas = [descricao.name for descricao in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=colunas)


def carregar(
    origem: str,
    eh_tabela: bool = False,
    separador: str = ",",
    limite: int | None = None,
) -> tuple[pd.DataFrame, str]:
    """Ponto único de entrada. Devolve o quadro e um rótulo para o relatório."""
    if eh_tabela:
        return ler_tabela(origem, limite), f"tabela {origem}"
    caminho = Path(origem)
    return ler_arquivo(caminho, separador, limite), caminho.name
