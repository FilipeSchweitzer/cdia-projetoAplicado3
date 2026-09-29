# Posição no Enem

App em Streamlit que compara a nota de um candidato (do Enem ou de um simulado) com os microdados reais do Enem. A comparação usa o **INSE**, o Indicador de Nível Socioeconômico do INEP, para comparar o candidato com pessoas de perfil socioeconômico parecido, e não só com o Brasil inteiro.

O app tem três páginas: **login → formulário → dashboard**. O dashboard tem uma mensagem ("você está acima / abaixo / dentro da média") e quatro espaços para gráficos ou tabelas, **um para cada integrante do grupo**.

## Estrutura

```
app.py  →  main.py  →  extrator_microdados.py (lê os dados)  +  tabela.py (trata)  →  main.py  →  app.py
```

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Só a interface: páginas, formulário e dashboard. Não lê dados e não conhece códigos do INEP. |
| `main.py` | Centro do fluxo. Carrega os dados uma vez, **decodifica** o que vem do formulário (ex.: "São Paulo" → `35`, idade → faixa etária), chama o `tabela.py` e devolve o resultado ao app. |
| `tabela.py` | Tratamento e análises. Recebe DataFrames e dados já em códigos e devolve DataFrames ou dicionários. Não tem nada de Streamlit. |
| `extrator_microdados.py` | Baixa os microdados do Enem e as planilhas do INSE, gera o dicionário de variáveis, converte para parquet e lê os arquivos. |
| `graficos/` | Um arquivo por gráfico, só com o desenho (Altair/Streamlit). |
| `config.py` | Pastas de dados (`ZIPs/`, `dump/`, `dados/`). |
| `tabela.ipynb` | Notebook de exploração: importa os `.py` para testar. A lógica oficial fica nos `.py`. |
| `Colab_notebook.ipynb` | Cópia de trabalho para ler os dados no Colab. Não faz parte do app. |

## Rodando

> ⚠️ **Os microdados não cabem na memória de um notebook comum** (o CSV de 2023 tem 1,7 GB). Rodar a extração ou o app com dados reais numa máquina fraca pode travar o computador. Use o Colab ou o servidor, com pelo menos ~12 GB de RAM.

### 1. Dependências

```bash
pip install -r requirements.txt
```

A extração também precisa do `7z` instalado no sistema para descompactar o zip do INEP.

### 2. Baixar e preparar os dados

```bash
python extrator_microdados.py 2023        # ou 2019, 2021; sem argumento usa 2023
```

Só existem **2019, 2021 e 2023**, os anos em que o INEP publicou o INSE; os outros anos não têm como ser cruzados. O script:

1. baixa e descompacta os microdados do Enem;
2. baixa as planilhas de INSE de escolas e de municípios;
3. gera `DICIONARIO_{ano}.json` a partir do dicionário em Excel do INEP;
4. converte os CSVs para parquet.

Os arquivos de cada ano ficam em `dados/dados_{ano}/`:

```
MICRODADOS_ENEM_{ano}.parquet
INSE_ESCOLAS_{ano}.parquet
INSE_MUNICIPIOS_{ano}.parquet
DICIONARIO_{ano}.json
```

### 3. Abrir o app

```bash
streamlit run app.py        # ou python app.py
```

O app usa sempre o ano mais recente que já foi extraído. Se nenhum ano foi extraído, o formulário mostra um erro pedindo para rodar o extrator.

## Como adicionar uma análise no dashboard

Cada integrante é dono de **um** dos quatro espaços do dashboard. Já estão feitos: Gráfico 1 (percentil, `graficos/percentil.py`), Gráfico 2 (médias por UF e município, `graficos/regional.py`) e Gráfico 3 (distribuição de notas por área, `graficos/distribuicao.py`). Para não haver conflito no Git, cada um mexe só nos seus arquivos e no seu espaço.

O caminho é sempre o mesmo, em quatro passos. O exemplo abaixo cria o gráfico "média do grupo INSE por área".

### Passo 1: o cálculo vai no `tabela.py`

Escreva uma função que recebe DataFrames e valores já em códigos e devolve um DataFrame ou dicionário **pequeno**, pronto para desenhar. Nada de Streamlit aqui.

```python
# tabela.py
def media_por_area(df_nivel: pl.DataFrame, nivel: str) -> pl.DataFrame:
    grupo = df_nivel.filter(pl.col('NIVEL_ESTIMADO') == nivel)
    return pl.DataFrame({
        'AREA': COLUNAS_NOTA,
        'MEDIA': [grupo[coluna].mean() for coluna in COLUNAS_NOTA],
    })
```

O DataFrame principal é o `df_nivel`: os microdados do Enem já cruzados com o INSE. Ele tem:

| Coluna | Conteúdo |
|---|---|
| `NU_NOTA_CN`, `NU_NOTA_CH`, `NU_NOTA_LC`, `NU_NOTA_MT`, `NU_NOTA_REDACAO` | notas (em `tabela.COLUNAS_NOTA`) |
| `NIVEL_ESTIMADO` | nível INSE do candidato (`'Nível I'` … `'Nível VII'`) |
| `CO_MUNICIPIO_REF`, `CO_UF_REF` | município e UF de referência do candidato |
| `TP_FAIXA_ETARIA`, `TP_SEXO`, `TP_COR_RACA`, `TP_NACIONALIDADE`, `TP_ST_CONCLUSAO`, `TP_ANO_CONCLUIU`, `IN_TREINEIRO` | perfil |

Se precisar de outra coluna dos microdados (ex.: `Q006`, a renda), adicione em `COLUNAS_MICRODADOS` no `main.py`.

Use `tabela.MIN_CANDIDATOS` para não calcular nada com grupos pequenos demais.

### Passo 2: o `main.py` chama a função e devolve o resultado

Adicione uma chave nova no dicionário que `analisar()` devolve:

```python
# main.py, dentro de analisar()
return {
    ...
    'media_por_area': tabela.media_por_area(df_nivel, nivel),
}
```

Dentro de `analisar()` você já tem:

| Variável | O que é |
|---|---|
| `df_nivel` | os dados (Passo 1) |
| `nivel` | nível INSE do usuário |
| `coluna_nota` | coluna da área escolhida (ex.: `'NU_NOTA_MT'`) |
| `co_uf` | código da UF escolhida |
| `candidato` | perfil do usuário em códigos (`tabela.Candidato`) |
| `entrada` | o que veio do formulário, ex.: `entrada['nota']`, `entrada['municipio']` |

Se a análise precisar de um **campo novo no formulário**:
1. Adicione o campo no `app.py`, em `pagina_formulario()`, e coloque o valor em `entrada`.
2. Se for um dropdown de valores fixos, as opções devem vir do `main.opcoes_formulario()`. Por exemplo, uma variável do dicionário entra em `VARIAVEIS_PERFIL`.
3. A conversão de texto para código fica no `main.py`, com `decodificar(variavel, descricao)` ou uma função parecida. O app só manda texto.

### Passo 3: o desenho vai num arquivo seu em `graficos/`

```python
# graficos/media_area.py
import altair as alt
import polars as pl


def grafico_media_area(df: pl.DataFrame) -> alt.Chart:
    return alt.Chart(df).mark_bar().encode(
        x=alt.X('AREA:N', title=None),
        y=alt.Y('MEDIA:Q', title='Média do seu grupo INSE'),
        tooltip=['AREA', alt.Tooltip('MEDIA:Q', format='.1f')],
    )
```

Veja `graficos/percentil.py` como referência. Ele tem o gráfico e uma frase explicando o resultado para o usuário.

### Passo 4: ligar no seu espaço do dashboard

No `app.py`, em `pagina_dashboard()`, troque o conteúdo do seu espaço, que está marcado com `# TODO`:

```python
# app.py
from graficos import media_area

...
with coluna_2:
    st.subheader('Média do seu grupo por área')
    st.altair_chart(media_area.grafico_media_area(resultado['media_por_area']), width='stretch')
```

### Checklist

- [ ] cálculo em `tabela.py`, sem Streamlit e sem decodificação
- [ ] `main.analisar()` devolve o resultado numa chave nova
- [ ] desenho em `graficos/<seu_arquivo>.py`
- [ ] só o seu espaço do dashboard foi alterado no `app.py`
- [ ] testado com dados de verdade no Colab ou no servidor, não num notebook fraco

## Decisões sobre os dados

- **O nível INSE do candidato vem do município.** A partir de 2020 os microdados do Enem não trazem o código da escola, só o município. O município usado é o da escola, se o candidato informou; se não, é o município onde ele fez a prova (`CO_MUNICIPIO_REF`).
- **O nível INSE do usuário vem da escola, se informada.** Se não, vem do município.
- **Classificação dos municípios.** A planilha de municípios do INSE só tem a média (`MEDIA_INSE`), então ela é classificada nas mesmas faixas que o INEP usa nas escolas daquele ano (`tabela.limites_niveis`). Usa-se a linha de total do município (`TP_TIPO_REDE = 6`, `TP_LOCALIZACAO = 0`).
- **Formato das planilhas por ano.** As planilhas de 2019 têm outros nomes de coluna e linhas de observação antes do cabeçalho. O extrator e o `tabela.py` já tratam isso.
- **Dicionário por ano.** Os textos e códigos do questionário mudam de um ano para outro (ex.: "concluirei o Ensino Médio em 2023"), por isso cada ano tem o seu `DICIONARIO_{ano}.json`.
