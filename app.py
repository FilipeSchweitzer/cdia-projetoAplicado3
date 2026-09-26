import sys

import polars as pl
import streamlit as st

# permite rodar com "python app.py" (ex.: botão Run do VSCode), relançando via "streamlit run"
if __name__ == '__main__' and not st.runtime.exists():
    from streamlit.web import cli as stcli
    sys.argv = ['streamlit', 'run', __file__, *sys.argv[1:]]
    sys.exit(stcli.main())

st.set_page_config(page_title='Posição no ENEM', layout='wide')

# valores fixos das áreas de conhecimento (coluna_nota em estimar_posicao_candidato)
AREAS_NOTA = {
    'Ciências da Natureza': 'NU_NOTA_CN',
    'Ciências Humanas': 'NU_NOTA_CH',
    'Linguagens e Códigos': 'NU_NOTA_LC',
    'Matemática': 'NU_NOTA_MT',
    'Redação': 'NU_NOTA_REDACAO',
}

# diferença (em pontos) até a qual o candidato é considerado "dentro da média"
TOLERANCIA_MEDIA = 10.0


def iniciar_estado():
    if 'pagina' not in st.session_state:
        st.session_state.pagina = 'login'
        st.session_state.usuario = None
        st.session_state.parametros = None


def ir_para(pagina: str):
    st.session_state.pagina = pagina
    st.rerun()


def autenticar(usuario: str, senha: str) -> bool:
    # TODO: validar usuário e senha de verdade
    return bool(usuario) and bool(senha)


def calcular_resultado(parametros: dict) -> dict:
    # TODO: substituir por estimar_posicao_candidato(**parametros) do Colab_notebook.ipynb
    media_grupo = 550.0
    return {
        'nivel_inse': 'Nível IV',
        'tamanho_grupo': 0,
        'media_grupo': media_grupo,
        'nota_usuario': parametros['nota_usuario'],
        'diferenca_absoluta': round(parametros['nota_usuario'] - media_grupo, 1),
        'percentil_usuario': 0.0,
    }


def pagina_login():
    st.title('Login')

    with st.form('form_login'):
        usuario = st.text_input('Usuário')
        senha = st.text_input('Senha', type='password')
        entrar = st.form_submit_button('Entrar')

    if entrar:
        if autenticar(usuario, senha):
            st.session_state.usuario = usuario
            ir_para('formulario')
        else:
            st.error('Usuário ou senha inválidos.')


def pagina_formulario():
    st.title('Dados do candidato')

    with st.form('form_candidato'):
        area = st.selectbox('Área de conhecimento', list(AREAS_NOTA.keys()))
        nota_usuario = st.number_input('Sua nota', min_value=0.0, max_value=1000.0, step=0.1)
        co_municipio = st.text_input('Código do município (IBGE)', placeholder='Ex.: 3550308')
        co_escola = st.text_input('Código da escola (opcional)', placeholder='Ex.: 35000000')
        enviar = st.form_submit_button('Ver resultado')

    if enviar:
        if not co_municipio.strip().isdigit():
            st.error('Informe um código de município válido (apenas números).')
            return
        if co_escola.strip() and not co_escola.strip().isdigit():
            st.error('O código da escola deve conter apenas números.')
            return

        st.session_state.parametros = {
            'nota_usuario': nota_usuario,
            'coluna_nota': AREAS_NOTA[area],
            'co_municipio': int(co_municipio),
            'co_escola': int(co_escola) if co_escola.strip() else None,
        }
        ir_para('dashboard')


def mensagem_posicao(resultado: dict):
    diferenca = resultado['diferenca_absoluta']

    if diferenca > TOLERANCIA_MEDIA:
        st.success(f'Você está acima da média ({diferenca:+.1f} pontos).')
    elif diferenca < -TOLERANCIA_MEDIA:
        st.error(f'Você está abaixo da média ({diferenca:+.1f} pontos).')
    else:
        st.info(f'Você está dentro da média ({diferenca:+.1f} pontos).')


def pagina_dashboard():
    st.title('Dashboard')

    resultado = calcular_resultado(st.session_state.parametros)
    mensagem_posicao(resultado)

    # TODO: trocar os dados de exemplo pelos dados reais de cada gráfico/tabela
    exemplo = pl.DataFrame({
        'NIVEL': ['I', 'II', 'III', 'IV', 'V', 'VI'],
        'MEDIA': [450.0, 480.0, 510.0, 540.0, 570.0, 600.0],
    })

    coluna_1, coluna_2 = st.columns(2)
    with coluna_1:
        st.subheader('Gráfico 1')
        st.bar_chart(exemplo, x='NIVEL', y='MEDIA')
    with coluna_2:
        st.subheader('Gráfico 2')
        st.line_chart(exemplo, x='NIVEL', y='MEDIA')

    coluna_3, coluna_4 = st.columns(2)
    with coluna_3:
        st.subheader('Tabela 1')
        st.dataframe(exemplo, hide_index=True)
    with coluna_4:
        st.subheader('Resumo')
        st.dataframe(pl.DataFrame({
            'INDICADOR': list(resultado.keys()),
            'VALOR': [str(valor) for valor in resultado.values()],
        }), hide_index=True)

    if st.button('Nova consulta'):
        ir_para('formulario')


iniciar_estado()

with st.sidebar:
    if st.session_state.usuario:
        st.write(f'Usuário: {st.session_state.usuario}')
        if st.button('Sair'):
            st.session_state.clear()
            st.rerun()

if st.session_state.pagina == 'login':
    pagina_login()
elif st.session_state.pagina == 'formulario':
    pagina_formulario()
else:
    pagina_dashboard()
