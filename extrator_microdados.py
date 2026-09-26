import json
import re
import shutil
import ssl
import subprocess
import sys
from pathlib import Path
import time
import certifi
import requests
import polars as pl

from config import ZIP_DIR, DUMP_DIR, DADOS_DIR

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

CA_BUNDLE = Path("inep_ca_bundle.pem")

# o INSE só é publicado nos anos de Saeb; só esses anos do Enem têm como ser cruzados com ele
URL_INSE = 'https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/{ano}/nivel_socioeconomico/{arquivo}'
ARQUIVOS_INSE = {
    2019: {'escolas': 'INSE_2019_ESCOLAS.xlsx', 'municipios': 'INSE_2019_MUNICIPIOS.xlsx'},
    2021: {'escolas': 'INSE_2021_escolas.xlsx', 'municipios': 'INSE_2021_municipios.xlsx'},
    2023: {'escolas': 'INSE_2023_escolas.xlsx', 'municipios': 'INSE_2023_municipios.xlsx'},
}
ANOS_INSE = tuple(ARQUIVOS_INSE)


def validar_ano(ano: int):
    if ano not in ANOS_INSE:
        raise ValueError(f'Ano {ano} não tem INSE publicado. Anos válidos: {ANOS_INSE}')


def pasta_ano(ano: int) -> Path:
    return Path(DADOS_DIR) / f'dados_{ano}'


def caminho_microdados(ano: int) -> Path:
    return pasta_ano(ano) / f'MICRODADOS_ENEM_{ano}.parquet'


def caminho_inse(ano: int, tipo: str) -> Path:
    return pasta_ano(ano) / f'INSE_{tipo.upper()}_{ano}.parquet'


def caminho_dicionario(ano: int) -> Path:
    return pasta_ano(ano) / f'DICIONARIO_{ano}.json'


# ---------------------------------------------------------------- download

def pegar_com_retry(url, headers, ca_bundle, offset=0, tentativas=5):
    for i in range(tentativas):
        try:
            req_headers = {**headers, "Range": f"bytes={offset}-"} if offset else headers
            resposta = requests.get(url, stream=True, timeout=30, verify=str(ca_bundle), headers=req_headers)
            resposta.raise_for_status()
            return resposta
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            espera = 2 ** i  # backoff exponencial: 1, 2, 4, 8, 16s
            print(f"Tentativa {i+1} falhou ({e}). Esperando {espera}s...")
            time.sleep(espera)
    raise RuntimeError("Não foi possível baixar o arquivo após várias tentativas.")

def baixar_com_resume(url, headers, ca_bundle, destino, tentativas_streaming=5):
    for tentativa in range(tentativas_streaming):
        offset = destino.stat().st_size if destino.exists() else 0
        resposta = pegar_com_retry(url, headers, ca_bundle, offset=offset)

        content_range = resposta.headers.get("content-range")
        if content_range and "/" in content_range:
            tamanho_total = int(content_range.rsplit("/", 1)[-1])
        else:
            tamanho_total = offset + int(resposta.headers.get("content-length", 0))
            if offset and resposta.status_code != 206:
                # servidor não suporta resume: recomeça do zero
                offset = 0

        modo = "ab" if offset else "wb"
        try:
            with open(destino, modo) as f:
                for chunk in resposta.iter_content(chunk_size=8192):
                    f.write(chunk)
                    print(f"Baixando: {f.tell() / 1024 / 1024:.2f} / {tamanho_total / 1024 / 1024:.2f} MB", end="\r")
            print()
        except requests.exceptions.ConnectionError as e:
            print(f"\nConexão caiu durante o download ({e}). Retomando...")
            continue

        if tamanho_total and destino.stat().st_size == tamanho_total:
            return
        print(f"\nArquivo incompleto ({destino.stat().st_size} / {tamanho_total} bytes). Retomando...")

    raise RuntimeError("Não foi possível concluir o download após várias tentativas.")

def garantir_ca_bundle():
    # o site do INEP não envia o certificado intermediário, então montamos o bundle na mão
    if not CA_BUNDLE.exists():
        intermediate = requests.get(
            "http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt", timeout=15
        ).content
        CA_BUNDLE.write_text(Path(certifi.where()).read_text() + ssl.DER_cert_to_PEM_cert(intermediate))

def pegar_microdados_ano(ano: int):
    validar_ano(ano)
    url = f"https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"

    destino = Path(f"{ZIP_DIR}/microdados_{ano}.zip")
    destino.parent.mkdir(parents=True, exist_ok=True)

    garantir_ca_bundle()
    baixar_com_resume(url, HEADERS, CA_BUNDLE, destino)

    Path(DUMP_DIR).mkdir(parents=True, exist_ok=True)
    subprocess.run(["7z", "x", "-y", f"-o{DUMP_DIR}", str(destino)], check=True)

def pegar_inse_ano(ano: int):
    """Baixa as planilhas de INSE (escolas e municípios) do ano e salva como parquet."""
    validar_ano(ano)
    garantir_ca_bundle()
    pasta_ano(ano).mkdir(parents=True, exist_ok=True)

    for tipo, arquivo in ARQUIVOS_INSE[ano].items():
        caminho_parquet = caminho_inse(ano, tipo)
        if caminho_parquet.exists():
            print(f'{caminho_parquet.name} já existe, pulando.')
            continue

        caminho_xlsx = Path(ZIP_DIR) / arquivo
        caminho_xlsx.parent.mkdir(parents=True, exist_ok=True)
        baixar_com_resume(URL_INSE.format(ano=ano, arquivo=arquivo), HEADERS, CA_BUNDLE, caminho_xlsx)

        ler_planilha_inse(caminho_xlsx).write_parquet(caminho_parquet)
        print(f'{arquivo} -> {caminho_parquet.name}')

def ler_planilha_inse(caminho_xlsx: Path) -> pl.DataFrame:
    # algumas planilhas (ex.: 2019) têm linhas de observação antes do cabeçalho
    # e asteriscos de nota de rodapé nos nomes das colunas
    bruto = pl.read_excel(caminho_xlsx, read_options={'header_row': None, 'n_rows': 20})
    primeira_coluna = bruto.to_series(0).to_list()
    linha_cabecalho = next(
        i for i, valor in enumerate(primeira_coluna)
        if valor in ('NU_ANO_SAEB', 'CO_UF', 'CO_ESCOLA')
    )

    df = pl.read_excel(caminho_xlsx, read_options={'header_row': linha_cabecalho})
    return df.rename({coluna: coluna.strip('*').strip() for coluna in df.columns})

# ---------------------------------------------------------------- organização

def organizar_dados():
    dump_path = Path(DUMP_DIR)
    dados_path = Path(DADOS_DIR)
    dados_path.mkdir(parents=True, exist_ok=True)

    for arquivo in dump_path.glob("microdados_*"):
        if not arquivo.is_dir():
            continue

        match = re.search(r"(\d{4})", arquivo.name)
        if not match:
            print(f"Não foi possível identificar o ano em '{arquivo.name}', pulando.")
            continue
        ano = int(match.group(1))
        if ano not in ANOS_INSE:
            print(f"Ano {ano} não tem INSE publicado, pulando.")
            continue

        pasta_dados = arquivo / "DADOS"
        if not pasta_dados.exists():
            print(f"Pasta DADOS não encontrada em '{arquivo}', pulando.")
            continue

        destino = dados_path / f"dados_{ano}"
        destino.mkdir(parents=True, exist_ok=True)
        for item in pasta_dados.iterdir():
            alvo = destino / item.name
            if alvo.exists():
                alvo.unlink()
            shutil.move(str(item), str(alvo))
        print(f"Dados do ano {ano} movidos para '{destino}'.")

def criar_dicionario(ano: int):
    """Gera o JSON {variável: {código: descrição}} a partir do dicionário em Excel do INEP."""
    validar_ano(ano)
    caminho_json = caminho_dicionario(ano)
    if caminho_json.exists():
        print(f'{caminho_json.name} já existe, pulando.')
        return

    caminho_excel = next(Path(DUMP_DIR).glob(f'microdados_enem_{ano}/DICIONÁRIO/*.xlsx'))
    df_dict = pl.read_excel(caminho_excel, sheet_id=1, read_options={'header_row': None})

    df_dict.columns = ['NOME_VARIAVEL', 'DESCRICAO', 'CATEGORIA', 'DESCRICAO_CATEGORIA', 'TAMANHO', 'TIPO']
    df_dict = df_dict.slice(2)

    # remove as linhas de seção (ex.: "DADOS DO PARTICIPANTE"), que têm nome mas não têm descrição
    df_dict = df_dict.filter(
        ~(pl.col('NOME_VARIAVEL').is_not_null() & pl.col('DESCRICAO').is_null())
    )

    df_categorias = df_dict.with_columns(
        pl.col('NOME_VARIAVEL').forward_fill()
    ).filter(
        pl.col('NOME_VARIAVEL').is_not_null()
        & pl.col('CATEGORIA').is_not_null()
        & pl.col('DESCRICAO_CATEGORIA').is_not_null()
    ).select(['NOME_VARIAVEL', 'CATEGORIA', 'DESCRICAO_CATEGORIA'])

    dicionario_variaveis = {}
    for nome_variavel, categoria, descricao_categoria in df_categorias.iter_rows():
        dicionario_variaveis.setdefault(nome_variavel, {})[categoria] = descricao_categoria.strip()

    caminho_json.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho_json, 'w', encoding='utf-8') as f:
        json.dump(dicionario_variaveis, f, ensure_ascii=False, indent=2)

    print(f'{caminho_json.name} criado com sucesso!')

def csvs_para_parquet():
    for caminho_csv in Path(DADOS_DIR).rglob('*.csv'):
        caminho_parquet = caminho_csv.with_suffix('.parquet')
        if caminho_parquet.exists():
            print(f'{caminho_parquet.name} já existe, pulando.')
            continue

        # o polars só lê CSV em UTF-8 de forma lazy; converter o latin1 em blocos evita
        # carregar o arquivo inteiro (2GB+) na memória
        caminho_utf8 = caminho_csv.with_suffix('.utf8.tmp')
        with open(caminho_csv, encoding='latin1', newline='') as origem, \
             open(caminho_utf8, 'w', encoding='utf-8', newline='') as destino:
            shutil.copyfileobj(origem, destino, 16 * 1024 * 1024)

        pl.scan_csv(caminho_utf8, separator=';', infer_schema_length=1_000_000).sink_parquet(caminho_parquet)
        caminho_utf8.unlink()

        tamanho_csv_mb = caminho_csv.stat().st_size / 1e6
        tamanho_parquet_mb = caminho_parquet.stat().st_size / 1e6
        print(f'{caminho_csv.name} ({tamanho_csv_mb:.1f} MB) -> {caminho_parquet.name} ({tamanho_parquet_mb:.1f} MB)')

def preparar_ano(ano: int):
    """Roda toda a extração de um ano: microdados, INSE, dicionário e conversão para parquet."""
    validar_ano(ano)
    if not caminho_microdados(ano).exists() and not caminho_microdados(ano).with_suffix('.csv').exists():
        pegar_microdados_ano(ano)
        organizar_dados()
    pegar_inse_ano(ano)
    criar_dicionario(ano)
    csvs_para_parquet()

# ---------------------------------------------------------------- leitura

def anos_disponiveis() -> list[int]:
    """Anos com todos os arquivos já extraídos e prontos para leitura."""
    return [
        ano for ano in ANOS_INSE
        if caminho_microdados(ano).exists()
        and caminho_inse(ano, 'escolas').exists()
        and caminho_inse(ano, 'municipios').exists()
        and caminho_dicionario(ano).exists()
    ]

def ler_microdados(ano: int, colunas: list[str]) -> pl.DataFrame:
    """Lê só as colunas pedidas (as que existirem naquele ano) do parquet dos microdados."""
    df = pl.scan_parquet(caminho_microdados(ano))
    existentes = [coluna for coluna in colunas if coluna in df.collect_schema().names()]
    return df.select(existentes).collect()

def ler_inse(ano: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    return pl.read_parquet(caminho_inse(ano, 'escolas')), pl.read_parquet(caminho_inse(ano, 'municipios'))

def ler_dicionario(ano: int) -> dict:
    with open(caminho_dicionario(ano), encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    # uso: python extrator_microdados.py [ano ...]   (padrão: o ano mais recente com INSE)
    anos = [int(ano) for ano in sys.argv[1:]] or [max(ANOS_INSE)]
    for ano in anos:
        preparar_ano(ano)
