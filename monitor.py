import os
import asyncio
import random
import urllib.parse
import psycopg2
from playwright.async_api import async_playwright
from telegram import Bot
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÕES ---
BASE_URL = "https://www.autoviacao1001.com.br/disponibilidade"

# PARAMS = {
#     "data_ida": "10022026",  # Formato DDMMAAAA
#     "origem_id": "14245",
#     "destino_id": "14199",
#     "num_psgr": "3",         # Adultos
#     "num_chda": "0",         # Crianças de colo? (verificar site)
#     "num_chds": "0",         # Crianças
#     # "deep": "true"
# }
# # Configuração da Faixa de Horário (Hora cheia)
# HORARIOS_ALVO = [22, 23, 0]

# Ambiente
DATABASE_URL = os.getenv("DATABASE_URL") # String de conexão do NeonDB
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- NOVA FUNÇÃO PARA CARREGAR CONFIG ---
def carregar_configuracao(cursor):
    sql = """
    SELECT travel_date, origin_id, destiny_id, adults, children, target_hours
    FROM search_config 
    WHERE id=1;
    """
    cursor.execute(sql)
    row = cursor.fetchone()
    
    if not row:
        raise Exception("Nenhuma configuração encontrada no banco (ID 1).")
    
    # Converte a string "23,0,1" em lista de inteiros [23, 0, 1]
    # horas_lista = [int(x.strip()) for x in row[4].split(',') if x.strip()]
    # raw_hours = row[6]
    raw_hours = row[5]
    
    if raw_hours:
        horas_lista = [int(h.strip()) for h in str(raw_hours).split(',') if h.strip().isdigit()]
    else:
        horas_lista = []
    
    config = {
        "params": {
            "data_ida": row[0],
            "origem_id": row[1],
            "destino_id": row[2],
            "num_psgr": str(row[3]),
            # "num_chda": str(row[4]),
            "num_chda": 0,
            # "num_chds": str(row[5]),
            "num_chds": str(row[4]),
            "deep": "true"
        },
        "horas_alvo": horas_lista
    }
    return config 

# def build_url():
def build_url(params):
    """Constrói a URL dinamicamente com os parâmetros."""
    # query_string = urllib.parse.urlencode(PARAMS)
    query_string = urllib.parse.urlencode(params)
    return f"{BASE_URL}?{query_string}" 
    
async def get_best_price(params, horas_alvo):
    url = build_url(params)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
                args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox'
                ]
            )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={'width': 1366, 'height': 768}
            )
        
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        
        print(f"Acessando {url}...")
        
        try:
            waitTime = random.randint(5000, 10000)
            
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            
            print(f"Aguardando {int(waitTime / 1000)}s para garantir o carregamento...")
            await page.wait_for_timeout(waitTime)
            
            print("Rolando a página até o fim para carregar todo o conteúdo...")
            for i in range(15):
                await page.mouse.wheel(0, 800)
                await page.wait_for_timeout(500)
                
            await page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"Erro de navegação... {e}")
            await browser.close()
            return None
        
        content = await page.content()
        await browser.close()

        return process_html_content(content, horas_alvo)

def extract_price_from_tag(container, label_attr, decimal_attr):
    """
    Função auxiliar para extrair preço dado os nomes dos atributos data-js.
    """
    labels = container.find_all('span', attrs={'data-js': label_attr})
    prices = []
    
    for label in labels:
        # Se o elemento estiver oculto (classe d-none), ignoramos
        # ou tentamos ler mesmo assim, pois as vezes o site apenas esconde visualmente
        # mas no caso da 1001, o preço Pix costuma estar visível quando ativo.
        
        parent = label.parent
        decimal = parent.find('span', attrs={'data-js': decimal_attr})
        
        if decimal:
            txt_int = label.get_text(strip=True).replace('.', '')
            txt_dec = decimal.get_text(strip=True).replace(',', '')
            
            # Validação básica para evitar converter vazio
            if txt_int and txt_dec:
                try:
                    val = float(f"{txt_int}.{txt_dec}")
                    prices.append(val)
                except ValueError:
                    continue
    return prices

def process_html_content(html_content, horas_alvo_int):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    precos_encontrados = []
        
    cards = soup.find_all('li', class_='list-companies-item')
    
    print(f"Encontrados {len(cards)} horários de viagens.")
    
    for card in cards:
        time_element = card.find('span', {'data-js': 'fromTime'})
        
        if not time_element:
            continue
        
        horario_texto = time_element.get_text(strip=True)
        
        try:
            hora_partida = int(horario_texto.split(':')[0])
        
            if hora_partida in horas_alvo_int:
                print(f"-> Analisando Card das {horario_texto} (Hora {hora_partida}h)...")
                
                prices_in_card = []
                prices_in_card.extend(extract_price_from_tag(card, 'priceLabel', 'decimalLabel'))                
                
                prices_in_card.extend(extract_price_from_tag(card, 'priceLabelPix', 'decimalLabelPix'))
                
                if prices_in_card:
                    min_price = min(prices_in_card)
                    print(f"   Preços neste horário: {prices_in_card}")
                    print(f"   Melhor oferta encontrada: R$ {min_price:.2f}")
                    precos_encontrados.append(min_price)
                else:
                    print("   Sem preços disponíveis (Esgotado ou Erro de Leitura).")
            
                # Busca todas as tags que tenham o atributo data-js="priceLabel"
                # labels_inteiro = card.find_all('span', attrs={'data-js': 'priceLabel'})
            
            # if not labels_inteiro:
            #     print(f"   Aviso: Nenhum preço encontrado dentro do card das {horario_texto} (pode estar esgotado).")
            #     continue
            
                # for label_int in labels_inteiro:
                    # O label decimal costuma ser irmão ou estar no mesmo pai
                    # Vamos buscar o pai desse preço inteiro para achar o decimal vizinho
                    # container_preco = label_int.parent                
                    # label_dec = container_preco.find('span', attrs={'data-js': 'decimalLabel'})
                
                    # if label_dec:
                    #     # Texto puro: "177" e ",74"
                    #     txt_int = label_int.get_text(strip=True).replace('.', '')
                    #     txt_dec = label_dec.get_text(strip=True).replace(',', '')
                
                    #     try:
                    #         preco_float = float(f"{txt_int}.{txt_dec}")
                    #         print(f"   Preço detectado: R$ {preco_float:.2f}")
                    #         precos_encontrados.append(preco_float)
                    #     except ValueError:
                    #         continue
        except ValueError:
            continue
                
    if not precos_encontrados:
        print(f"Nenhum preço disponível para os horários: {horas_alvo_int}")
        return None
        
    # menor_preco = min(precos_encontrados)
    # return menor_preco
    return min(precos_encontrados)

def get_last_price(cursor):
    # cursor.execute("SELECT price FROM price_history ORDER BY register_date DESC LIMIT 1;")
    cursor.execute("SELECT price FROM price_history WHERE id=1;")
    result = cursor.fetchone()
    return float(result[0]) if result and result[0] is not None else None

def save_price(cursor, conn, price):
    # cursor.execute("INSERT INTO price_history (price) VALUES (%s)", (price,))
    sql = """
    UPDATE price_history
    SET price = %s,
    register_date = CURRENT_TIMESTAMP
    WHERE id = 1;
    """
    cursor.execute(sql, (price,))
    conn.commit()

async def send_telegram_alert(price, old_price, link):
    bot = Bot(token=TELEGRAM_TOKEN)
    economia = ""
    if old_price:
        diff = old_price - price
        economia = f"\n📉 Economia de: R$ {diff:.2f}"
        
    # link = build_url()
    msg = (
        f"🚨 **BAIXOU O PREÇO!** 🚨\n\n"
        f"De: R$ {old_price:.2f}\n"
        f"Para: R$ {price:.2f}\n\n"
        f"{economia}\n\n"
        f"Corre para comprar: {link}"
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')

async def main():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada.")
        return

    # Conecta ao Banco
    print("Conectando ao banco de dados...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # 1. Carrega Configuração Dinâmica
        print("Lendo configurações do banco...")
        config = carregar_configuracao(cursor)
        params_busca = config['params']
        horas_alvo = config['horas_alvo']

        print("Analisando preços...")
    # 1. Pega preço atual no site
        # current_price = await get_best_price()
        current_price = await get_best_price(params_busca, horas_alvo)
    
        if current_price:
            print(f"Preço atual detectado: R$ {current_price:.2f}")
            # 2. Pega último preço no banco
            last_price = get_last_price(cursor)
            
            link = build_url(params_busca)
        
            # 3. Lógica de Comparação
            if last_price is None:
                print("Primeira execução. Salvando preço inicial.")
                save_price(cursor, conn, current_price)
        
            elif current_price < last_price:
                print("Preço caiu! Enviando alerta...")
                await send_telegram_alert(current_price, last_price, link)
                save_price(cursor, conn, current_price)
            
            elif current_price > last_price:
                print("Preço subiu. Atualizando registro.")
                save_price(cursor, conn, current_price)
            else:
                print("Preço se manteve.")
                # Opcional: Salvar mesmo se manteve para ter histórico de horário?
                # save_price(cursor, conn, current_price)
            
        else:
            print(f"Nenhum preço encontrado nos horários desejados ({horas_alvo}).")

        conn.close()
    except Exception as e:
        print(f"Erro geral... {e}")

if __name__ == "__main__":
    asyncio.run(main())