import streamlit as st
import psycopg2
import os
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Monitor de Passagens", page_icon="🚌", layout="centered")

# Conexão com Banco
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url and "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
    
    return psycopg2.connect(db_url)

st.title("🚌 Controle do Monitor de Passagens")
st.markdown("---")
# Colunas para mostrar o Status Atual (Lendo tabela monitor_status)
col_status1, col_status2 = st.columns(2)

# # Formulário
# with st.form("config_form"):
#     st.write("### Parâmetros da Viagem")
    
#     col1, col2 = st.columns(2)
#     with col1:
#         data_input = st.text_input("Data (DDMMAAAA)", value="10022026")
#         origem = st.text_input("ID Origem", value="14245")
#     with col2:
#         adultos = st.number_input("Adultos", min_value=1, value=2)
#         criancas = st.number_input("Crianças (até 5 anos)", min_value=0, value=0)
#         adolescentes = 0
#         destino = st.text_input("ID Destino", value="14199")
    
#     st.write("### Filtro de Horário")
#     horas_txt = st.text_input("Horas de Partida (separar por vírgula)", value="22,23,0,1")
#     st.caption("Exemplo: Digite '23,0' para monitorar qualquer ônibus saindo às 23h ou 00h.")
    
#     submitted = st.form_submit_button("💾 Salvar Configuração")
    
#     if submitted:
#         try:
#             conn = get_db_connection()
#             cur = conn.cursor()
            
#             # Atualiza sempre o registro ID=1
#             query = """
#                 UPDATE search_config 
#                 SET travel_date=%s, origin_id=%s, destiny_id=%s, adults=%s, children=%s, teens=%s, target_hours=%s
#                 WHERE id=1;
#             """
#             cur.execute(query, (data_input, origem, destino, adultos, criancas, adolescentes, horas_txt))
#             conn.commit()
#             conn.close()
#             st.success("Configuração atualizada com sucesso! O robô usará esses dados na próxima rodada.")
#         except Exception as e:
#             st.error(f"Erro ao salvar: {e}")

# # Mostrar dados atuais
# st.divider()
# st.write("🔍 **Configuração Atual no Banco:**")
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT price, register_date FROM search_config WHERE id=1")
    status = cur.fetchone()
    # conn.close()
    
    if status:
        price = status[0]
        register_date = status[1].strftime("%d/%m/%Y %H:%M") if status[1] else "Nunca"
        
        with col_status1:
            st.metric("💰 Último Preço Encontrado", f"R$ {price:.2f}")
        with col_status2:
            st.metric("🕒 Última Atualização", register_date)
    else:
        st.warning("Ainda sem dados de monitoramento...")
    
    conn.close()
    
except Exception as e:
    st.error(f"Não ao conectar... {e}")

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
        # Cria o formulário
        with st.form("config_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                # O site pede DDMMAAAA, mantemos texto para evitar erros de conversão
                travel_date = st.text_input("Data da Viagem (DDMMAAAA)", value=config[0])
                origin_id = st.text_input("ID Origem", value=config[1])
                active_monitor = st.checkbox("Monitor Ativo?", value=config[7])
                
            with col2:
                # Horários alvo
                target_hours = st.text_input("Horas Alvo (separar por vírgula)", value=config[6], help="Ex: 22,23,0 para buscar ônibus saindo às 22h, 23h ou Meia-noite.")
                destiny_id = st.text_input("ID Destino", value=config[2])

            st.write("**Passageiros**")
            p_col1, p_col2, p_col3 = st.columns(3)
            with p_col1:
                adults = st.number_input("Adultos", min_value=1, value=config[3])
            with p_col2:
                children = st.number_input("Crianças", min_value=0, value=config[4])
            with p_col3:
                teens = st.number_input("Jovens/Outros", min_value=0, value=config[5])

            # Botão de Salvar
            submitted = st.form_submit_button("💾 Salvar Novas Regras")

            if submitted:
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
                    cur.execute(sql, (travel_date, origin_id, destiny_id, adults, children, teens, target_hours, active_monitor))
                    conn.commit()
                    conn.close()
                    st.success("✅ Configurações salvas! O robô usará esses dados na próxima hora.")
                    
                    # Recarrega a página para atualizar os dados visuais
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
    else:
        st.error("Não foi possível carregar as configurações iniciais do banco (ID 1 inexistente).")

except Exception as e:
    st.error(f"Erro no formulário: {e}")