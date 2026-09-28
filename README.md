# data-quality-toolkit

Uma ferramenta de terminal que responde três perguntas sobre uma base de
dados, antes que ela vire relatório.

## Do que se trata, em linguagem simples

Todo mundo que trabalha com dados já recebeu uma planilha ou um arquivo e
teve que perguntar: **dá para confiar nisso?**

Normalmente a resposta vem depois — quando o relatório sai estranho,
alguém investiga e descobre que 6% das linhas estavam sem valor, ou que
tinha idade negativa, ou que o mesmo cliente aparecia duas vezes.

Esta ferramenta antecipa isso. Ela responde:

1. **Como esse dado é?** Quantas linhas, quantas em branco, qual o menor e
   o maior valor de cada coluna — comando `perfil`
2. **Ele respeita as regras que combinamos?** Idade entre 18 e 110, e-mail
   com formato válido, estado dentro da lista de siglas — comando
   `validar`
3. **Mudou alguma coisa desde a última carga?** A média saltou, o número
   de linhas em branco triplicou, uma coluna mudou de tipo — comando
   `comparar`

Funciona com arquivos CSV, arquivos Parquet e tabelas de PostgreSQL.

As regras ficam num arquivo de texto separado do código, porque quem
conhece o dado nem sempre é quem programa.

## O que você precisa ter instalado

- **Python 3.11 ou mais novo** —
  [python.org](https://www.python.org/downloads/), marcando "Add Python to
  PATH" na instalação.

Só isso. Não precisa de Docker nem de banco de dados.

## Instalação

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e .
```

No Linux ou macOS, a segunda linha é `source .venv/bin/activate`.

O `venv` é uma pasta isolada para as bibliotecas deste projeto, para elas
não se misturarem com as de outros. Quando funciona, o nome `(.venv)`
aparece no começo da linha do terminal.

Isso disponibiliza o comando `dq`. Para conferir:

```bash
dq --versao
```

Para ler arquivos Parquet: `pip install -e ".[parquet]"`.
Para ler tabelas do PostgreSQL: `pip install -e ".[postgres]"`.

## Como usar

A pasta `exemplos/` traz uma base de clientes com defeitos plantados, para
os comandos terem o que encontrar.

### Perfil: como é esse dado?

```bash
dq perfil exemplos/clientes.csv
```

```
Perfil de clientes.csv (400 linhas)
Coluna         Tipo       Em branco   Distintos      Mínimo          Máximo
id_cliente     inteiro    0 (0,00%)   397 (99,25%)   1               400
nome           texto      0 (0,00%)   177 (44,25%)   Ana Almeida     Vitor Souza
email          texto      0 (0,00%)   400 (100,00%)  ana.almeida90…  vitor.souza164…
idade          inteiro    0 (0,00%)   63 (15,75%)    -3              199
uf             texto      0 (0,00%)   11 (2,75%)     BA              XX
cidade         texto      0 (0,00%)   10 (2,50%)     Belo Horizonte  São Paulo
renda_mensal   decimal    31 (7,75%)  369 (92,25%)   1.517,21        17.946,21
data_cadastro  data       0 (0,00%)   304 (76,00%)   2024-01-02      2025-11-28
canal_origem   texto      0 (0,00%)   4 (1,00%)      app             site
ativo          booleano   0 (0,00%)   2 (0,50%)      false           true

  email: candidata a chave (sem nulos, sem repetições)
```

Duas coisas já saltam sem nenhuma regra escrita: **idade tem valor
negativo** (-3 e 199 não são idades) e **`uf` tem 11 valores distintos**,
sendo o último em ordem alfabética o `XX` — que não é sigla de estado
nenhum.

O tipo mostrado é o tipo **útil** da coluna, não o que o Python guardou.
O arquivo é lido todo como texto de propósito: a detecção automática
esconde problema, porque uma coluna de números inteiros com uma célula em
branco vira decimal e o defeito desaparece.

### Validação: respeita as regras?

```bash
dq validar exemplos/clientes.csv --regras exemplos/regras.toml
```

```
Escopo      Regra     Status   Falhas     Detalhe
id_cliente  unico     falha    4 (1,00%)  4 linhas repetidas (ex.: 1)
idade       entre     falha    4 (1,00%)  4 valores fora de [18, 110]
uf          dominio   falha    5 (1,25%)  5 fora do domínio (ex.: XX)
email       formato   alerta   6 (1,50%)  6 fora do padrão (ex.: ...)
...
17 ok, 1 alertas, 3 falhas.
```

As falhas vêm primeiro, depois os alertas, e por último as regras que
passaram. O nome da regra aparece como está escrito no arquivo `.toml` --
`unico`, `dominio`, `nao_nulo` -- para você poder procurar direto lá.

O comando termina com **código de erro** quando alguma regra falha, então
serve como etapa automática de um processo:

```bash
dq validar dados/carga.csv --regras regras.toml --markdown relatorio.md || exit 1
```

Alertas não derrubam a execução. Uma regra vira alerta quando você definiu
uma tolerância e o percentual de problemas ficou abaixo dela — útil para
defeito conhecido que ninguém vai corrigir hoje, mas que precisa continuar
visível.

### Gerando um primeiro arquivo de regras

Escrever regras do zero dá trabalho. A ferramenta gera um rascunho a
partir do que observa:

```bash
dq sugerir exemplos/clientes.csv --saida regras.toml
```

**Atenção:** o gerador descreve o dado **como ele está, defeitos
inclusive**. Se a base já tem idade 199, a faixa sugerida vai até 199. É
um ponto de partida para você revisar, não algo para sair usando.

### Comparação: mudou alguma coisa?

Guarde o retrato de uma carga que você sabe que está boa:

```bash
dq perfil dados/janeiro.csv --salvar base.perfil.json
```

E compare as próximas contra ela:

```bash
dq comparar base.perfil.json --contra dados/fevereiro.csv
```

```
Coluna        Aspecto               Antes      Agora                     Gravidade
id_cliente    valores distintos     99,25%     90,48%                    aviso
idade         média                 49,37      46,15 (6,5% de variação)  aviso
renda_mensal  percentual em branco  7,75%      22,86%                    alta
renda_mensal  média                 9.933,35   16.481,19 (65,9% ...)     alta
renda_mensal  valores distintos     92,25%     77,14%                    alta
```

Os três sinais mais úteis na prática: **mudança de tipo** (o formato
mudou), **salto no percentual em branco** (a origem parou de mandar o
campo) e **queda de valores distintos** (a carga duplicou).

O comando devolve código de erro quando há divergência grave.

### Lendo do PostgreSQL

```bash
cp .env.example .env     # preencha com um usuário somente leitura
dq validar vendas.pedidos --tabela --regras regras.toml
```

Nenhuma credencial vai para o código ou para o arquivo de regras. Se
faltar alguma configuração, o comando diz exatamente qual.

## As regras

O arquivo de regras é um texto simples:

```toml
[dataset]
minimo_de_linhas = 300

[[coluna]]
nome = "idade"
nao_nulo = true
entre = [18, 110]

[[coluna]]
nome = "uf"
dominio = ["SP", "RJ", "MG", "PR", "RS", "BA", "PE", "CE", "GO", "SC"]

[[coluna]]
nome = "email"
formato = '[^@\s]+@[^@\s]+\.[A-Za-z]{2,}'
maximo_de_falhas_pct = 3.0
```

As regras disponíveis:

| Regra | Onde se aplica | O que faz |
|-------|---------------|-----------|
| `minimo_de_linhas` | base inteira | pega carga que veio pela metade |
| `colunas_obrigatorias` | base inteira | pega mudança de formato |
| `nao_nulo` | coluna | em branco, vazio e "nan" contam como ausente |
| `unico` | coluna | procura repetições |
| `entre` | coluna | faixa de valores; texto ali também falha |
| `dominio` | coluna | lista fechada de valores aceitos |
| `formato` | coluna | expressão regular |
| `tamanho_maximo` | coluna | comprimento em caracteres |
| `maximo_de_nulos_pct` | coluna | tolerância de ausência |
| `maximo_de_falhas_pct` | coluna | rebaixa falha para alerta |

O detalhe de cada uma, com exemplos e o que ela **não** pega, está em
[docs/regras.md](docs/regras.md).

## Os relatórios

```bash
dq validar exemplos/clientes.csv --regras exemplos/regras.toml \
   --markdown relatorio.md --html relatorio.html
```

O Markdown serve para colar num chamado. O HTML é um arquivo único, com o
estilo embutido e nada vindo da internet, que abre em qualquer navegador.

## Estrutura das pastas

```
src/dq/fontes.py      lê CSV, Parquet e tabela
src/dq/perfil.py      estatísticas por coluna e detecção de tipo
src/dq/regras.py      o motor de regras e o gerador de rascunho
src/dq/deriva.py      a comparação entre dois retratos
src/dq/relatorio.py   Markdown e HTML
exemplos/             a base com defeitos plantados e as regras de exemplo
```

## Problemas comuns

**"Ler Parquet exige o pyarrow."** Instale o extra:
`pip install -e ".[parquet]"`.

**"Faltam variáveis de ambiente."** Você usou `--tabela` sem preencher o
`.env`. Copie o `.env.example` e complete com os dados do banco.

**"Arquivo de regras não encontrado."** Confira o caminho passado em
`--regras`. Ele é relativo à pasta onde você está.

**O comando `dq` não é reconhecido.** O ambiente virtual provavelmente não
está ativo. O nome `(.venv)` deve aparecer no começo da linha do terminal.

## Limitações

- O arquivo é carregado inteiro na memória. Para arquivos grandes use
  `--limite` para conferir uma amostra; validar uma base enorme por
  inteiro exigiria processamento em pedaços, que não foi implementado.
- **Não há regra entre colunas** (do tipo "data de fim depois da data de
  início") **nem entre arquivos** (conferir se todo pedido aponta para um
  cliente que existe). São as duas ausências que mais incomodam no uso
  real.
- A comparação olha apenas médias e contagens. Uma mudança de distribuição
  que mantenha a média passa despercebida.
- Os relatórios em HTML são estáticos, sem gráfico. A intenção era um
  arquivo único, sem depender de nada externo.

---

## 👤 Autor

Desenvolvido por **Caio Vinícius Barbosa Barros**.

Se você tiver dúvidas, sugestões ou quiser reportar um problema, sinta-se à vontade para entrar em contato:

*   **✉️ E-mail:** [caio@dynamicmotioncentury.com.br](mailto:caio@dynamicmotioncentury.com.br)
*   **🌐 Site/Portfólio:** [www.dynamicmotioncentury.com.br](https://dynamicmotioncentury.com.br)
*   **💼 LinkedIn:** [linkedin.com/in/caio-vinicius-dmc](https://linkedin.com/in/caio-vinicius-dmc)
*   **🐙 GitHub:** [@caio-vinicius-dmc](https://github.com/caio-vinicius-dmc)

💡 *Se este projeto te ajudou, deixe uma ⭐ no repositório!*
