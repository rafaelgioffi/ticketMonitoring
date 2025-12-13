import streamlit as st
import psycopg2
import os
from datetime import datetime

# Configuração da página
st.set_page_config(
    page_title="Monitor de Passagens", 
    page_icon="🚌", 
    layout="centered"
    )

CIDADES_MAP = {
    "Araruama": "14265",
    "Búzios": "14103",
    "Cabo Frio": "14270",
    "Campos dos Goytacazes (Shop.Estrada)": "14245",
    "Macaé": "14235",
    "Niterói": "14224",
    "Rio das Ostras": "14274",
    "Rio de Janeiro (Novo Rio)": "14199",
    "São Paulo (Tietê)": "18697", # Exemplo fictício, verifique o ID real se usar
}

ID_TO_NOME = {v: k for k, v in CIDADES_MAP.items()}

# Conexão com Banco
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url and "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
    
    return psycopg2.connect(db_url)

st.title("🚌 Monitor de Passagens")
st.markdown("---")
# Colunas para mostrar o Status Atual (Lendo tabela monitor_status)
col_status1, col_status2 = st.columns(2)

try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT price, register_date FROM price_history WHERE id=1")
    status = cur.fetchone()
    # conn.close()
    
    if status:
        price = status[0]
        timestamp_utc = status[1]
        # register_date = status[1].strftime("%d/%m/%Y %H:%M") if status[1] else "Nunca"
        if timestamp_utc:
            timestamp_br = timestamp_utc - timedelta(hours=3)  # Ajuste para horário de Brasília
            last_update_str = timestamp_br.strftime("%d/%m/%Y %H:%M")
        else:
            register_date = "Ainda não monitorado"
        
        with col_status1:
            st.metric("💰 Último Preço Encontrado", f"R$ {price:.2f}")
        with col_status2:
            st.metric("🕒 Última Atualização", last_update_str)
    else:
        st.warning("Ainda sem dados de monitoramento...")
    
    conn.close()
    
except Exception as e:
    st.error(f"Erro ao conectar... {e}")

st.markdown("---")

# --- FORMULÁRIO DE CONFIGURAÇÃO ---
st.subheader("⚙️ Configurar Busca")

try:
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Busca configuração atual para preencher o formulário
    cur.execute("SELECT travel_date, origin_id, destiny_id, adults, children, teens, target_hours, active FROM search_config WHERE id=1")
    config = cur.fetchone()
    conn.close()

    if config:
        db_date_str = config[0]
        db_origin_id = config[1]
        db_destiny_id = config[2]
        
        try:
            default_date = datetime.strptime(db_date_str, "%d%m%Y").date()
        except:
            default_date = datetime.today().date()
            
        #Selects das cidades...
        origin_default_idx = list(CIDADES_MAP.values()).index(db_origin_id) if db_origin_id in CIDADES_MAP.values() else 0
        destiny_default_idx = list(CIDADES_MAP.values()).index(db_destiny_id) if db_destiny_id in CIDADES_MAP.values() else 1
        
        # Cria o formulário
        with st.form("config_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                new_date_obj = st.date_input("Data da Viagem", value=default_date, format="DD/MM/YYYY")
                
                origin = st.selectbox("Origem", options=list(CIDADES_MAP.keys()), index=origin_default_idx)
                # O site pede DDMMAAAA, mantemos texto para evitar erros de conversão
                # travel_date = st.text_input("Data da Viagem (DDMMAAAA)", value=config[0])
                # origin_id = st.text_input("ID Origem", value=config[1])
                active_monitor = st.checkbox("Monitor Ativo?", value=config[7])
                
            with col2:
                # Horários alvo
                target_hours = st.text_input("Horas Alvo (separar por vírgula)", value=config[6], help="Ex: 22,23,0 para buscar ônibus saindo às 22h, 23h ou Meia-noite.")
                # destiny_id = st.text_input("ID Destino", value=config[2])
                destiny = st.selectbox("Destino", options=list(CIDADES_MAP.keys()), index=destiny_default_idx)

            st.write("**Passageiros**")
            p_col1, p_col2, p_col3 = st.columns(3)
            
            with p_col1:
                adults = st.number_input("Adultos", min_value=1, value=config[3])
            with p_col2:
                children = st.number_input("Crianças", min_value=0, value=config[4])
            with p_col3:
                teens = st.number_input("Jovens", min_value=0, value=config[5])

            # Botão de Salvar
            submitted = st.form_submit_button("💾 Salvar Novas Regras")

            if submitted:
                date_to_save = new_date_obj.strftime("%d%m%Y")
                id_origin = CIDADES_MAP[origin]
                id_destiny = CIDADES_MAP[destiny]
                
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    
                    sql = """
                        UPDATE search_config 
                        SET travel_date=%s, origin_id=%s, destiny_id=%s, 
                            adults=%s, children=%s, teens=%s, 
                            target_hours=%s, active=%s
                        WHERE id=1;
                    """
                    cur.execute(sql, (date_to_save, id_origin, id_destiny, adults, children, teens, target_hours, active_monitor))
                    conn.commit()
                    conn.close()
                    st.success("✅ Configurações salvas! Viagem de {origin} para {destiny} em {new_date_obj.strftime('%d/%m/%Y')}.")
                    
                    # Recarrega a página para atualizar os dados visuais
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
    else:
        st.error("Não foi possível carregar as configurações iniciais da base de dados.")

except Exception as e:
    st.error(f"Erro no formulário: {e}")