---
name: enem-inse-app
description: Convenções do app "Posição no Enem" (Streamlit + Polars + microdados do INEP cruzados com INSE). Use ao adicionar análises ou gráficos ao dashboard, ler os microdados do Enem, tratar planilhas do INSE, decodificar valores do formulário, baixar dados do site do INEP ou navegar pela arquitetura em camadas do projeto.
---

# Posição no Enem — Convenções do Projeto

## Overview

Este skill captura as convenções extraídas do histórico do Git do app **Posição no Enem**: um Streamlit app que compara a nota de um candidato com os microdados reais do Enem, usando o INSE (Indicador de Nível Socioeconômico do INEP) para comparar com pessoas de perfil parecido. Projeto acadêmico em grupo, todo em português.

O padrão central é a **arquitetura em camadas com contrato rígido entre arquivos**. Cada arquivo tem um papel único e não vaza responsabilidades:

```
app.py  →  main.py  →  extrator_microdados.py (lê) + tabela.py (trata)  →  main.py  →  app.py
```

| Arquivo | Responsabilidade | Proibido |
|---|---|---|
| `app.py` | Só a interface: páginas, formulário, dashboard | Ler dados, conhecer códigos do INEP |
| `main.py` | Centro do fluxo: carrega dados 1x com `@cache`, **decodifica** texto→código, chama `tabela.py` | Conter cálculo estatístico |
| `tabela.py` | Tratamento e análises puras em Polars. Recebe DataFrames e códigos, devolve DataFrames/dicts pequenos | Qualquer `st.*` (Streamlit), decodificação |
| `extrator_microdados.py` | Baixa microdados/INSE, gera dicionários, converte CSV→parquet, lê arquivos | Lógica de análise |
| `graficos/` | Um arquivo por gráfico, só o desenho (Altair) | Cálculo |
| `config.py` | Pastas de dados (`ZIPs/`, `dump/`, `dados/`) | — |

## Patterns

### Pattern 1: Receita em 4 passos para adicionar uma análise ao dashboard

- **When to use**: sempre que um gráfico, tabela ou métrica nova for parar no dashboard.
- **Implementation**: o caminho é sempre o mesmo (documentado no README e nos commits "App Esqueleto" e "Reorganização do Fluxo"):
  1. **Cálculo no `tabela.py`** — função recebe DataFrames + valores já em códigos, devolve DataFrame/dict pequeno pronto para desenhar.
  2. **`main.analisar()` devolve o resultado numa chave nova** do dicionário de retorno.
  3. **Desenho em `graficos/<seu_arquivo>.py`** — função `grafico_x(df) -> alt.Chart` (e, se possível, uma `frase_x(df) -> str` explicando o resultado).
  4. **Ligar no SEU espaço do dashboard** em `pagina_dashboard()` — cada integrante é dono de um só espaço.
- **Example**:

```python
# 1. tabela.py — sem Streamlit, sem decodificação
def media_por_area(df_nivel: pl.DataFrame, nivel: str) -> pl.DataFrame:
    grupo = df_nivel.filter(pl.col('NIVEL_ESTIMADO') == nivel)
    return pl.DataFrame({
        'AREA': COLUNAS_NOTA,
        'MEDIA': [grupo[coluna].mean() for coluna in COLUNAS_NOTA],
    })

# 2. main.py, dentro de analisar()
return {
    ...
    'media_por_area': tabela.media_por_area(df_nivel, nivel),
}

# 3. graficos/media_area.py
def grafico_media_area(df: pl.DataFrame) -> alt.Chart:
    return alt.Chart(df).mark_bar().encode(
        x=alt.X('AREA:N', title=None),
        y=alt.Y('MEDIA:Q', title='Média do seu grupo INSE'),
    )

# 4. app.py — só o seu espaço
st.altair_chart(media_area.grafico_media_area(resultado['media_por_area']), width='stretch')
```

**Checklist** (do README): cálculo em `tabela.py` sem Streamlit ✓ resultado numa chave nova de `analisar()` ✓ desenho em `graficos/` ✓ só o seu espaço alterado no `app.py` ✓ testado com dados de verdade (Colab/servidor, ~12 GB RAM) ✓

### Pattern 2: Decodificação texto → código no `main.py`

- **When to use**: qualquer campo novo no formulário, ou sempre que a UI manda texto que precisa virar código do INEP.
- **Implementation**: o app só manda texto ("São Paulo", "Feminino"); a conversão fica no `main.py` usando o `DICIONARIO_{ano}.json` (os textos mudam de ano para ano). Matching é insensível a acento/caixa via NFKD. Opções de dropdown vêm SEMPRE de `main.opcoes_formulario()`, nunca escritas à mão.
- **Example**:

```python
def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    return texto.strip().lower()

def decodificar(variavel: str, descricao: str) -> str:
    """Converte a descrição escolhida no app no código da variável segundo o dicionário do ano."""
    categorias = _dicionario()[variavel]
    if str(descricao) in categorias:
        return str(descricao)
    alvo = _normalizar(descricao)
    for codigo, desc in categorias.items():
        if _normalizar(desc) == alvo:
            return codigo
    raise ValueError(f"Valor '{descricao}' não encontrado em {variavel}")
```

Conversões não-dicionário (ex.: idade → `TP_FAIXA_ETARIA`) também ficam no `main.py` (`calcular_faixa_etaria`).

**Atenção: campos cujas opções dependem de outro campo ficam FORA do `st.form`.** Dentro de um form o script só roda no envio — uma cascata como UF → município não atualiza lá. O padrão do projeto é o bloco "Localização" fora do form: o `st.selectbox` da UF alimenta `main.opcoes_municipios(uf)`, que devolve as opções do `st.selectbox` de município (`key` fixa para manter a escolha; trocar de UF limpa a escolha sozinho, porque o valor sai das opções). O `st.form` guarda só o que é preenchido de uma vez (Nota + Perfil). Detalhe da busca nativa do `st.selectbox` (digitar na lista): o JS só faz `toLowerCase`, sem normalizar acentos — "cuiaba" pode não achar "Cuiabá"; com a lista já filtrada pela UF isso raramente atrapalha, mas se precisar de busca insensível a acentos, filtre no script com `main._normalizar`.

### Pattern 3: Leitura lazy com Polars para arquivos gigantes

- **When to use**: sempre que tocar os microdados (CSV de 2023 tem 1,7 GB — não cabe em memória de máquina comum).
- **Implementation**: parquet é o formato canônico (`dados/dados_{ano}/`). Leitura é lazy (`scan_parquet`) e **seleciona só as colunas pedidas**. CSVs latin1 são convertidos para UTF-8 em blocos de 16 MB antes do `scan_csv` (o Polars só lê UTF-8 de forma lazy).
- **Example**:

```python
def ler_microdados(ano: int, colunas: list[str]) -> pl.DataFrame:
    """Lê só as colunas pedidas (as que existirem naquele ano) do parquet dos microdados."""
    df = pl.scan_parquet(caminho_microdados(ano))
    existentes = [coluna for coluna in colunas if coluna in df.collect_schema().names]
    return df.select(existentes).collect()
```

Precisa de uma coluna a mais (ex.: `Q006`)? Adicione em `COLUNAS_MICRODADOS` no `main.py` — não leia o arquivo inteiro.

### Pattern 4: Pipeline idempotente e download resumível

- **When to use**: qualquer etapa de extração/download.
- **Implementation**: cada passo verifica se o produto já existe e pula ("já existe, pulando"); downloads usam `Range` para retomar, backoff exponencial (1, 2, 4, 8, 16 s) e tratam servidor sem suporte a resume; o site do INEP não envia o certificado intermediário, então monta-se um CA bundle na mão (`garantir_ca_bundle()`); loops de organização avisam e fazem `continue` em vez de explodir.
- **Example**:

```python
def pegar_com_retry(url, headers, ca_bundle, offset=0, tentativas=5):
    for i in range(tentativas):
        try:
            req_headers = {**headers, "Range": f"bytes={offset}-"} if offset else headers
            resposta = requests.get(url, stream=True, timeout=30, verify=str(ca_bundle), headers=req_headers)
            resposta.raise_for_status()
            return resposta
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            espera = 2 ** i  # backoff exponencial
            print(f"Tentativa {i+1} falhou ({e}). Esperando {espera}s...")
            time.sleep(espera)
    raise RuntimeError("Não foi possível baixar o arquivo após várias tentativas.")
```

### Pattern 5: Segurança estatística com `MIN_CANDIDATOS`

- **When to use**: qualquer estatística calculada sobre um grupo de candidatos.
- **Implementation**: abaixo de `tabela.MIN_CANDIDATOS = 30` o percentil/média fica instável e NÃO é calculado. Grupos pequenos viram mensagem explícita ("dados insuficientes (N candidatos)"), nunca omissão silenciosa.
- **Example**:

```python
# tabela.py
grupo = df_nivel.filter((pl.col('NIVEL_ESTIMADO') == nivel) & pl.col(coluna_nota).is_not_null())
if grupo.height < MIN_CANDIDATOS:
    raise ValueError(f'Há apenas {grupo.height} candidatos no {nivel}, poucos para comparar.')
```

```python
# graficos/percentil.py — avisa em vez de sumir com a escala
sem_dados = df_percentis.filter(pl.col('PERCENTIL').is_null())
for escala, candidatos in zip(sem_dados['ESCALA'], sem_dados['CANDIDATOS']):
    frase += f' {escala}: dados insuficientes ({candidatos} candidatos).'
```

### Pattern 6: Tolerância a variação entre anos

- **When to use**: qualquer código que toque mais de um ano de dados (2019, 2021, 2023).
- **Implementation**: colunas mudam de nome (2019: `RENOMEAR_INSE_2019`), planilhas têm linhas de observação antes do cabeçalho e asteriscos nos nomes (detecta a linha do cabeçalho dinamicamente), `CO_ESCOLA` só existe até 2019 (join condicional), e cada ano tem seu `DICIONARIO_{ano}.json` porque os textos mudam.
- **Example**:

```python
# extrator_microdados.py — detecta o cabeçalho onde ele estiver
bruto = pl.read_excel(caminho_xlsx, read_options={'header_row': None, 'n_rows': 20})
linha_cabecalho = next(
    i for i, valor in enumerate(bruto.to_series(0).to_list())
    if valor in ('NU_ANO_SAEB', 'CO_UF', 'CO_ESCOLA')
)
df = pl.read_excel(caminho_xlsx, read_options={'header_row': linha_cabecalho})
return df.rename({coluna: coluna.strip('*').strip() for coluna in df.columns})
```

```python
# tabela.py — coluna que só existe em alguns anos
if 'CO_ESCOLA' in df.columns:
    df = df.join(..., how='left')
    nivel = pl.coalesce('NIVEL_DA_ESCOLA', 'NIVEL_DO_MUNICIPIO')
else:
    nivel = pl.col('NIVEL_DO_MUNICIPIO')
```

### Pattern 7: Posse de arquivos por integrante (evitar conflito no Git)

- **When to use**: trabalho em grupo no mesmo repositório.
- **Implementation**: cada integrante é dono de **um** dos quatro espaços do dashboard e mexe só nos seus arquivos (`graficos/<seu_arquivo>.py` + seu espaço em `app.py`). Mudanças no contrato compartilhado (`tabela.py`, `main.py`) seguem a receita dos 4 passos para não quebrar os outros.
- **Example**: Gráfico 1 → `graficos/percentil.py`, Gráfico 2 → `graficos/regional.py`, Gráfico 3 → `graficos/distribuicao.py`; o espaço restante está marcado com `# TODO: gráfico/tabela de outro integrante`.

## Best Practices

1. **Respeite a camada**: `st.*` nunca em `tabela.py`/`extrator_microdados.py`; códigos do INEP nunca em `app.py`; decodificação nunca em `tabela.py`.
2. **Carregue uma vez por processo**: dados compartilhados ficam em funções `@cache` no `main.py` (`_dicionario()`, `_inse()`, `_df_nivel()`); o app usa sempre o ano mais recente extraído (`ano_atual()`).
3. **Notebooks são para exploração**; a lógica oficial fica nos `.py`. O `Colab_notebook.ipynb` não faz parte do app.
4. **Valide o formulário antes de calcular**: checos explícitos campo a campo em `pagina_formulario()` com mensagens de erro específicas; use `st.form`.
5. **Arredonde para exibição** (`round(x, 1)`) no ponto de cálculo, não deixe float cru chegar ao gráfico.
6. **Documente decisões de dados** na seção "Decisões sobre os dados" do README (ex.: nível INSE vem da escola se informada, senão do município).
7. **Comentes explicam o porquê** (peculiaridades dos dados), em português, com separadores de seção `# ---- nome`.
8. **Mensagens de commit**: prefixo curto + nome (`Feature <Nome>`, `Fix - <Nome>`, `App <Nome>`), em português, com problemas conhecidos/limitações documentados no corpo.

## Common Mistakes

1. **Ler o CSV inteiro com `read_csv`/pandas** — 1,7 GB trava máquinas comuns. Como evitar: lazy scan + seleção de colunas + parquet (Pattern 3).
2. **Calcular estatística em grupo pequeno** — percentil de 12 candidatos é ruído. Como evitar: sempre checar `MIN_CANDIDATOS` (Pattern 5).
3. **Escrever rótulos do dicionário à mão** — "concluirei o Ensino Médio em 2023" muda de ano. Como evitar: opções vêm de `opcoes_formulario()`/`DICIONARIO_{ano}.json` (Pattern 2).
4. **Assumir que as colunas do INEP são estáveis entre anos** — 2019 tem nomes diferentes e `CO_ESCOLA` some depois. Como evitar: renames explícitos e joins condicionais (Pattern 6).
5. **Sumir silenciosamente com dados vazios** — o usuário fica sem entender. Como evitar: mensagem explícita de dados insuficientes (Pattern 5).
6. **Misturar decodificação em `tabela.py` ou UI em `main.py`** — quebra o contrato e duplica lógica. Como evitar: receita dos 4 passos (Patterns 1 e 2).
7. **Confiar no SSL do site do INEP** — falta o certificado intermediário. Como evitar: `garantir_ca_bundle()` + `verify=` sempre (Pattern 4).
8. **Editar o dashboard todo quando só um espaço é seu** — conflito no Git em grupo. Como evitar: posse por integrante (Pattern 7).

## Examples

### Good Example

Análise nova completa, seguindo as camadas (resumo do fluxo real de `medias_por_uf`):

```python
# tabela.py — cálculo puro, formato longo pronto para desenhar, sem Streamlit
def medias_por_uf(df_nivel: pl.DataFrame, df_inse_municipios: pl.DataFrame) -> pl.DataFrame:
    df = (
        df_nivel
        .group_by('CO_UF_REF')
        .agg(
            pl.len().alias('CANDIDATOS'),
            *[pl.col(coluna).mean().round(1).alias(coluna) for coluna in COLUNAS_NOTA],
        )
        .join(ufs(df_inse_municipios), left_on='CO_UF_REF', right_on='CO_UF', how='inner')
    )
    return df.unpivot(
        COLUNAS_NOTA, index=['NO_UF', 'CANDIDATOS'],
        variable_name='COLUNA', value_name='MEDIA',
    )
```

```python
# main.py — só orquestra e devolve numa chave nova
'medias_uf': tabela.medias_por_uf(df_nivel, df_municipios),
```

```python
# graficos/regional.py — só desenha
def grafico_medias_uf(df_medias, area, uf_usuario) -> alt.Chart:
    ...
```

### Anti-pattern

```python
# NÃO FAÇA: tudo embrulhado num arquivo só
def pagina_dashboard():                     # ❌ UI
    df = pl.read_csv('dados/dados_2023/MICRODADOS_ENEM_2023.csv')  # ❌ CSV inteiro, não-lazy
    media = df.filter(pl.col('NIVEL') == 'Nível I')['NU_NOTA_MT'].mean()  # ❌ sem MIN_CANDIDATOS
    if df.height == 0:
        return                              # ❌ falha silenciosa
    sexo_codigo = {'M': 0, 'F': 1}[sexo]    # ❌ decodificação hardcoded, ignora o dicionário do ano
    st.altair_chart(alt.Chart(df).mark_bar().encode(x='TP_SEXO', y='NU_NOTA_MT'))  # ❌ códigos INEP na UI
```

## Referências

- `README.md` — arquitetura, receita dos 4 passos, checklist e "Decisões sobre os dados" (a fonte da verdade do contrato).
- Commits de referência: `c1c19ac` (estrutura em camadas nasce), `a87347d` (Fix com problemas documentados no corpo), `0a6ccf5`/`f501f12` (esqueleto do app e reorganização do fluxo).
