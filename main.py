import polars as pl

def datraframe_microdados(ano:int, tipo_dado:str, teste:bool = False) -> pl.DataFrame:
    CAMINHO_CSV = f'dados_censos/microdados_enem_{ano}/DADOS/{tipo_dado}_{ano}.csv'

    if teste:
        df = pl.read_csv(CAMINHO_CSV, separator=";", encoding="latin1", n_rows=50)
    else:
        df = pl.read_csv(CAMINHO_CSV, separator=";", encoding="latin1")

    return df