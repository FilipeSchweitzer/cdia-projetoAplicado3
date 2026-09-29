# Análise de possibilidades — Microdados do ENEM 2025

> **Propósito deste documento:** material para discussão com a equipe sobre o que é (e o que não é) possível fazer com os microdados do ENEM 2025, e qual caminho adotar para o produto do projeto.
>
> Data: 23/09/2026 · Projeto: cdia-projetoAplicado3

---

## 1. Contexto e problema detectado

Os notebooks do projeto (`Colab_notebook.ipynb` e `tabela.ipynb`) tentavam cruzar os participantes filtrados por perfil (idade, sexo, raça etc.) com as notas da prova, via:

```python
df_candidato.join(df_prova, left_on='NU_INSCRICAO', right_on='NU_SEQUENCIAL', how='inner')
```

Esse join sempre retorna **0 linhas** — e a hipótese registrada nos commits ("CSVs não são ordenados igualmente", "leitura cortada") estava errada. A causa real está abaixo.

## 2. Diagnóstico: o join é impossível por design

O INEP dividiu os microdados em 3 bases desde a edição **2024** e removeu intencionalmente qualquer chave de ligação entre elas, para cumprir a **LGPD** (não vincular o questionário socioeconômico às notas de uma pessoa, já que `CO_ESCOLA` voltou à base a partir de 2024).

**Fontes oficiais:**

- **Dicionário de variáveis (aba RESULTADOS, nota 1):**
  > *"Número sequencial que identifica cada linha da base de Resultados. Variável distinta da NU_INSCRICAO disponível na base de Participantes, de modo que não é possível utilizá-la para relacionar as duas bases."*
- **Leia-Me dos Microdados ENEM 2025 (seção 3):**
  > *"Ressalta-se que os arquivos PARTICIPANTES_2025.csv e RESULTADOS_2025.csv não possuem chave de ligação em comum. Dessa forma, as informações relativas à escola de conclusão do ensino médio não possibilitam a identificação indevida dos participantes do exame, em fiel observância ao que estabelece a Lei Geral de Proteção de Dados Pessoais (LGPD)."*

**Evidências medidas nos dados locais:**

| Evidência | Resultado |
|---|---|
| Linhas em cada base | **4.810.772 em ambas** (mesma população — distribuição por UF identicamente igual — em ordens embaralhadas) |
| `NU_SEQUENCIAL` | Permutação dos inteiros **1 a 4.810.772** (máx. 7 dígitos) — é só o número da linha |
| `NU_INSCRICAO` | Máscara de **12 dígitos** (ex.: 210066506229) — o próprio INEP diz que "trata-se de uma máscara e não o seu número de inscrição original" |
| Join `NU_INSCRICAO == NU_SEQUENCIAL` | **0 casamentos é matematicamente garantido** (espaços de valores disjuntos), independente de truncamento |
| Presença dia 2 (`TP_PRESENCA_CN`) | 3.260.336 presentes · 1.548.487 ausentes · 1.949 eliminados |
| Dados no Colab | Parquets enviados estavam **truncados** (2.290.718 participantes / 526.815 resultados) — o dado local está completo |

### Bugs secundários encontrados nos notebooks (independentes do join)

1. `filtrar_candidato(df_raw, candidato)` **ignora o parâmetro `df_raw`** — dentro dela há uma releitura com `teste=True` (tabela.ipynb) que lê só 51 linhas. No Colab "funcinou por acaso" porque lá os ramos `teste=True/False` são idênticos.
2. No Colab, `dataframe_microdados` tem `if teste: / else:` com o mesmo código nos dois ramos.
3. `main.py` e `README.md` estão vazios.

---

## 3. Estrutura das 3 bases de 2025

| Base | Tamanho local | Linhas | Conteúdo |
|---|---|---|---|
| `PARTICIPANTES_2025.csv` | 513 MB | 4.810.772 | Perfil (faixa etária, sexo, cor/raça, nacionalidade, conclusão EM), treineiro, município/UF de prova, questionário Q001–Q023 |
| `RESULTADOS_2025.csv` | 2,1 GB | 4.810.772 | Escola de conclusão (`CO_ESCOLA`, dependência ADM, localização...), presença, cadernos, respostas, gabaritos, notas TRI, redação (nota total, 5 competências, **notas por avaliador AV1–AV4 — novidade 2025**) |
| `ITENS_PROVA_2025.csv` | 365 KB | ~milhares | Itens: posição, área, gabarito, habilidade, parâmetros TRI (A/B/C), itens abandonados |
| Dicionário | XLSX/ODS | — | 3 abas (uma por base); é dele que sai o `dicionario_variaveis.json` |

---

## 4. O que É possível analisar com 2025

### 🧑‍🎓 Com PARTICIPANTES (quem são os inscritos)

1. Perfil demográfico: faixa etária, sexo, cor/raça, estado civil, nacionalidade
2. Situação escolar: concluintes vs. cursando, ano de conclusão, **treineiros vs. não**
3. Geografia da participação: inscritos por UF/município de prova
4. Retrato socioeconômico: renda familiar (Q006), escolaridade/ ocupação dos pais, itens do lar (internet, computador, carro, empregados, banheiros...)
5. Cruzamentos internos: renda × cor/raça, renda × escolaridade da mãe, tipo de escola do EM (Q023) × renda...
6. **⭐ Caso do projeto:** *"quantas pessoas com um perfil como o meu fizeram o ENEM 2025?"* + composição socioeconômica desse grupo — **o filtro da classe `Candidato` já funciona aqui**

### 📝 Com RESULTADOS (como foi o desempenho)

1. Distribuição de notas geral e por área (CN/CH/LC/MT/redação): média, mediana, percentis
2. Médias por UF e município de prova (mapas, comparações regionais)
3. Abstenção: ausências por UF/município, dia 1 vs. dia 2, eliminados
4. **Pública × privada × federal**: desempenho pela escola de conclusão (`TP_DEPENDENCIA_ADM_ESC`), urbana × rural
5. Língua estrangeira: inglês vs. espanhol (quem escolhe o quê, desempenho por opção)
6. Redação: notas por competência (COMP1–5), % nota mil, zeradas/anuladas (`TP_STATUS_REDACAO`)
7. **Avaliadores de redação (2025)**: divergência AV1 × AV2, bancas de 3 avaliadores (AV3/AV4)
8. Aplicação específica da BAM (Belém/Ananindeua/Marituba — COP30), identificável via `CO_PROVA`
9. Agregação por escola (`CO_ESCOLA`) — ⚠️ INEP não recomenda rankings; escolas com <10 participantes têm código mascarado
10. Padrões de resposta: brancos, duplas marcações, distratores

### ❓ Com ITENS_PROVA (as questões)

1. Parâmetros TRI por item: dificuldade (B), discriminação (A), acerto casual (C)
2. Itens abandonados pelo INEP e motivos
3. Mapa de habilidades por área/posição

### 🔗 Único join que funciona: RESULTADOS ↔ ITENS_PROVA (por `CO_PROVA`)

1. **% de acerto por questão e por habilidade** (resposta × gabarito)
2. Validação do TRI: dificuldade real vs. `NU_PARAM_B`
3. Análise de distratores (quais alternativas erradas atraem mais)
4. Comparação entre cadernos da mesma área (azul/amarelo/verde/branco/Libras...)

### 🌉 Cruzamentos PARTICIPANTES ↔ RESULTADOS (só agregados, sem link individual)

As bases compartilham **UF e município de prova** — permite análises **ecológicas** (por região, nunca por pessoa), com ressalva de falácia ecológica:

- renda média dos inscritos × nota média da região
- perfil demográfico × desempenho por UF

---

## 5. O que NÃO é possível com 2025

- ❌ Notas de um grupo demográfico específico (ex.: "notas de mulheres, brancas, cursando o 3º ano")
- ❌ Correlação perfil individual ↔ desempenho individual
- ❌ Acompanhar o mesmo participante entre anos (a máscara muda a cada edição)
- ❌ **⭐ O objetivo original do produto: "mostrar as notas de pessoas parecidas com o usuário"**

---

## 6. Impacto no produto do projeto

O site planejado tem duas telas implícitas:

| Funcionalidade | Possível com 2025? |
|---|---|
| "Quantas pessoas com seu perfil fizeram o ENEM?" | ✅ Sim (PARTICIPANTES) |
| "Qual a composição socioeconômica desse grupo?" | ✅ Sim (PARTICIPANTES, Q001–Q023) |
| "Quais notas as pessoas como você tiraram?" | ❌ **Não** (LGPD wall) |

---

## 7. Alternativas em discussão

### Opção A — Usar microdados de 2023 (último ano consolidado) ✅ *viável*

- 2023 é o último ano com **arquivo único** (`MICRODADOS_ENEM_2023.csv`): perfil e notas na mesma linha, ligados por `NU_INSCRICAO`.
- O projeto inteiro funciona sem mudança conceitual: filtra por perfil → lê as notas do próprio registro.
- `extrator_microdados.py` já é parametrizado por ano; o `organizar_dados()` já move a pasta `DADOS` genericamente.
- **Custo:** download ~1 GB (zip) / ~3–4 GB extraídos; adaptar `criar_dicionario()` ao dicionário de 2023 (nome de aba/layout levemente diferente); estratégia Parquet para não estourar RAM.
- **Ressalva metodológica:** as comparações usam 2023 (aplicação diferente, contexto pré-COP30 etc.).

### Opção B — Só 2025, estatísticas agregadas ✅ *sem download*

- Mantém tudo em 2025; relaxa o requisito de notas comparativas.
- Produto mostra **perfil e contagem** dos candidatos parecidos + distribuição geral de notas (por UF, tipo de escola, etc.) — sem vínculo entre os dois.
- **Risco:** perde a funcionalidade central do produto ("notas de pessoas como você").

### Opção C — Híbrido: 2025 (perfil) + 2023 (notas) ⚠️ *mais complexo*

- "X pessoas como você fizeram o ENEM 2025" + "no ENEM 2023, pessoas assim tiraram em média Y".
- Duas bases, dois pipelines, explicação ao usuário sobre anos distintos.

---

## 8. Questões para a equipe decidir

1. O requisito **"ver notas de candidatos parecidos" é negociável**? (define se a Opção A é obrigatória)
2. Há restrições do curso sobre usar **2025 especificamente**?
3. Se usarmos 2023: acomodamos **espaço em disco** extra (~3–4 GB) no pipeline local e no Colab?
4. O produto aceita mostrar **dados agregados/ecológicos** como "perfil vs. média regional"?
5. Lista acima (seção 4): **quais análises são prioridade** para o produto final?

---

## Referências

- Leia-Me · `dump/microdados_enem_2025/LEIA-ME E DOCUMENTOS TÉCNICOS/Leia_Me_Enem_2025.pdf` (seção 3)
- Dicionário de variáveis · `dump/microdados_enem_2025/DICIONÁRIO/Dicionário_Microdados_Enem_2025.xlsx` (nota 1 da aba RESULTADOS_2025; nota 1 de NU_INSCRICAO na aba PARTICIPANTES_2025)
- Dados analisados · `dados/dados_2025/{PARTICIPANTES,RESULTADOS,ITENS_PROVA}_2025.csv`
