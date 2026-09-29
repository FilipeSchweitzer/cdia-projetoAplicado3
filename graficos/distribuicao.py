"""Gráfico 3: distribuição de notas por área — média, mediana e faixa P25–P75.

Só desenha; o cálculo vem pronto de tabela.distribuicao_notas (via main.analisar).
"""

import altair as alt
import polars as pl


def grafico_distribuicao(df_dist: pl.DataFrame, nota_usuario: float | None, area_usuario: str) -> alt.LayerChart:
    base = alt.Chart(df_dist).encode(
        x=alt.X('AREA:N', title=None, sort=list(df_dist['AREA'])),
    )

    # caixa: metade central dos candidatos (P25 a P75)
    caixa = base.mark_bar(size=40, opacity=0.35, color='#4c78a8').encode(
        y=alt.Y('P25:Q', title='Nota', scale=alt.Scale(zero=False)),
        y2=alt.Y2('P75:Q'),
        tooltip=[
            alt.Tooltip('AREA:N', title='Área'),
            alt.Tooltip('MEDIA:Q', title='Média', format='.1f'),
            alt.Tooltip('MEDIANA:Q', title='Mediana', format='.1f'),
            alt.Tooltip('P10:Q', title='P10', format='.0f'),
            alt.Tooltip('P25:Q', title='P25', format='.0f'),
            alt.Tooltip('P75:Q', title='P75', format='.0f'),
            alt.Tooltip('P90:Q', title='P90', format='.0f'),
            alt.Tooltip('CANDIDATOS:Q', title='Candidatos', format=',d'),
        ],
    )

    # haste: 80% central dos candidatos (P10 a P90)
    haste = base.mark_rule(color='#4c78a8', opacity=0.7).encode(
        y='P10:Q',
        y2='P90:Q',
    )
    mediana = base.mark_tick(color='#00355e', thickness=2, size=28).encode(y='MEDIANA:Q')
    media = base.mark_point(shape='diamond', color='#e45756', size=60).encode(y='MEDIA:Q')

    grafico = caixa + haste + mediana + media

    # marca a nota do usuário na área que ele escolheu no formulário
    if nota_usuario is not None:
        linhas = df_dist.filter(pl.col('AREA') == area_usuario)
        if not linhas.is_empty():
            marco = alt.Chart(pl.DataFrame({'NOTA': [nota_usuario], 'AREA': [area_usuario]})).mark_point(
                shape='triangle-down', color='#e45756', size=120, filled=True,
            ).encode(x=alt.X('AREA:N'), y=alt.Y('NOTA:Q'))
            grafico = grafico + marco

    return grafico.properties(height=380)


def frase_distribuicao(df_dist: pl.DataFrame, area_usuario: str, escopo: str) -> str:
    onde = 'no Brasil' if escopo == 'Brasil' else 'na sua UF'
    linha = df_dist.filter(pl.col('AREA') == area_usuario)
    if linha.is_empty():
        return f'Não há candidatos suficientes {onde} para {area_usuario}.'
    return (
        f'{onde[0].upper()}{onde[1:]}, {area_usuario} teve média de {linha["MEDIA"][0]:.1f} e mediana de '
        f'{linha["MEDIANA"][0]:.1f} pontos; a metade central dos candidatos ficou entre '
        f'{linha["P25"][0]:.0f} e {linha["P75"][0]:.0f} pontos.'
    )
