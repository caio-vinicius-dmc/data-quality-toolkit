"""Linha de comando do toolkit.

    dq perfil exemplos/clientes.csv
    dq perfil exemplos/clientes.csv --salvar base.perfil.json
    dq sugerir exemplos/clientes.csv > regras.toml
    dq validar exemplos/clientes.csv --regras exemplos/regras.toml
    dq comparar base.perfil.json --contra exemplos/clientes.csv

Sem instalar o pacote, todos os comandos funcionam com
`python -m dq.cli <comando>`.

Códigos de saída (pensados para uso em CI):
    0  tudo certo, no máximo alertas
    1  alguma regra falhou ou houve deriva grave
    2  erro de uso (arquivo inexistente, regra inválida)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .deriva import comparar
from .formato import numero as _numero, pct as _pct
from .fontes import FonteInvalida, carregar
from .perfil import Perfil, perfilar


from .regras import (
    STATUS_ALERTA,
    STATUS_FALHA,
    STATUS_OK,
    RegraInvalida,
    carregar_regras,
    sugerir,
    validar,
)
from . import relatorio as saida

console = Console()

COR = {STATUS_OK: "green", STATUS_ALERTA: "yellow", STATUS_FALHA: "red"}


def _carregar(args: argparse.Namespace):
    return carregar(
        args.origem,
        eh_tabela=args.tabela,
        separador=args.separador,
        limite=args.limite,
    )


def comando_perfil(args: argparse.Namespace) -> int:
    quadro, rotulo = _carregar(args)
    perfil = perfilar(quadro, rotulo)

    tabela = Table(title=f"Perfil de {rotulo} ({perfil.linhas} linhas)")
    for coluna in ("Coluna", "Tipo", "Em branco", "Distintos", "Mínimo", "Máximo"):
        tabela.add_column(coluna)

    for c in perfil.colunas:
        tabela.add_row(
            c.nome,
            c.tipo_inferido,
            f"{c.nulos} ({_pct(c.nulos_pct)}%)",
            f"{c.distintos} ({_pct(c.distintos_pct)}%)",
            _numero(c.minimo),
            _numero(c.maximo),
        )
    console.print(tabela)

    for c in perfil.colunas:
        if c.candidata_a_chave:
            console.print(f"  {c.nome}: candidata a chave (sem nulos, sem repetições)")
        if c.constante:
            console.print(f"  [yellow]{c.nome}: valor constante em todas as linhas[/yellow]")

    if args.salvar:
        destino = perfil.salvar(Path(args.salvar))
        console.print(f"\nPerfil salvo em {destino}")

    if args.markdown:
        console.print(f"Markdown em {saida.salvar(saida.perfil_em_markdown(perfil), Path(args.markdown))}")
    if args.html:
        console.print(f"HTML em {saida.salvar(saida.perfil_em_html(perfil), Path(args.html))}")

    return 0


def comando_sugerir(args: argparse.Namespace) -> int:
    quadro, rotulo = _carregar(args)
    texto = sugerir(perfilar(quadro, rotulo))

    if args.saida:
        destino = saida.salvar(texto, Path(args.saida))
        console.print(f"Regras sugeridas em {destino}. Revise antes de usar.")
    else:
        # Sem --saida vai para o stdout limpo, para poder redirecionar
        # com > sem os enfeites do rich no meio.
        print(texto)

    return 0


def comando_validar(args: argparse.Namespace) -> int:
    quadro, rotulo = _carregar(args)
    regras = carregar_regras(Path(args.regras))
    resultado = validar(quadro, regras, rotulo)

    tabela = Table(title=f"Validação de {rotulo}")
    for coluna in ("Escopo", "Regra", "Status", "Falhas", "Detalhe"):
        tabela.add_column(coluna)

    ordem = {STATUS_FALHA: 0, STATUS_ALERTA: 1, STATUS_OK: 2}
    for r in sorted(resultado.resultados, key=lambda r: (ordem[r.status], r.escopo)):
        tabela.add_row(
            r.escopo,
            r.regra,
            f"[{COR[r.status]}]{r.status}[/{COR[r.status]}]",
            f"{r.falhas} ({_pct(r.falhas_pct)}%)",
            r.detalhe,
        )
    console.print(tabela)

    falhas = resultado.contar(STATUS_FALHA)
    alertas = resultado.contar(STATUS_ALERTA)
    console.print(
        f"{resultado.contar(STATUS_OK)} ok, {alertas} alertas, {falhas} falhas."
    )

    if args.markdown:
        console.print(f"Markdown em {saida.salvar(saida.validacao_em_markdown(resultado), Path(args.markdown))}")
    if args.html:
        console.print(f"HTML em {saida.salvar(saida.validacao_em_html(resultado), Path(args.html))}")

    return 1 if resultado.falhou else 0


def comando_comparar(args: argparse.Namespace) -> int:
    base = Perfil.carregar(Path(args.base))
    quadro, rotulo = _carregar(args)
    atual = perfilar(quadro, rotulo)

    divergencias = comparar(base, atual, limite_pct=args.limite_pct)

    if not divergencias:
        console.print(
            f"[green]Nenhuma divergência acima de {_pct(args.limite_pct, 1)}%[/green] "
            f"entre {base.origem} e {rotulo}."
        )
    else:
        tabela = Table(title=f"{base.origem} comparado com {rotulo}")
        for coluna in ("Coluna", "Aspecto", "Antes", "Agora", "Gravidade"):
            tabela.add_column(coluna)
        for d in divergencias:
            cor = "red" if d.gravidade == "alta" else "yellow"
            tabela.add_row(
                d.coluna, d.aspecto, d.antes, d.agora, f"[{cor}]{d.gravidade}[/{cor}]"
            )
        console.print(tabela)

    if args.markdown:
        console.print(
            f"Markdown em {saida.salvar(saida.deriva_em_markdown(base, atual, divergencias), Path(args.markdown))}"
        )

    graves = sum(1 for d in divergencias if d.gravidade == "alta")
    return 1 if graves else 0


def _adicionar_origem(parser: argparse.ArgumentParser) -> None:
    """Opções comuns a todos os comandos que leem dado."""
    parser.add_argument("origem", help="caminho do CSV/Parquet ou nome da tabela")
    parser.add_argument(
        "--tabela",
        action="store_true",
        help="trata a origem como tabela do PostgreSQL (usa o .env)",
    )
    parser.add_argument("--separador", default=",", help="separador do CSV (padrão: ,)")
    parser.add_argument("--limite", type=int, help="lê apenas as N primeiras linhas")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq",
        description="Perfil e validação de qualidade de dados.",
    )
    parser.add_argument("--versao", action="version", version=f"dq {__version__}")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_perfil = sub.add_parser("perfil", help="descreve as colunas da origem")
    _adicionar_origem(p_perfil)
    p_perfil.add_argument("--salvar", metavar="ARQUIVO", help="grava o perfil em JSON")
    p_perfil.add_argument("--markdown", metavar="ARQUIVO")
    p_perfil.add_argument("--html", metavar="ARQUIVO")
    p_perfil.set_defaults(funcao=comando_perfil)

    p_sugerir = sub.add_parser(
        "sugerir", help="gera um esqueleto de regras a partir do dado atual"
    )
    _adicionar_origem(p_sugerir)
    p_sugerir.add_argument("--saida", metavar="ARQUIVO", help="grava em arquivo")
    p_sugerir.set_defaults(funcao=comando_sugerir)

    p_validar = sub.add_parser("validar", help="aplica um arquivo de regras")
    _adicionar_origem(p_validar)
    p_validar.add_argument("--regras", required=True, metavar="ARQUIVO")
    p_validar.add_argument("--markdown", metavar="ARQUIVO")
    p_validar.add_argument("--html", metavar="ARQUIVO")
    p_validar.set_defaults(funcao=comando_validar)

    p_comparar = sub.add_parser("comparar", help="procura deriva contra um perfil salvo")
    p_comparar.add_argument("base", help="arquivo .perfil.json gerado antes")
    p_comparar.add_argument(
        "--contra", dest="origem", required=True, help="origem atual a comparar"
    )
    p_comparar.add_argument("--tabela", action="store_true")
    p_comparar.add_argument("--separador", default=",")
    p_comparar.add_argument("--limite", type=int)
    p_comparar.add_argument(
        "--limite-pct",
        dest="limite_pct",
        type=float,
        default=5.0,
        help="variação aceita antes de virar divergência (padrão: 5)",
    )
    p_comparar.add_argument("--markdown", metavar="ARQUIVO")
    p_comparar.set_defaults(funcao=comando_comparar)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        return args.funcao(args)
    except (FonteInvalida, RegraInvalida) as erro:
        console.print(f"[red]{erro}[/red]")
        return 2


if __name__ == "__main__":
    sys.exit(main())
