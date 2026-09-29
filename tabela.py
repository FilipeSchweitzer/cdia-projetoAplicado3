"""Tratamento dos dados: cruza microdados do Enem com o INSE e calcula as análises do candidato.

Todas as funções recebem DataFrames já lidos (pelo extrator_microdados.py) e dados do usuário
já decodificados em códigos (pelo main.py).
"""

from dataclasses import dataclass

import polars as pl

COLUNAS_NOTA = ['NU_NOTA_CN', 'NU_NOTA_CH', 'NU_NOTA_LC', 'NU_NOTA_MT', 'NU_NOTA_REDACAO']

NOMES_AREAS = {
    'NU_NOTA_CN': 'Ciências da Natureza',
    'NU_NOTA_CH': 'Ciências Humanas',
    'NU_NOTA_LC': 'Linguagens e Códigos',
    'NU_NOTA_MT': 'Matemática',
    'NU_NOTA_REDACAO': 'Redação',
}

# abaixo disso o percentil/média fica instável e não é calculado
MIN_CANDIDATOS = 30

# linha da planilha de municípios que representa o total (todas as redes, urbana + rural)
REDE_TOTAL = 6
LOCALIZACAO_TOTAL = 0

# nomes das colunas do INSE 2019, que mudaram a partir de 2021
RENOMEAR_INSE_2019 = {
    'CO_ESCOLA': 'ID_ESCOLA',
    'NOME_ESCOLA': 'NO_ESCOLA',
    'NOME_UF': 'NO_UF',
    'NOME_MUNICIPIO': 'NO_MUNICIPIO',
    'INSE_VALOR_ABSOLUTO': 'MEDIA_INSE',
}


@dataclass
class Candidato:
    """Perfil do candidato já em códigos dos microdados (decodificado pelo main.py)."""
    faixa_etaria: int
    sexo: str
    cor_raca: int
    nacionalidade: int
    st_conclusao: int
    ano_concluiu: int
    treineiro: int


# ---------------------------------------------------------------- INSE

def tratar_inse_escolas(df_inse_escolas: pl.DataFrame) -> pl.DataFrame:
    df = df_inse_escolas.rename(RENOMEAR_INSE_2019, strict=False)
    return df.select('ID_ESCOLA', 'CO_MUNICIPIO', 'CO_UF', 'NO_UF', 'MEDIA_INSE', 'INSE_CLASSIFICACAO')


def limites_niveis(df_inse_escolas: pl.DataFrame) -> pl.DataFrame:
    """Menor MEDIA_INSE de cada nível, tirada da própria classificação das escolas do ano."""
    return (
        df_inse_escolas
        .group_by('INSE_CLASSIFICACAO')
        .agg(pl.col('MEDIA_INSE').min().alias('MINIMO'))
        .sort('MINIMO')
    )


def classificar_inse(coluna: str, limites: pl.DataFrame) -> pl.Expr:
    # a planilha de municípios só tem a média, então usamos as mesmas faixas das escolas
    return pl.col(coluna).cut(
        breaks=limites['MINIMO'].to_list()[1:],
        labels=limites['INSE_CLASSIFICACAO'].to_list(),
        left_closed=True,
    ).cast(pl.String)


def tratar_inse_municipios(df_inse_municipios: pl.DataFrame, limites: pl.DataFrame) -> pl.DataFrame:
    df = df_inse_municipios.rename(RENOMEAR_INSE_2019, strict=False)
    return (
        df.filter(
            (pl.col('TP_TIPO_REDE') == REDE_TOTAL)
            & (pl.col('TP_LOCALIZACAO') == LOCALIZACAO_TOTAL)
            & pl.col('MEDIA_INSE').is_not_null()
        )
        .select('CO_MUNICIPIO', 'CO_UF', 'NO_UF', 'NO_MUNICIPIO', 'MEDIA_INSE')
        .with_columns(classificar_inse('MEDIA_INSE', limites).alias('NIVEL_DO_MUNICIPIO'))
    )


def ufs(df_inse_municipios: pl.DataFrame) -> pl.DataFrame:
    """Tabela CO_UF / NO_UF (o dicionário do Enem não traz os nomes das UFs)."""
    return df_inse_municipios.select('CO_UF', 'NO_UF').unique().sort('NO_UF')


# ---------------------------------------------------------------- microdados + INSE

def resultados_nivel(
    df_microdados: pl.DataFrame,
    df_inse_escolas: pl.DataFrame,
    df_inse_municipios: pl.DataFrame,
) -> pl.DataFrame:
    """Adiciona NIVEL_ESTIMADO (INSE) e CO_UF_REF a cada candidato."""
    # só interessa quem fez ao menos uma prova
    df = df_microdados.filter(pl.any_horizontal(pl.col(COLUNAS_NOTA).is_not_null()))

    # município da escola quando o candidato informou; senão o município onde fez a prova
    df = df.with_columns(
        pl.coalesce('CO_MUNICIPIO_ESC', 'CO_MUNICIPIO_PROVA').alias('CO_MUNICIPIO_REF'),
    ).with_columns(
        (pl.col('CO_MUNICIPIO_REF') // 100_000).alias('CO_UF_REF'),
    )

    df = df.join(
        df_inse_municipios.select('CO_MUNICIPIO', 'NIVEL_DO_MUNICIPIO'),
        left_on='CO_MUNICIPIO_REF',
        right_on='CO_MUNICIPIO',
        how='left',
    )

    # os microdados só trazem o código da escola até 2019; a partir daí fica só o município
    if 'CO_ESCOLA' in df.columns:
        df = df.join(
            df_inse_escolas.select('ID_ESCOLA', pl.col('INSE_CLASSIFICACAO').alias('NIVEL_DA_ESCOLA')),
            left_on='CO_ESCOLA',
            right_on='ID_ESCOLA',
            how='left',
        )
        nivel = pl.coalesce('NIVEL_DA_ESCOLA', 'NIVEL_DO_MUNICIPIO')
    else:
        nivel = pl.col('NIVEL_DO_MUNICIPIO')

    return df.with_columns(nivel.alias('NIVEL_ESTIMADO'))


def nivel_usuario(
    df_inse_escolas: pl.DataFrame,
    df_inse_municipios: pl.DataFrame,
    co_municipio: int,
    co_escola: int | None = None,
) -> tuple[str, str]:
    """Nível INSE do usuário: pela escola se ela estiver no INSE, senão pelo município."""
    if co_escola is not None:
        linha_escola = df_inse_escolas.filter(pl.col('ID_ESCOLA') == co_escola)
        if linha_escola.height > 0:
            return linha_escola['INSE_CLASSIFICACAO'][0], 'escola'

    linha_municipio = df_inse_municipios.filter(pl.col('CO_MUNICIPIO') == co_municipio)
    if linha_municipio.height == 0:
        raise ValueError(f'Município {co_municipio} não encontrado no INSE.')
    return linha_municipio['NIVEL_DO_MUNICIPIO'][0], 'município'


# ---------------------------------------------------------------- análises

def estimar_posicao_candidato(df_nivel: pl.DataFrame, coluna_nota: str, nota_usuario: float, nivel: str) -> dict:
    grupo = df_nivel.filter((pl.col('NIVEL_ESTIMADO') == nivel) & pl.col(coluna_nota).is_not_null())
    if grupo.height < MIN_CANDIDATOS:
        raise ValueError(f'Há apenas {grupo.height} candidatos no {nivel}, poucos para comparar.')

    media_grupo = grupo[coluna_nota].mean()
    percentil = (grupo[coluna_nota] < nota_usuario).mean() * 100

    return {
        'nivel_inse': nivel,
        'tamanho_grupo': grupo.height,
        'media_grupo': round(media_grupo, 1),
        'nota_usuario': nota_usuario,
        'diferenca_absoluta': round(nota_usuario - media_grupo, 1),
        'percentil_usuario': round(percentil, 1),
    }


def calcular_percentis(
    df_nivel: pl.DataFrame,
    coluna_nota: str,
    nota_usuario: float,
    nivel: str,
    co_uf: int,
) -> pl.DataFrame:
    """Percentil do usuário no grupo INSE, na UF e no Brasil (Gráfico 1)."""
    df_notas = df_nivel.filter(pl.col(coluna_nota).is_not_null())
    escalas = {
        'Seu grupo INSE': df_notas.filter(pl.col('NIVEL_ESTIMADO') == nivel),
        'Sua UF': df_notas.filter(pl.col('CO_UF_REF') == co_uf),
        'Brasil': df_notas,
    }

    linhas = []
    for escala, grupo in escalas.items():
        percentil = None
        if grupo.height >= MIN_CANDIDATOS:
            percentil = round((grupo[coluna_nota] < nota_usuario).mean() * 100, 1)
        linhas.append({'ESCALA': escala, 'PERCENTIL': percentil, 'CANDIDATOS': grupo.height})

    return pl.DataFrame(linhas, schema={'ESCALA': pl.String, 'PERCENTIL': pl.Float64, 'CANDIDATOS': pl.Int64})


def calcular_media_por_nivel(df_nivel: pl.DataFrame) -> pl.DataFrame:
    return (
        df_nivel
        .filter(pl.col('NIVEL_ESTIMADO').is_not_null())
        .group_by('NIVEL_ESTIMADO')
        .agg(
            *[pl.col(coluna).mean().round(1).alias(coluna.replace('NU_NOTA', 'MEDIA')) for coluna in COLUNAS_NOTA],
            pl.len().alias('QUANTIDADE_DE_CANDIDATOS'),
        )
        .sort('NIVEL_ESTIMADO')
    )


def medias_por_uf(df_nivel: pl.DataFrame, df_inse_municipios: pl.DataFrame) -> pl.DataFrame:
    """Média de cada área por UF de residência de prova (formato longo: NO_UF, AREA, MEDIA)."""
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
    ).with_columns(
        pl.col('COLUNA').replace_strict(NOMES_AREAS).alias('AREA'),
    ).drop('COLUNA')


def medias_por_municipio(
    df_nivel: pl.DataFrame,
    df_inse_municipios: pl.DataFrame,
    co_uf: int,
    top: int = 15,
) -> pl.DataFrame:
    """Média de cada área nos municípios com mais candidatos dentro de uma UF (formato longo)."""
    df = (
        df_nivel
        .filter(pl.col('CO_UF_REF') == co_uf)
        .group_by('CO_MUNICIPIO_REF')
        .agg(
            pl.len().alias('CANDIDATOS'),
            *[pl.col(coluna).mean().round(1).alias(coluna) for coluna in COLUNAS_NOTA],
        )
        .filter(pl.col('CANDIDATOS') >= MIN_CANDIDATOS)
        .join(
            df_inse_municipios.select('CO_MUNICIPIO', 'NO_MUNICIPIO'),
            left_on='CO_MUNICIPIO_REF', right_on='CO_MUNICIPIO', how='left',
        )
        .with_columns(
            pl.coalesce('NO_MUNICIPIO', pl.col('CO_MUNICIPIO_REF').cast(pl.String)).alias('MUNICIPIO'),
        )
        .sort('CANDIDATOS', descending=True)
        .head(top)
    )
    return df.unpivot(
        COLUNAS_NOTA, index=['MUNICIPIO', 'CANDIDATOS'],
        variable_name='COLUNA', value_name='MEDIA',
    ).with_columns(
        pl.col('COLUNA').replace_strict(NOMES_AREAS).alias('AREA'),
    ).drop('COLUNA')


def distribuicao_notas(df_nivel: pl.DataFrame) -> pl.DataFrame:
    """Média, mediana e percentis de cada área entre candidatos com nota naquela área."""
    linhas = []
    for coluna, area in NOMES_AREAS.items():
        notas = df_nivel[coluna].drop_nulls()
        if notas.len() < MIN_CANDIDATOS:
            continue
        linhas.append({
            'AREA': area,
            'CANDIDATOS': notas.len(),
            'MEDIA': round(notas.mean(), 1),
            'MEDIANA': round(notas.median(), 1),
            **{f'P{p}': round(notas.quantile(p / 100), 1) for p in (10, 25, 75, 90)},
        })
    return pl.DataFrame(linhas)


def resumir_perfil(df_perfil: pl.DataFrame, coluna_nota: str) -> dict:
    """Contagem, média e quantis da nota entre candidatos com o mesmo perfil do usuário."""
    notas = df_perfil[coluna_nota].drop_nulls()
    if notas.len() < MIN_CANDIDATOS:
        return {'candidatos': notas.len(), 'media': None, 'quantis': {}}

    return {
        'candidatos': notas.len(),
        'media': round(notas.mean(), 1),
        'quantis': {quantil: round(notas.quantile(quantil / 100), 1) for quantil in (10, 25, 50, 75, 90)},
    }


def filtrar_candidato(df: pl.DataFrame, candidato: Candidato) -> pl.DataFrame:
    """Candidatos com exatamente o mesmo perfil do usuário."""
    return df.filter(
        (pl.col('TP_FAIXA_ETARIA') == candidato.faixa_etaria)
        & (pl.col('TP_SEXO') == candidato.sexo)
        & (pl.col('TP_COR_RACA') == candidato.cor_raca)
        & (pl.col('TP_NACIONALIDADE') == candidato.nacionalidade)
        & (pl.col('TP_ST_CONCLUSAO') == candidato.st_conclusao)
        & (pl.col('TP_ANO_CONCLUIU') == candidato.ano_concluiu)
        & (pl.col('IN_TREINEIRO') == candidato.treineiro)
    )
