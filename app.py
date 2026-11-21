import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Portal de Expedição", layout="centered")
st.title("🚚 Portal de Expedição - Motoristas")

# Conectando ao Google Sheets usando [connections.gsheets] dos Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# Nome exato da aba na planilha
aba_planilha = "Plano de expedição"

# Função auxiliar para ler e padronizar colunas
def carregar_dados():
    # Se o cabeçalho não estiver na linha 1 da planilha, adicione header=1 (linha 2), header=2 (linha 3), etc.
    dados = conn.read(worksheet=aba_planilha, ttl=0)
    dados.columns = dados.columns.astype(str).str.strip()
    return dados

df = carregar_dados()

# Verifica se 'ID' existe (mesmo se estiver em minúsculo, como 'id' ou 'Id')
colunas_maiusculas = {col.upper(): col for col in df.columns}

if 'ID' in colunas_maiusculas:
    nome_real_coluna_id = colunas_maiusculas['ID']
    df.rename(columns={nome_real_coluna_id: 'ID'}, inplace=True)
    df['ID'] = df['ID'].fillna('').astype(str)
else:
    st.error("Coluna 'ID' não encontrada na planilha.")
    st.warning(f"Colunas que o sistema encontrou na linha 1 da aba '{aba_planilha}':")
    st.write(list(df.columns))
    st.dataframe(df.head(5), use_container_width=True)
    st.stop()

# Filtrando apenas rotas sem ID preenchido
df_disponiveis = df[df['ID'].str.strip().isin(['', 'nan', 'None'])]

if df_disponiveis.empty:
    st.info("Nenhuma rota disponível no momento. Todas já foram atribuídas!")
else:
    st.subheader("Rotas Disponíveis")
    
    # Colunas visíveis para os motoristas
    colunas_visiveis = ['AT', 'GAIOLA', 'Veiculo', 'CLUSTER']
    colunas_existentes = [col for col in colunas_visiveis if col in df_disponiveis.columns]
    
    st.dataframe(df_disponiveis[colunas_existentes], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Solicitar Rota")
    
    with st.form("form_solicitacao"):
        motorista_id = st.text_input("Digite o seu ID:")
        tipo_veiculo = st.selectbox("Qual o seu veículo?", ["PASSEIO", "FIORINO", "VAN", "CAMINHÃO"])
        
        opcoes_rotas = df_disponiveis['AT'].tolist() if 'AT' in df_disponiveis.columns else df_disponiveis.index.tolist()
        rota_escolhida = st.selectbox("Selecione a rota (AT):", opcoes_rotas)
        
        submit = st.form_submit_button("Confirmar Solicitação")
        
        if submit:
            if not motorista_id.strip():
                st.warning("Por favor, preencha o seu ID.")
            else:
                # Releitura em tempo real (ttl=0) antes de gravar para evitar conflitos
                df_atualizado = carregar_dados()
                df_atualizado.rename(columns={nome_real_coluna_id: 'ID'}, inplace=True)
                df_atualizado['ID'] = df_atualizado['ID'].fillna('').astype(str)
                
                if 'AT' in df_atualizado.columns:
                    idx_rota = df_atualizado[df_atualizado['AT'] == rota_escolhida].index[0]
                else:
                    idx_rota = rota_escolhida
                
                id_atual = df_atualizado.at[idx_rota, 'ID'].strip()
                
                if id_atual in ['', 'nan', 'None']:
                    veiculo_rota = str(df_atualizado.at[idx_rota, 'Veiculo']).strip().upper() if 'Veiculo' in df_atualizado.columns else ''
                    
                    if veiculo_rota == 'FIORINO' and tipo_veiculo != 'FIORINO':
                        st.error(f"Esta rota tem prioridade/exigência para FIORINO. Seu veículo é {tipo_veiculo}.")
                    else:
                        df_atualizado.at[idx_rota, 'ID'] = motorista_id.strip()
                        
                        # Restaura o nome original da coluna antes de salvar, caso fosse 'Id' ou 'id'
                        df_para_salvar = df_atualizado.rename(columns={'ID': nome_real_coluna_id})
                        conn.update(worksheet=aba_planilha, data=df_para_salvar)
                        
                        st.success(f"Sucesso! A rota {rota_escolhida} foi atribuída ao ID {motorista_id}.")
                        st.rerun()
                else:
                    st.error("Poxa, outro motorista acabou de pegar essa rota! Tente outra.")
                    st.rerun()
