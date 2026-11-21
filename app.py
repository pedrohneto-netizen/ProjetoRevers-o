import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Portal de Expedição", layout="centered")
st.title("🚚 Portal de Expedição - Motoristas")

# Define automaticamente a aba do dia no padrão "dia/mês - AM" (Fuso de São Paulo)
fuso_sp = ZoneInfo("America/Sao_Paulo")
aba_planilha = datetime.now(fuso_sp).strftime("%d/%m - AM")
# Caso queira fixar uma aba específica para testes, descomente a linha abaixo:
# aba_planilha = "19/11 - AM"

st.caption(f"📅 Expedição do dia: **{aba_planilha}**")

# Conectando ao Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(nome_aba):
    df_lido = conn.read(worksheet=nome_aba, ttl=0)
    df_lido.columns = df_lido.columns.astype(str).str.strip()
    return df_lido

def verificar_compatibilidade(veiculo_motorista, veiculo_rota):
    """
    Define a hierarquia de compatibilidade de veículos:
    - CAMINHÃO atende qualquer rota
    - VAN atende VAN, FIORINO e PASSEIO
    - FIORINO atende FIORINO e PASSEIO
    - PASSEIO atende apenas PASSEIO (ou rotas sem restrição)
    """
    hierarquia = {
        "PASSEIO": ["PASSEIO", ""],
        "FIORINO": ["FIORINO", "PASSEIO", ""],
        "VAN": ["VAN", "FIORINO", "PASSEIO", ""],
        "CAMINHÃO": ["CAMINHÃO", "VAN", "FIORINO", "PASSEIO", ""]
    }
    permitidos = hierarquia.get(veiculo_motorista.upper(), [veiculo_motorista.upper()])
    return veiculo_rota.upper() in permitidos

# Inicializa estado da sessão para o cadastro do motorista
if "motorista_cadastrado" not in st.session_state:
    st.session_state.motorista_cadastrado = False
    st.session_state.dados_motorista = {}

# ==============================================================================
# ETAPA 1: CADASTRO DO MOTORISTA
# ==============================================================================
if not st.session_state.motorista_cadastrado:
    st.subheader("1. Identificação do Motorista")
    st.write("Preencha seus dados abaixo para visualizar as rotas disponíveis.")
    
    with st.form("form_cadastro_motorista"):
        motorista_id = st.text_input("Seu ID (apenas números):")
        tipo_veiculo = st.selectbox("Tipo de Veículo:", ["PASSEIO", "FIORINO", "VAN", "CAMINHÃO"])
        telefone = st.text_input("Telefone para contato (com DDD):", placeholder="Ex: 11999999999")
        
        btn_continuar = st.form_submit_button("Ver Rotas Disponíveis", use_container_width=True)
        
        if btn_continuar:
            id_limpo = motorista_id.strip()
            tel_limpo = telefone.strip()
            
            if not id_limpo or not tel_limpo:
                st.warning("⚠️ Por favor, preencha seu ID e telefone para contato.")
            elif not id_limpo.isdigit():
                st.warning("⚠️ O ID deve conter apenas números.")
            else:
                st.session_state.dados_motorista = {
                    "id": id_limpo,
                    "veiculo": tipo_veiculo,
                    "telefone": tel_limpo
                }
                st.session_state.motorista_cadastrado = True
                st.rerun()

# ==============================================================================
# ETAPA 2: VISUALIZAÇÃO EM CARTÕES E SELEÇÃO DE ROTAS
# ==============================================================================
else:
    dados_mot = st.session_state.dados_motorista
    
    # Cabeçalho compacto com os dados do motorista e botão para corrigir cadastro
    col_info, col_sair = st.columns([3, 1])
    with col_info:
        st.info(f"👤 **ID:** {dados_mot['id']} | 🚐 **Veículo:** {dados_mot['veiculo']} | 📞 **Tel:** {dados_mot['telefone']}")
    with col_sair:
        if st.button("Alterar Dados", use_container_width=True):
            st.session_state.motorista_cadastrado = False
            st.rerun()

    # Lê a planilha do dia
    try:
        df = carregar_dados(aba_planilha)
    except Exception:
        st.error(f"A planilha da expedição **{aba_planilha}** ainda não está disponível. Aguarde a liberação.")
        st.stop()

    # Garante leitura limpa da coluna Q (ID) e coluna A (AT)
    df['ID'] = df['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df['AT'] = df['AT'].fillna('').astype(str).str.strip()
    
    # Verifica se este motorista JÁ possui uma rota atribuída hoje
    rota_existente = df[df['ID'] == dados_mot['id']]
    if not rota_existente.empty:
        gaiola_atual = rota_existente.iloc[0].get('GAIOLA', 'N/A')
        at_atual = rota_existente.iloc[0].get('AT', 'N/A')
        st.success(f"✅ Você já possui uma rota confirmada para hoje!\n\n**Gaiola:** {gaiola_atual} | **Rota (AT):** {at_atual}")
        st.stop()

    # Filtra linhas válidas e sem ID preenchido
    df_valido = df[df['AT'] != ''].copy()
    df_disponiveis = df_valido[df_valido['ID'].isin(['', 'nan', 'None', '<NA>'])].copy()

    if df_disponiveis.empty:
        st.warning("Nenhuma rota disponível no momento. Todas as gaiolas já foram preenchidas!")
        st.stop()

    st.subheader(f"2. Selecione suas opções de rota ({len(df_disponiveis)} disponíveis)")
    st.caption("Você pode marcar mais de uma opção por ordem de preferência. O sistema atribuirá **apenas 1 rota** compatível com o seu veículo.")

    # Renderiza os cartões em grade de 2 colunas
    rotas_selecionadas = []
    cols = st.columns(2)
    
    for i, (_, row) in enumerate(df_disponiveis.iterrows()):
        at_codigo = row['AT']
        gaiola = str(row.get('GAIOLA', 'Sem Gaiola')).strip()
        veiculo_req = str(row.get('Veiculo', '')).strip().upper()
        cluster = str(row.get('CLUSTER', '-')).strip()
        bairro = str(row.get('BAIRRO', '-')).strip()
        
        # Resumo dos bairros para não poluir o cartão
        bairro_resumo = bairro[:65] + "..." if len(bairro) > 65 else bairro
        compativel = verificar_compatibilidade(dados_mot['veiculo'], veiculo_req)
        
        with cols[i % 2]:
            with st.container(border=True):
                # GAIOLA como informação principal em destaque
                st.markdown(f"### 📦 Gaiola {gaiola}")
                st.markdown(f"**Veículo:** `{veiculo_req}` | **Cluster:** {cluster}")
                st.caption(f"📍 {bairro_resumo}")
                st.caption(f"🔑 AT: {at_codigo}")
                
                if compativel:
                    selecionado = st.checkbox(f"Selecionar Gaiola {gaiola}", key=f"chk_{at_codigo}")
                    if selecionado:
                        rotas_selecionadas.append(at_codigo)
                else:
                    st.button(f"Exige {veiculo_req}", key=f"dis_{at_codigo}", disabled=True, use_container_width=True)

    st.divider()
    
    # Botão de envio fixo ao final da seleção
    if st.button("🚀 Enviar Solicitação", type="primary", use_container_width=True):
        if not rotas_selecionadas:
            st.warning("⚠️ Selecione pelo menos uma gaiola antes de enviar.")
        else:
            with st.spinner("Verificando disponibilidade e compatibilidade..."):
                # Releitura em tempo real (ttl=0) antes de gravar
                df_atualizado = carregar_dados(aba_planilha)
                df_atualizado['ID'] = df_atualizado['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df_atualizado['AT'] = df_atualizado['AT'].fillna('').astype(str).str.strip()
                
                # Dupla checagem: garante que o motorista não pegou rota em outra aba/dispositivo
                if not df_atualizado[df_atualizado['ID'] == dados_mot['id']].empty:
                    st.error("Este ID já possui uma rota atribuída na planilha.")
                    st.rerun()
                
                rota_atribuida = None
                gaiola_atribuida = None
                
                # Percorre as rotas marcadas pelo motorista e pega APENAS A PRIMEIRA livre e compatível
                for at_escolhida in rotas_selecionadas:
                    filtro_linha = df_atualizado[df_atualizado['AT'] == at_escolhida]
                    if not filtro_linha.empty:
                        idx = filtro_linha.index[0]
                        id_na_planilha = df_atualizado.at[idx, 'ID']
                        veic_na_planilha = str(df_atualizado.at[idx, 'Veiculo']).strip().upper()
                        
                        # Verifica se continua vazia E se o veículo é compatível
                        if id_na_planilha in ['', 'nan', 'None', '<NA>'] and verificar_compatibilidade(dados_mot['veiculo'], veic_na_planilha):
                            # Preenche SOMENTE a coluna ID (Coluna Q)
                            df_atualizado.at[idx, 'ID'] = dados_mot['id']
                            rota_atribuida = at_escolhida
                            gaiola_atribuida = df_atualizado.at[idx, 'GAIOLA']
                            break  # Para imediatamente após preencher 1 única rota!
                
                if rota_atribuida:
                    conn.update(worksheet=aba_planilha, data=df_atualizado)
                    st.success(f"🎉 Solicitação confirmada! A **Gaiola {gaiola_atribuida}** ({rota_atribuida}) foi atribuída ao seu ID **{dados_mot['id']}**.")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("😕 As rotas selecionadas acabaram de ser preenchidas por outros motoristas ou não são compatíveis. Escolha outras opções!")
                    st.rerun()
