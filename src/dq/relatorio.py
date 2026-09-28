"""Saída dos comandos em Markdown e HTML.

O Markdown serve para colar em pull request ou em ticket. O HTML e para
quando alguém de fora do time precisa olhar sem abrir um editor -- por isso
ele e um arquivo único, com o CSS embutido e sem nenhum recurso externo.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .deriva import Divergencia
from .formato import numero, pct
from .perfil import Perfil
from .regras import STATUS_ALERTA, STATUS_FALHA, STATUS_OK, Relatorio

SIMBOLO = {STATUS_OK: "ok", STATUS_ALERTA: "alerta", STATUS_FALHA: "FALHA"}


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def perfil_em_markdown(perfil: Perfil) -> str:
    linhas = [
        f"# Perfil de {perfil.origem}",
        "",
        f"Gerado em {perfil.gerado_em}. {perfil.linhas} linhas, "
        f"{len(perfil.colunas)} colunas.",
        "",
        "| Coluna | Tipo | Nulos | Distintos | Mínimo | Máximo |",
        "|--------|------|-------|-----------|--------|--------|",
    ]

    for c in perfil.colunas:
        linhas.append(
            f"| {c.nome} | {c.tipo_inferido} | {c.nulos} ({pct(c.nulos_pct)}%) | "
            f"{c.distintos} ({pct(c.distintos_pct)}%) | {numero(c.minimo)} | {numero(c.maximo)} |"
        )

    observacoes = []
    for c in perfil.colunas:
        if c.candidata_a_chave:
            observacoes.append(f"- `{c.nome}` e candidata a chave: sem nulos e sem repetições.")
        if c.constante:
            observacoes.append(f"- `{c.nome}` tem valor único em todas as linhas.")
        if c.nulos_pct > 50:
            observacoes.append(f"- `{c.nome}` está vazia em {pct(c.nulos_pct)}% das linhas.")

    if observacoes:
        linhas.extend(["", "## Observacoes", "", *observacoes])

    dominios = [c for c in perfil.colunas if c.valores_frequentes]
    if dominios:
        linhas.extend(["", "## Valores mais frequentes", ""])
        for c in dominios:
            amostra = ", ".join(f"{valor} ({qtd})" for valor, qtd in c.valores_frequentes)
            linhas.append(f"- **{c.nome}**: {amostra}")

    return "\n".join(linhas) + "\n"


def validacao_em_markdown(relatorio: Relatorio) -> str:
    falhas = relatorio.contar(STATUS_FALHA)
    alertas = relatorio.contar(STATUS_ALERTA)
    veredito = "reprovado" if falhas else ("aprovado com alertas" if alertas else "aprovado")

    linhas = [
        f"# Validação de {relatorio.origem}",
        "",
        f"Executada em {datetime.now():%d/%m/%Y às %H:%M}. "
        f"{relatorio.linhas} linhas avaliadas.",
        "",
        f"**Resultado: {veredito}** -- {relatorio.contar(STATUS_OK)} regras ok, "
        f"{alertas} alertas, {falhas} falhas.",
        "",
        "| Escopo | Regra | Status | Falhas | Detalhe |",
        "|--------|-------|--------|--------|---------|",
    ]

    # Falhas primeiro: quem abre o relatório quer ver o problema, não rolar
    # até o fim da lista para achar.
    ordem = {STATUS_FALHA: 0, STATUS_ALERTA: 1, STATUS_OK: 2}
    for r in sorted(relatorio.resultados, key=lambda r: (ordem[r.status], r.escopo)):
        linhas.append(
            f"| {r.escopo} | {r.regra} | {SIMBOLO[r.status]} | "
            f"{r.falhas} ({pct(r.falhas_pct)}%) | {r.detalhe} |"
        )

    return "\n".join(linhas) + "\n"


def deriva_em_markdown(
    base: Perfil, atual: Perfil, divergencias: list[Divergencia]
) -> str:
    linhas = [
        "# Comparação de perfis",
        "",
        f"Base: {base.origem} ({base.gerado_em}, {base.linhas} linhas)",
        f"Atual: {atual.origem} ({atual.gerado_em}, {atual.linhas} linhas)",
        "",
    ]

    if not divergencias:
        linhas.append("Nenhuma divergência acima do limite configurado.")
        return "\n".join(linhas) + "\n"

    linhas.extend(
        [
            f"{len(divergencias)} divergências encontradas.",
            "",
            "| Coluna | Aspecto | Antes | Agora | Gravidade |",
            "|--------|---------|-------|-------|-----------|",
        ]
    )
    for d in divergencias:
        linhas.append(
            f"| {d.coluna} | {d.aspecto} | {d.antes} | {d.agora} | {d.gravidade} |"
        )

    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
ESTILO = """
:root { color-scheme: light dark; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  max-width: 68rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.55;
}
h1 { font-size: 1.6rem; margin-bottom: .2rem; }
p.meta { color: #666; margin-top: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem; }
th, td { border: 1px solid #ccc; padding: .45rem .6rem; text-align: left; }
th { background: #f3f3f3; }
@média (prefers-color-scheme: dark) {
  th { background: #2a2a2a; }
  th, td { border-color: #444; }
  p.meta { color: #aaa; }
}
td.falha { background: #fdd; font-weight: 600; }
td.alerta { background: #fef3cd; }
td.ok { color: #2a7a2a; }
@média (prefers-color-scheme: dark) {
  td.falha { background: #5a2020; }
  td.alerta { background: #5a4a15; }
  td.ok { color: #7fd17f; }
}
"""


def _escapar(texto: object) -> str:
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _pagina(titulo: str, meta: str, corpo: str) -> str:
    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escapar(titulo)}</title>
<style>{ESTILO}</style>
</head>
<body>
<h1>{_escapar(titulo)}</h1>
<p class="meta">{_escapar(meta)}</p>
{corpo}
</body>
</html>
"""


def validacao_em_html(relatorio: Relatorio) -> str:
    falhas = relatorio.contar(STATUS_FALHA)
    alertas = relatorio.contar(STATUS_ALERTA)
    veredito = "reprovado" if falhas else ("aprovado com alertas" if alertas else "aprovado")

    ordem = {STATUS_FALHA: 0, STATUS_ALERTA: 1, STATUS_OK: 2}
    corpo = [
        "<table><thead><tr>",
        "<th>Escopo</th><th>Regra</th><th>Status</th><th>Falhas</th><th>Detalhe</th>",
        "</tr></thead><tbody>",
    ]
    for r in sorted(relatorio.resultados, key=lambda r: (ordem[r.status], r.escopo)):
        corpo.append(
            f"<tr><td>{_escapar(r.escopo)}</td><td>{_escapar(r.regra)}</td>"
            f'<td class="{r.status}">{SIMBOLO[r.status]}</td>'
            f"<td>{r.falhas} ({pct(r.falhas_pct)}%)</td>"
            f"<td>{_escapar(r.detalhe)}</td></tr>"
        )
    corpo.append("</tbody></table>")

    meta = (
        f"{relatorio.linhas} linhas avaliadas em {datetime.now():%d/%m/%Y às %H:%M}. "
        f"Resultado: {veredito}."
    )
    return _pagina(f"Validação de {relatorio.origem}", meta, "\n".join(corpo))


def perfil_em_html(perfil: Perfil) -> str:
    corpo = [
        "<table><thead><tr>",
        "<th>Coluna</th><th>Tipo</th><th>Nulos</th><th>Distintos</th>",
        "<th>Minimo</th><th>Maximo</th>",
        "</tr></thead><tbody>",
    ]
    for c in perfil.colunas:
        corpo.append(
            f"<tr><td>{_escapar(c.nome)}</td><td>{_escapar(c.tipo_inferido)}</td>"
            f"<td>{c.nulos} ({pct(c.nulos_pct)}%)</td>"
            f"<td>{c.distintos} ({pct(c.distintos_pct)}%)</td>"
            f"<td>{_escapar(c.minimo or '-')}</td><td>{_escapar(c.maximo or '-')}</td></tr>"
        )
    corpo.append("</tbody></table>")

    meta = f"{perfil.linhas} linhas, {len(perfil.colunas)} colunas. Gerado em {perfil.gerado_em}."
    return _pagina(f"Perfil de {perfil.origem}", meta, "\n".join(corpo))


def salvar(conteudo: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return destino
