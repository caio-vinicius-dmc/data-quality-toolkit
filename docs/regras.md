# Catálogo de regras

O arquivo de regras é um TOML com dois tipos de bloco: um `[dataset]`
opcional e quantos `[[coluna]]` forem necessários.

```toml
[dataset]
minimo_de_linhas = 300
colunas_obrigatorias = ["id_cliente", "email"]

[[coluna]]
nome = "email"
nao_nulo = true
unico = true
formato = '[^@\s]+@[^@\s]+\.[A-Za-z]{2,}'
maximo_de_falhas_pct = 3.0
```

Cada regra vira uma linha no relatório com um destes três status:

- **ok** -- nenhuma linha reprovou.
- **alerta** -- houve reprovação, mas dentro da tolerância configurada.
- **falha** -- houve reprovação e não há tolerância, ou ela foi estourada.
  É o único status que faz o comando sair com código 1.

## Regras de dataset

### `minimo_de_linhas`

```toml
[dataset]
minimo_de_linhas = 300
```

Pega o caso mais comum de falha silenciosa: o arquivo chegou, o processo
rodou sem erro, mas veio só um pedaço. Sem essa regra a carga passa e o
problema só aparece no relatório da área de negocio.

### `colunas_obrigatorias`

```toml
colunas_obrigatorias = ["id_cliente", "email", "data_cadastro"]
```

Coluna ausente é sempre falha, nunca alerta. Se a coluna não existe, as
outras regras dela não tem como ser avaliadas -- deixar passar como aviso
daria uma falsa sensação de que o resto foi verificado.

## Regras de coluna

Todo bloco precisa do campo `nome`. As demais chaves são opcionais e podem
ser combinadas.

### `nao_nulo`

```toml
nao_nulo = true
```

Considera ausente: o nulo de verdade, a string vazia, a string só com
espaços e o texto literal `nan`. Esse último caso aparece quando o dado já
passou por um pandas mal configurado em algum ponto anterior da cadeia.

### `unico`

```toml
unico = true
```

Procura repetições apenas entre os valores preenchidos. Dois nulos não
contam como duplicidade -- é o mesmo critério de um índice único no banco.

O detalhe do relatório traz até três exemplos dos valores repetidos, o que
costuma ser suficiente para achar a origem do problema.

### `entre`

```toml
entre = [18, 110]
```

Faixa numérica fechada nas duas pontas. Valor não numérico também conta
como falha: se a coluna tem faixa configurada, texto ali dentro significa
que o dado não é do tipo que a regra assume.

### `dominio`

```toml
dominio = ["site", "app", "indicacao", "loja"]
```

Lista fechada. A comparação e por texto exato depois de remover espaços das
pontas, então `SP` e `sp` são valores diferentes -- proposital, porque
variação de caixa costuma indicar duas origens gravando na mesma coluna.

O relatório mostra até cinco valores inesperados, ordenados.

### `formato`

```toml
formato = '\d{4}-\d{2}-\d{2}'
```

Expressão regular do Python, avaliada com casamento **total**: não é preciso
escrever `^` e `$`. Use aspas simples no TOML para não ter que escapar as
barras invertidas duas vezes.

### `tamanho_maximo`

```toml
tamanho_maximo = 80
```

Comprimento em caracteres. Útil quando o destino tem coluna `varchar(n)` e
a carga quebraria no meio.

## Tolerancias

### `maximo_de_nulos_pct`

```toml
maximo_de_nulos_pct = 15.0
```

Usada sozinha, sem `nao_nulo`, quando o campo e legitimamente opcional mas
existe um limite a partir do qual algo está errado com a origem.

### `maximo_de_falhas_pct`

```toml
maximo_de_falhas_pct = 3.0
```

Vale para todas as regras da coluna. Abaixo do limite, a reprovação vira
alerta e a execução continua; acima, vira falha.

Serve para defeito conhecido e tolerado: alguns e-mails tortos numa base
antiga não justificam barrar a carga, mas precisam continuar visíveis no
relatório para não virarem paisagem.

## Limitações conhecidas do motor

- **Não há regra entre colunas.** Algo como `data_fim >= data_inicio` ou
  `valor_total = quantidade * valor_unitario` não tem como ser expresso.
  Seria a próxima adição mais útil.
- **Não há checagem de chave estrangeira** contra outro arquivo ou tabela.
- **A ordem de avaliação não é configurável.** Se `nao_nulo` falha, as
  demais regras da coluna rodam mesmo assim, sobre os valores preenchidos.
  Em geral é o que se quer, mas gera linhas redundantes no relatório quando
  a coluna está quase toda vazia.
