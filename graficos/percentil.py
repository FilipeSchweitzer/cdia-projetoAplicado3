"""Gráfico 1: percentil do candidato em três escalas (grupo INSE, UF e Brasil).

Só desenha; o cálculo vem pronto de tabela.calcular_percentis (via main.analisar).
"""

import altair as alt
import polars as pl


def grafico_percentis(df_percentis: pl.DataFrame) -> alt.LayerChart:
    base = alt.Chart(df_percentis.filter(pl.col('PERCENTIL').is_not_null())).encode(
        y=alt.Y('ESCALA:N', title=None, sort=list(df_percentis['ESCALA'])),
        x=alt.X('PERCENTIL:Q', title='Percentil (% de candidatos com nota menor)',
                scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 25, 50, 75, 100])),
        tooltip=[
            alt.Tooltip('ESCALA:N', title='Escala'),
            alt.Tooltip('PERCENTIL:Q', title='Percentil', format='.1f'),
            alt.Tooltip('CANDIDATOS:Q', title='Candidatos', format=',d'),
        ],
    )

    barras = base.mark_bar(size=22, cornerRadiusEnd=4)
    rotulos = base.mark_text(align='left', dx=6).encode(
        text=alt.Text('PERCENTIL:Q', format='.0f'),
    )
    # referência: percentil 50 = mediana
    mediana = alt.Chart(pl.DataFrame({'x': [50]})).mark_rule(strokeDash=[4, 4], opacity=0.5).encode(x='x:Q')

    return (barras + rotulos + mediana).properties(height=180)


def frase_percentil(df_percentis: pl.DataFrame) -> str:
    valores = dict(zip(df_percentis['ESCALA'], df_percentis['PERCENTIL']))
    grupo = valores['Seu grupo INSE']
    brasil = valores['Brasil']

    if grupo is None:
        frase = 'Não há candidatos suficientes no seu grupo INSE para calcular o percentil.'
    else:
        frase = f'Sua nota supera {grupo:.0f}% dos candidatos com perfil socioeconômico parecido'
        if brasil is not None:
            frase += f' e {brasil:.0f}% dos candidatos do Brasil'
        frase += '.'

    # avisa quais escalas ficaram de fora do gráfico em vez de sumir com elas em silêncio
    sem_dados = df_percentis.filter(pl.col('PERCENTIL').is_null())
    for escala, candidatos in zip(sem_dados['ESCALA'], sem_dados['CANDIDATOS']):
        frase += f' {escala}: dados insuficientes ({candidatos} candidatos).'
    return frase
