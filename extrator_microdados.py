import ssl
import zipfile
from pathlib import Path
import time
import certifi
import requests

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

    destino = Path(f"Microdados_ZIP/microdados_{ano}.zip")
    destino.parent.mkdir(parents=True, exist_ok=True)

    CA_BUNDLE = Path("inep_ca_bundle.pem")
    if not CA_BUNDLE.exists():
        intermediate = requests.get(
            "http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt", timeout=15
        ).content
        CA_BUNDLE.write_text(Path(certifi.where()).read_text() + ssl.DER_cert_to_PEM_cert(intermediate))

    resposta = pegar_com_retry(url, HEADERS, CA_BUNDLE)
    with open(destino, "wb") as f:
        for chunk in resposta.iter_content(chunk_size=8192):
            f.write(chunk)
            print(f"Baixando: {f.tell() / 1024 / 1024:.2f} MB", end="\r")
    print()

    with zipfile.ZipFile(destino) as z:
        z.extractall(f"dados_censos")

if __name__ == "__main__":
    pegar_microdados_ano(2025)