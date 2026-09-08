import re
import shutil
import ssl
import zipfile
from pathlib import Path
import time
import certifi
import requests

from config import ZIP_DIR, DUMP_DIR, DADOS_DIR

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def pegar_com_retry(url, headers, ca_bundle, tentativas=5):
    for i in range(tentativas):
        try:
            resposta = requests.get(url, stream=True, timeout=30, verify=str(ca_bundle), headers=headers)
            resposta.raise_for_status()
            return resposta
        except requests.exceptions.ConnectionError as e:
            espera = 2 ** i  # backoff exponencial: 1, 2, 4, 8, 16s
            print(f"Tentativa {i+1} falhou ({e}). Esperando {espera}s...")
            time.sleep(espera)
    raise RuntimeError("Não foi possível baixar o arquivo após várias tentativas.")

def pegar_microdados_ano(ano: int):
    url = f"https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"

    destino = Path(f"{ZIP_DIR}/microdados_{ano}.zip")
    destino.parent.mkdir(parents=True, exist_ok=True)

    CA_BUNDLE = Path("inep_ca_bundle.pem")
    if not CA_BUNDLE.exists():
        intermediate = requests.get(
            "http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt", timeout=15
        ).content
        CA_BUNDLE.write_text(Path(certifi.where()).read_text() + ssl.DER_cert_to_PEM_cert(intermediate))

    resposta = pegar_com_retry(url, HEADERS, CA_BUNDLE)
    tamanho_total = int(resposta.headers.get("content-length", 0)) / 1024 / 1024
    with open(destino, "wb") as f:
        for chunk in resposta.iter_content(chunk_size=8192):
            f.write(chunk)
            print(f"Baixando: {f.tell() / 1024 / 1024:.2f} / {tamanho_total:.2f} MB", end="\r")
    print()

    with zipfile.ZipFile(destino) as z:
        z.extractall(DUMP_DIR)

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
        ano = match.group(1)

        pasta_dados = arquivo / "DADOS"
        if not pasta_dados.exists():
            print(f"Pasta DADOS não encontrada em '{arquivo}', pulando.")
            continue

        destino = dados_path / f"dados_{ano}"
        if destino.exists():
            shutil.rmtree(destino)
        shutil.move(str(pasta_dados), str(destino))
        print(f"Dados do ano {ano} movidos para '{destino}'.")

if __name__ == "__main__":
    # pegar_microdados_ano(2025)
    organizar_dados()