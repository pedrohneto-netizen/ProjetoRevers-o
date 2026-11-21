import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Portal de Expedição", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)
ABA_CONFIG = "CONFIG_ADMIN"

# ==============================================================================
# FUNÇÕES DE LEITURA E GRAVAÇÃO DE CONFIGURAÇÃO
# ==============================================================================
def ler_configuracao():
    fuso_sp = ZoneInfo("America/Sao_Paulo")
    aba_padrao = datetime.now(fuso_sp).strftime("%d/%m - AM")
    try:
        df_cfg = conn.read(worksheet=ABA_CONFIG, ttl=0)
        aba_ativa = str(df_cfg.at[0, 'aba_ativa']).strip()
        liberado = str(df_cfg.at[0, 'portal_liberado']).strip().upper() == "SIM"
        bloq_raw = str(df_cfg.at[0, 'gaiolas_bloqueadas']) if 'gaiolas_bloqueadas' in df_cfg.columns else ""
        bloqueadas = [g.strip() for g in bloq_raw.split(",") if g.strip() and g.strip().lower() != "nan"]
        return aba_ativa if aba_ativa and aba_ativa.lower() != "nan" else aba_padrao, liberado, bloqueadas
    except Exception:
        # Caso a aba CONFIG_ADMIN ainda não exista, usa valores seguros
        return aba_padrao, False, []

def salvar_configuracao(aba_ativa, portal_liberado, lista_bloqueadas):
    df_nova_cfg = pd.DataFrame([{
        "aba_ativa": aba_ativa.strip(),
        "portal_liberado": "SIM" if portal_liberado else "NAO",
        "gaiolas_bloqueadas": ",".join(lista_bloqueadas)
    }])
    conn.update(worksheet=ABA_CONFIG, data=df_nova_cfg)

def carregar_dados(nome_aba):
    df_lido = conn.read(worksheet=nome_aba, ttl=0)
    df_lido.columns = df_lido.columns.astype(str).str.strip()
    return df_lido

def verificar_compatibilidade(veiculo_motorista, veiculo_rota):
    hierarquia = {
        "PASSEIO": ["PASSEIO", ""],
        "FIORINO": ["FIORINO", "PASSEIO", ""],
        "VAN": ["VAN", "FIORINO", "PASSEIO", ""],
        "CAMINHÃO": ["CAMINHÃO", "VAN", "FIORINO", "PASSEIO", ""]
    }
    permitidos = hierarquia.get(veiculo_motorista.upper(), [veiculo_motorista.upper()])
    return veiculo_rota.upper() in permitidos

# ==============================================================================
# CONTROLE DE SESSÃO (ADMIN vs MOTORISTA)
# ==============================================================================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "mostrar_login_admin" not in st.session_state:
    st.session_state.mostrar_login_admin = False
if "motorista_cadastrado" not in st.session_state:
    st.session_state.motorista_cadastrado = False
    st.session_state.dados_motorista = {}

# Cabeçalho com botão discreto para o Administrador
col_titulo, col_btn_admin = st.columns([4, 1])
with col_titulo:
    st.title("🚚 Portal de Expedição")
with col_btn_admin:
    st.write("")
    if not st.session_state.is_admin:
        if st.button("🔒 Admin", use_container_width=True):
            st.session_state.mostrar_login_admin = not st.session_state.mostrar_login_admin
    else:
        if st.button("🚪 Sair Admin", use_container_width=True):
            st.session_state.is_admin = False
            st.session_state.mostrar_login_admin = False
            st.rerun()

# Caixa de login do Administrador (só aparece se clicar no cadeado)
if st.session_state.mostrar_login_admin and not st.session_state.is_admin:
    with st.container(border=True):
        st.subheader("Acesso Restrito - Administrador")
        senha_digitada = st.text_input("Digite a senha de administrador:", type="password")
        if st.button("Entrar no Painel"):
            senha_correta = st.secrets.get("admin_password", "admin123")
            if senha_digitada == senha_correta:
                st.session_state.is_admin = True
                st.session_state.mostrar_login_admin = False
                st.rerun()
            else:
                st.error("Senha incorreta.")

# Carrega status atual definido pelo Administrador
aba_planilha, portal_liberado, gaiolas_bloqueadas = ler_configuracao()

# ==============================================================================
# MODO ADMINISTRADOR (EXCLUSIVO PARA VOCÊ)
# ==============================================================================
if st.session_state.is_admin:
    st.success("🔓 **Modo Administrador Ativo**")
    
    with st.container(border=True):
        st.subheader("⚙️ Controle Geral de Liberação")
        
        fuso_sp = ZoneInfo("America/Sao_Paulo")
        sugestao_hoje = datetime.now(fuso_sp).strftime("%d/%m - AM")
        
        col_a, col_b = st.columns([2, 1])
        with col_a:
            nova_aba = st.text_input(
                "Nome da Aba da Expedição:",
                value=aba_planilha,
                help=f"Padrão diário: {sugestao_hoje}"
            )
        with col_b:
            st.write("")
            st.write("")
            status_toggle = st.toggle("🟢 Liberar Rotas", value=portal_liberado)
            
        st.caption(f"Status atual para os motoristas: **{'LIBERADO (Visível)' if status_toggle else 'BLOQUEADO (Oculto)'}**")

        # Tenta carregar a aba escolhida para permitir bloquear/liberar gaiolas individuais
        gaiolas_disponiveis_aba = []
        df_admin = None
        try:
            df_admin = carregar_dados(nova_aba)
            df_admin['ID'] = df_admin['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            df_admin['AT'] = df_admin['AT'].fillna('').astype(str).str.strip()
            df_admin = df_admin[df_admin['AT'] != '']
            if 'GAIOLA' in df_admin.columns:
                gaiolas_disponiveis_aba = df_admin['GAIOLA'].dropna().astype(str).str.strip().tolist()
        except Exception:
            st.warning(f"⚠️ A aba **'{nova_aba}'** ainda não foi encontrada na planilha.")

        novas_bloqueadas = st.multiselect(
            "Ocultar gaiolas específicas (opcional - deixe vazio para exibir todas):",
            options=gaiolas_disponiveis_aba,
            default=[g for g in gaiolas_bloqueadas if g in gaiolas_disponiveis_aba]
        )

        if st.button("💾 Salvar Configurações", type="primary", use_container_width=True):
            try:
                salvar_configuracao(nova_aba, status_toggle, novas_bloqueadas)
                st.success("✅ Configurações atualizadas com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar na aba '{ABA_CONFIG}'. Verifique se você criou essa aba na planilha. Detalhe: {e}")

    # Painel de acompanhamento em tempo real para o Admin
    if df_admin is not None:
        st.divider()
        st.subheader(f"📊 Acompanhamento em Tempo Real ({nova_aba})")
        total_rotas = len(df_admin)
        atribuidas = len(df_admin[~df_admin['ID'].isin(['', 'nan', 'None', '<NA>'])])
        livres = total_rotas - atribuidas
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total de Rotas", total_rotas)
        m2.metric("Atribuídas", atribuidas)
        m3.metric("Disponíveis", livres)
        
        colunas_monitor = [c for c in ['GAIOLA', 'AT', 'Veiculo', 'CLUSTER', 'ID', 'NOME'] if c in df_admin.columns]
        st.dataframe(df_admin[colunas_monitor], use_container_width=True, hide_index=True)

    st.stop()

# ==============================================================================
# MODO MOTORISTA (O QUE OS MOTORISTAS VEEM)
# ==============================================================================
st.caption(f"📅 Expedição: **{aba_planilha}**")

# Se o administrador NÃO liberou o portal, bloqueia tudo para os motoristas
if not portal_liberado:
    st.warning("⏳ **As rotas ainda não foram liberadas pela expedição.**\n\nAguarde a liberação do administrador e atualize a página.")
    if st.button("🔄 Atualizar Página", use_container_width=True):
        st.rerun()
    st.stop()

# ETAPA 1: CADASTRO DO MOTORISTA
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

# ETAPA 2: CARTÕES DE ROTAS E SOLICITAÇÃO
else:
    dados_mot = st.session_state.dados_motorista
    
    col_info, col_sair = st.columns([3, 1])
    with col_info:
        st.info(f"👤 **ID:** {dados_mot['id']} | 🚐 **Veículo:** {dados_mot['veiculo']} | 📞 **Tel:** {dados_mot['telefone']}")
    with col_sair:
        if st.button("Alterar Dados", use_container_width=True):
            st.session_state.motorista_cadastrado = False
            st.rerun()

    try:
        df = carregar_dados(aba_planilha)
    except Exception:
        st.error(f"A planilha da expedição **{aba_planilha}** ainda não está disponível. Aguarde a liberação.")
        st.stop()

    df['ID'] = df['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df['AT'] = df['AT'].fillna('').astype(str).str.strip()
    
    # Verifica se este motorista JÁ possui uma rota atribuída
    rota_existente = df[df['ID'] == dados_mot['id']]
    if not rota_existente.empty:
        gaiola_atual = rota_existente.iloc[0].get('GAIOLA', 'N/A')
        at_atual = rota_existente.iloc[0].get('AT', 'N/A')
        st.success(f"✅ Você já possui uma rota confirmada!\n\n**Gaiola:** {gaiola_atual} | **Rota (AT):** {at_atual}")
        st.stop()

    # Filtra rotas válidas, sem ID preenchido e que NÃO estejam bloqueadas pelo Admin
    df_valido = df[df['AT'] != ''].copy()
    df_disponiveis = df_valido[df_valido['ID'].isin(['', 'nan', 'None', '<NA>'])].copy()
    
    if 'GAIOLA' in df_disponiveis.columns and gaiolas_bloqueadas:
        df_disponiveis['GAIOLA_STR'] = df_disponiveis['GAIOLA'].astype(str).str.strip()
        df_disponiveis = df_disponiveis[~df_disponiveis['GAIOLA_STR'].isin(gaiolas_bloqueadas)]

    if df_disponiveis.empty:
        st.warning("Nenhuma rota disponível no momento. Todas as gaiolas liberadas já foram preenchidas!")
        st.stop()

    st.subheader(f"2. Selecione suas opções de rota ({len(df_disponiveis)} disponíveis)")
    st.caption("Marque suas opções de preferência. O sistema atribuirá **apenas 1 rota** compatível com o seu veículo.")

    rotas_selecionadas = []
    cols = st.columns(2)
    
    for i, (_, row) in enumerate(df_disponiveis.iterrows()):
        at_codigo = row['AT']
        gaiola = str(row.get('GAIOLA', 'Sem Gaiola')).strip()
        veiculo_req = str(row.get('Veiculo', '')).strip().upper()
        cluster = str(row.get('CLUSTER', '-')).strip()
        bairro = str(row.get('BAIRRO', '-')).strip()
        
        bairro_resumo = bairro[:65] + "..." if len(bairro) > 65 else bairro
        compativel = verificar_compatibilidade(dados_mot['veiculo'], veiculo_req)
        
        with cols[i % 2]:
            with st.container(border=True):
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
    
    if st.button("🚀 Enviar Solicitação", type="primary", use_container_width=True):
        if not rotas_selecionadas:
            st.warning("⚠️ Selecione pelo menos uma gaiola antes de enviar.")
        else:
            with st.spinner("Verificando disponibilidade e compatibilidade..."):
                df_atualizado = carregar_dados(aba_planilha)
                df_atualizado['ID'] = df_atualizado['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df_atualizado['AT'] = df_atualizado['AT'].fillna('').astype(str).str.strip()
                
                if not df_atualizado[df_atualizado['ID'] == dados_mot['id']].empty:
                    st.error("Este ID já possui uma rota atribuída na planilha.")
                    st.rerun()
                
                rota_atribuida = None
                gaiola_atribuida = None
                
                for at_escolhida in rotas_selecionadas:
                    filtro_linha = df_atualizado[df_atualizado['AT'] == at_escolhida]
                    if not filtro_linha.empty:
                        idx = filtro_linha.index[0]
                        id_na_planilha = df_atualizado.at[idx, 'ID']
                        veic_na_planilha = str(df_atualizado.at[idx, 'Veiculo']).strip().upper()
                        
                        if id_na_planilha in ['', 'nan', 'None', '<NA>'] and verificar_compatibilidade(dados_mot['veiculo'], veic_na_planilha):
                            df_atualizado.at[idx, 'ID'] = dados_mot['id']
                            rota_atribuida = at_escolhida
                            gaiola_atribuida = df_atualizado.at[idx, 'GAIOLA']
                            break
                
                if rota_atribuida:
                    conn.update(worksheet=aba_planilha, data=df_atualizado)
                    st.success(f"🎉 Solicitação confirmada! A **Gaiola {gaiola_atribuida}** ({rota_atribuida}) foi atribuída ao seu ID **{dados_mot['id']}**.")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("😕 As rotas selecionadas acabaram de ser preenchidas ou não são compatíveis. Escolha outras opções!")
                    st.rerun()
