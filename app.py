import sys

import polars as pl
import streamlit as st

import main
from graficos import percentil

# permite rodar com "python app.py" (ex.: botão Run do VSCode), relançando via "streamlit run"
if __name__ == '__main__' and not st.runtime.exists():
    from streamlit.web import cli as stcli
    sys.argv = ['streamlit', 'run', __file__, *sys.argv[1:]]
    sys.exit(stcli.main())

st.set_page_config(page_title='Posição no ENEM', layout='wide')

# diferença (em pontos) até a qual o candidato é considerado "dentro da média"
TOLERANCIA_MEDIA = 10.0

# rótulo no formulário -> variável do dicionário (as opções vêm do main.opcoes_formulario)
CAMPOS_PERFIL = {
    'sexo': ('Sexo', 'TP_SEXO'),
    'cor_raca': ('Cor/raça', 'TP_COR_RACA'),
    'nacionalidade': ('Nacionalidade', 'TP_NACIONALIDADE'),
    'st_conclusao': ('Situação do Ensino Médio', 'TP_ST_CONCLUSAO'),
    'ano_concluiu': ('Ano de conclusão do Ensino Médio', 'TP_ANO_CONCLUIU'),
}


def iniciar_estado():
    if 'pagina' not in st.session_state:
        st.session_state.pagina = 'login'
        st.session_state.usuario = None
        st.session_state.resultado = None


def ir_para(pagina: str):
    st.session_state.pagina = pagina
    st.rerun()


def pagina_login():
    st.title('Login')

    with st.form('form_login'):
        usuario = st.text_input('Usuário')
        senha = st.text_input('Senha', type='password')
        entrar = st.form_submit_button('Entrar')

    if entrar:
        if main.autenticar(usuario, senha):
            st.session_state.usuario = usuario
            ir_para('formulario')
        else:
            st.error('Usuário ou senha inválidos.')


def pagina_formulario():
    st.title('Dados do candidato')

    try:
        opcoes = main.opcoes_formulario()
    except main.DadosIndisponiveis as erro:
        st.error(str(erro))
        st.stop()

    st.caption(f'Comparação com os microdados do Enem {opcoes["ano"]}.')

    with st.form('form_candidato'):
        st.subheader('Nota')
        area = st.selectbox('Área de conhecimento', opcoes['areas'])
        nota = st.number_input('Sua nota', min_value=0.0, max_value=1000.0, value=None, step=0.1)

        st.subheader('Localização')
        uf = st.selectbox('Unidade da Federação', opcoes['ufs'], index=None, placeholder='Selecione a sua UF')
        co_municipio = st.text_input('Código do município (IBGE)', placeholder='Ex.: 3550308')
        co_escola = st.text_input('Código da escola (opcional)', placeholder='Ex.: 35000000')

        st.subheader('Perfil')
        idade = st.number_input('Idade', min_value=10, max_value=100, value=None, step=1)
        perfil = {
            campo: st.selectbox(rotulo, opcoes[variavel], index=None, placeholder='Selecione')
            for campo, (rotulo, variavel) in CAMPOS_PERFIL.items()
        }
        treineiro = st.checkbox('Fiz a prova apenas para treinar (treineiro)')

        enviar = st.form_submit_button('Ver resultado')

    if not enviar:
        return

    if nota is None:
        st.error('Informe a sua nota.')
        return
    if uf is None:
        st.error('Selecione a sua UF.')
        return
    if not co_municipio.strip().isdigit():
        st.error('Informe um código de município válido (apenas números).')
        return
    if co_escola.strip() and not co_escola.strip().isdigit():
        st.error('O código da escola deve conter apenas números.')
        return
    if idade is None:
        st.error('Informe a sua idade.')
        return
    faltando = [CAMPOS_PERFIL[campo][0] for campo, valor in perfil.items() if valor is None]
    if faltando:
        st.error(f'Preencha: {", ".join(faltando)}.')
        return

    entrada = {
        'area': area,
        'nota': nota,
        'uf': uf,
        'co_municipio': int(co_municipio),
        'co_escola': int(co_escola) if co_escola.strip() else None,
        'idade': idade,
        **perfil,
        'treineiro': treineiro,
    }

    try:
        with st.spinner('Calculando...'):
            st.session_state.resultado = main.analisar(entrada)
    except ValueError as erro:
        st.error(str(erro))
        return
    ir_para('dashboard')


def mensagem_posicao(posicao: dict):
    diferenca = posicao['diferenca_absoluta']

    if diferenca > TOLERANCIA_MEDIA:
        st.success(f'Você está acima da média ({diferenca:+.1f} pontos).')
    elif diferenca < -TOLERANCIA_MEDIA:
        st.error(f'Você está abaixo da média ({diferenca:+.1f} pontos).')
    else:
        st.info(f'Você está dentro da média ({diferenca:+.1f} pontos).')


def pagina_dashboard():
    st.title('Dashboard')

    resultado = st.session_state.resultado
    posicao = resultado['posicao']
    st.caption(
        f'Enem {resultado["ano"]} · {posicao["nivel_inse"]} do INSE '
        f'(estimado {"pela sua escola" if resultado["fonte_nivel"] == "escola" else "pelo seu município"}) · '
        f'{posicao["tamanho_grupo"]:,} candidatos no grupo'
    )
    mensagem_posicao(posicao)

    coluna_1, coluna_2 = st.columns(2)
    with coluna_1:
        st.subheader('Sua posição entre os candidatos')
        st.caption(percentil.frase_percentil(resultado['percentis']))
        st.altair_chart(percentil.grafico_percentis(resultado['percentis']), width='stretch')
    with coluna_2:
        # TODO: gráfico de outro integrante
        st.subheader('Gráfico 2')
        st.bar_chart(resultado['media_por_nivel'], x='NIVEL_ESTIMADO', y='MEDIA_MT')

    coluna_3, coluna_4 = st.columns(2)
    with coluna_3:
        # TODO: gráfico/tabela de outro integrante
        st.subheader('Tabela 1')
        st.dataframe(resultado['media_por_nivel'], hide_index=True)
    with coluna_4:
        # TODO: gráfico/tabela de outro integrante
        st.subheader('Resumo')
        st.dataframe(pl.DataFrame({
            'INDICADOR': list(posicao.keys()),
            'VALOR': [str(valor) for valor in posicao.values()],
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
