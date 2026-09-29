"""Gráfico 2: médias por UF e por município da UF do usuário (comparações regionais).

Só desenha; o cálculo vem pronto de tabela.medias_por_uf / medias_por_municipio (via main.analisar).
"""

import altair as alt
import polars as pl


def _grafico_barras(df: pl.DataFrame, coluna_grupo: str, grupo_destaque: str | None) -> alt.Chart:
    dados = df.sort('MEDIA', descending=True)
    base = alt.Chart(dados).encode(
        y=alt.Y(f'{coluna_grupo}:N', title=None, sort=list(dados[coluna_grupo])),
        x=alt.X('MEDIA:Q', title='Média'),
        tooltip=[
            alt.Tooltip(f'{coluna_grupo}:N'),
            alt.Tooltip('MEDIA:Q', title='Média', format='.1f'),
            alt.Tooltip('CANDIDATOS:Q', title='Candidatos', format=',d'),
        ],
        color=alt.condition(
            alt.datum[coluna_grupo] == (grupo_destaque or ''),
            alt.value('#e45756'),
            alt.value('#4c78a8'),
        ),
    )
    return base.mark_bar(cornerRadiusEnd=4, size=16)


def grafico_medias_uf(df_medias_uf: pl.DataFrame, area: str, uf_usuario: str) -> alt.Chart:
    return _grafico_barras(
        df_medias_uf.filter(pl.col('AREA') == area), 'NO_UF', uf_usuario,
    ).properties(height=480)


def grafico_medias_municipio(df_medias_municipio: pl.DataFrame, area: str, uf_usuario: str) -> alt.Chart:
    if df_medias_municipio.filter(pl.col('AREA') == area).is_empty():
        return None
    return _grafico_barras(
        df_medias_municipio.filter(pl.col('AREA') == area), 'MUNICIPIO', None,
    ).properties(height=max(180, 26 * len(df_medias_municipio['MUNICIPIO'].unique())))


def frase_regional(df_medias_uf: pl.DataFrame, area: str, uf_usuario: str) -> str:
    dados = df_medias_uf.filter(pl.col('AREA') == area)
    linha = dados.filter(pl.col('NO_UF') == uf_usuario)
    if linha.is_empty():
        return f'A média nacional em {area} é {dados["MEDIA"].mean():.1f} pontos.'
    media_uf = linha['MEDIA'][0]
    media_brasil = dados['MEDIA'].mean()
    posicao = dados.sort('MEDIA', descending=True)['NO_UF'].to_list().index(uf_usuario) + 1
    return (
        f'A média em {area} em {uf_usuario} é {media_uf:.1f} pontos '
        f'({"acima" if media_uf >= media_brasil else "abaixo"} da média nacional, {media_brasil:.1f}), '
        f'a {posicao}ª posição entre as UFs.'
    )
