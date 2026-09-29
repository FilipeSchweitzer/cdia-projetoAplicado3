"""Centro do fluxo: recebe os dados do app, decodifica, chama o tratador e devolve o resultado.

    app.py  ->  main.py  ->  extrator_microdados.py (leitura)  +  tabela.py (tratamento)  ->  main.py  ->  app.py
"""

import unicodedata
from functools import cache

import polars as pl

import extrator_microdados as extrator
import tabela

# nome mostrado no app -> coluna de nota nos microdados
AREAS_NOTA = {nome: coluna for coluna, nome in tabela.NOMES_AREAS.items()}

# variáveis do perfil do candidato que viram dropdowns no formulário (valores vêm do dicionário)
VARIAVEIS_PERFIL = ['TP_SEXO', 'TP_COR_RACA', 'TP_NACIONALIDADE', 'TP_ST_CONCLUSAO', 'TP_ANO_CONCLUIU']

COLUNAS_MICRODADOS = [
    *tabela.COLUNAS_NOTA,
    'CO_ESCOLA', 'CO_MUNICIPIO_ESC', 'CO_MUNICIPIO_PROVA',
    'TP_FAIXA_ETARIA', 'TP_SEXO', 'TP_COR_RACA', 'TP_NACIONALIDADE',
    'TP_ST_CONCLUSAO', 'TP_ANO_CONCLUIU', 'IN_TREINEIRO',
]


class DadosIndisponiveis(Exception):
    pass


# ---------------------------------------------------------------- carregamento (uma vez por processo)

@cache
def ano_atual() -> int:
    anos = extrator.anos_disponiveis()
    if not anos:
        raise DadosIndisponiveis(
            f'Nenhum ano com microdados + INSE foi extraído. Rode "python extrator_microdados.py" '
            f'(anos possíveis: {", ".join(map(str, extrator.ANOS_INSE))}).'
        )
    return max(anos)


@cache
def _dicionario() -> dict:
    return extrator.ler_dicionario(ano_atual())


@cache
def _inse() -> tuple[pl.DataFrame, pl.DataFrame]:
    df_escolas, df_municipios = extrator.ler_inse(ano_atual())
    df_escolas = tabela.tratar_inse_escolas(df_escolas)
    limites = tabela.limites_niveis(df_escolas)
    return df_escolas, tabela.tratar_inse_municipios(df_municipios, limites)


@cache
def _df_nivel() -> pl.DataFrame:
    df_escolas, df_municipios = _inse()
    df_microdados = extrator.ler_microdados(ano_atual(), COLUNAS_MICRODADOS)
    return tabela.resultados_nivel(df_microdados, df_escolas, df_municipios)


@cache
def _municipios_normalizados() -> pl.DataFrame:
    """Municípios com nome, UF e código normalizados (sem acento), para a busca do formulário."""
    df = tabela.municipios(_inse()[1])
    return df.with_columns(
        pl.col('NO_MUNICIPIO').map_elements(_normalizar, return_dtype=pl.String).alias('NORM_NOME'),
        pl.col('NO_UF').map_elements(_normalizar, return_dtype=pl.String).alias('NORM_UF'),
        pl.col('CO_MUNICIPIO').cast(pl.String).alias('CODIGO'),
    )


@cache
def _rotulos_municipios() -> tuple[list[str], dict[str, int]]:
    """Rótulos 'Nome (UF) — código IBGE' de todos os municípios com INSE, para o selectbox do formulário."""
    df = _municipios_normalizados()
    rotulos = [_rotulo_municipio(nome, uf, codigo) for codigo, nome, _, uf, *_ in df.iter_rows()]
    return rotulos, dict(zip(rotulos, df['CO_MUNICIPIO'].to_list()))


# ---------------------------------------------------------------- decodificação (texto do app -> código)

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


def decodificar_uf(nome_uf: str) -> int:
    _, df_municipios = _inse()
    df_ufs = tabela.ufs(df_municipios)
    linha = df_ufs.filter(pl.col('NO_UF').map_elements(_normalizar, return_dtype=pl.String) == _normalizar(nome_uf))
    if linha.height == 0:
        raise ValueError(f"UF '{nome_uf}' não encontrada.")
    return int(linha['CO_UF'][0])


def decodificar_municipio(rotulo: str) -> int:
    """Converte o rótulo 'Nome (UF) — código' escolhido no app no código IBGE do município."""
    _, mapa = _rotulos_municipios()
    if rotulo not in mapa:
        raise ValueError(f"Município '{rotulo}' não encontrado.")
    return int(mapa[rotulo])


def _rotulo_municipio(nome: str, uf: str, codigo: int) -> str:
    return f'{nome} ({uf}) — {codigo}'


def calcular_faixa_etaria(idade: int) -> int:
    """Converte a idade em anos no código de TP_FAIXA_ETARIA."""
    if idade < 17:
        return 1
    if idade <= 25:
        # 17 -> 2, 18 -> 3, ..., 25 -> 10
        return idade - 15
    if idade > 70:
        return 20
    # a partir de 26 as faixas têm 5 anos: 26-30 -> 11, 31-35 -> 12, ..., 66-70 -> 19
    return 11 + (idade - 26) // 5


def decodificar_candidato(entrada: dict) -> tabela.Candidato:
    return tabela.Candidato(
        faixa_etaria=calcular_faixa_etaria(entrada['idade']),
        sexo=decodificar('TP_SEXO', entrada['sexo']),
        cor_raca=int(decodificar('TP_COR_RACA', entrada['cor_raca'])),
        nacionalidade=int(decodificar('TP_NACIONALIDADE', entrada['nacionalidade'])),
        st_conclusao=int(decodificar('TP_ST_CONCLUSAO', entrada['st_conclusao'])),
        ano_concluiu=int(decodificar('TP_ANO_CONCLUIU', entrada['ano_concluiu'])),
        treineiro=1 if entrada['treineiro'] else 0,
    )


# ---------------------------------------------------------------- interface com o app

def autenticar(usuario: str, senha: str) -> bool:
    # TODO: validar usuário e senha de verdade
    return bool(usuario) and bool(senha)


def opcoes_formulario() -> dict:
    """Valores fixos que o app mostra como dropdown."""
    _, df_municipios = _inse()
    dicionario = _dicionario()
    return {
        'ano': ano_atual(),
        'areas': list(AREAS_NOTA),
        'ufs': tabela.ufs(df_municipios)['NO_UF'].to_list(),
        **{variavel: list(dicionario[variavel].values()) for variavel in VARIAVEIS_PERFIL},
    }


def opcoes_municipios(uf: str | None = None) -> list[str]:
    """Rótulos 'Nome (UF) — código IBGE' dos municípios para o selectbox do formulário.

    Com uma UF escolhida, só os municípios dela; sem UF, todos os 5,5 mil com INSE.
    """
    if not uf:
        return _rotulos_municipios()[0]

    df = _municipios_normalizados().filter(pl.col('NORM_UF') == _normalizar(uf))
    return [_rotulo_municipio(nome, uf_nome, codigo) for codigo, nome, _, uf_nome, *_ in df.iter_rows()]


def analisar(entrada: dict) -> dict:
    """Recebe o formulário do app (textos e números) e devolve tudo que o dashboard precisa.

    entrada: area, nota, uf, municipio (rótulo 'Nome (UF) — código' do selectbox),
             co_escola (ou None), idade, sexo, cor_raca, nacionalidade, st_conclusao,
             ano_concluiu, treineiro
    """
    coluna_nota = AREAS_NOTA[entrada['area']]
    co_uf = decodificar_uf(entrada['uf'])
    co_municipio = decodificar_municipio(entrada['municipio'])
    candidato = decodificar_candidato(entrada)

    df_escolas, df_municipios = _inse()
    df_nivel = _df_nivel()
    nivel, fonte_nivel = tabela.nivel_usuario(df_escolas, df_municipios, co_municipio, entrada['co_escola'])

    return {
        'ano': ano_atual(),
        'fonte_nivel': fonte_nivel,
        'posicao': tabela.estimar_posicao_candidato(df_nivel, coluna_nota, entrada['nota'], nivel),
        'percentis': tabela.calcular_percentis(df_nivel, coluna_nota, entrada['nota'], nivel, co_uf),
        'media_por_nivel': tabela.calcular_media_por_nivel(df_nivel),
        'perfil': tabela.resumir_perfil(tabela.filtrar_candidato(df_nivel, candidato), coluna_nota),
        'uf': entrada['uf'],
        'area': entrada['area'],
        'medias_uf': tabela.medias_por_uf(df_nivel, df_municipios),
        'medias_municipio': tabela.medias_por_municipio(df_nivel, df_municipios, co_uf),
        'distribuicao': {
            'Brasil': tabela.distribuicao_notas(df_nivel),
            'Sua UF': tabela.distribuicao_notas(df_nivel.filter(pl.col('CO_UF_REF') == co_uf)),
        },
    }
