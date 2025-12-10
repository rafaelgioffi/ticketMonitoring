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

PARAMS = {
    "data_ida": "10022026",  # Formato DDMMAAAA
    "origem_id": "14245",
    "destino_id": "14199",
    "num_psgr": "3",         # Adultos
    "num_chda": "0",         # Crianças de colo? (verificar site)
    "num_chds": "0",         # Crianças
    "deep": "true"
}
# Configuração da Faixa de Horário (Hora cheia)
HORARIOS_ALVO = ["23:00", "00:00", "00:15", "00:30", "01:00"]

# Ambiente
DATABASE_URL = os.getenv("DATABASE_URL") # String de conexão do NeonDB
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def build_url():
    """Constrói a URL dinamicamente com os parâmetros."""
    query_string = urllib.parse.urlencode(PARAMS)
    return f"{BASE_URL}?{query_string}" 
    
async def get_best_price():
    url = build_url()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, 
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
            waitTime = random.randint(10000, 20000)
            
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            
            print(f"Aguardando {waitTime / 1000}s para garantir o carregamento...")
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

        return process_html_content(content)

def process_html_content(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    precos_encontrados = []
        
    cards = soup.find_all('li', class_='list-companies-item')
    
    print(f"Encontrados {len(cards)} horários de viagens.")
    
    for card in cards:
        time_element = card.find('span', {'data-js': 'fromTime'})
        
        if not time_element:
            continue
        
        horario_texto = time_element.get_text(strip=True)
        
        if horario_texto in HORARIOS_ALVO:
            print(f"-> Analisando Card das {horario_texto}...")
            
            # Busca todas as tags que tenham o atributo data-js="priceLabel"
            labels_inteiro = card.find_all('span', attrs={'data-js': 'priceLabel'})
            
            if not labels_inteiro:
                print(f"   Aviso: Nenhum preço encontrado dentro do card das {horario_texto} (pode estar esgotado).")
                continue
            
            for label_int in labels_inteiro:
                # O label decimal costuma ser irmão ou estar no mesmo pai
                # Vamos buscar o pai desse preço inteiro para achar o decimal vizinho
                container_preco = label_int.parent
                
                label_dec = container_preco.find('span', attrs={'data-js': 'decimalLabel'})
                
                if label_dec:
                    # Texto puro: "177" e ",74"
                    txt_int = label_int.get_text(strip=True).replace('.', '')
                    txt_dec = label_dec.get_text(strip=True).replace(',', '')
                
                    try:
                        preco_float = float(f"{txt_int}.{txt_dec}")
                        print(f"   Preço detectado: R$ {preco_float:.2f}")
                        precos_encontrados.append(preco_float)
                    except ValueError:
                        continue
                
    if not precos_encontrados:
        print(f"Nenhum preço disponível para os horários: {HORARIOS_ALVO}")
        return None
        
    menor_preco = min(precos_encontrados)
    return menor_preco

def get_last_price(cursor):
    cursor.execute("SELECT price FROM price_history ORDER BY register_date DESC LIMIT 1;")
    result = cursor.fetchone()
    return float(result[0]) if result else None

def save_price(cursor, conn, price):
    cursor.execute("INSERT INTO price_history (price) VALUES (%s)", (price,))
    conn.commit()

async def send_telegram_alert(price, old_price):
    bot = Bot(token=TELEGRAM_TOKEN)
    link = build_url()
    msg = (
        f"🚨 **BAIXOU O PREÇO!** 🚨\n\n"
        f"De: R$ {old_price:.2f}\n"
        f"Para: R$ {price:.2f}\n\n"
        f"Corre para comprar: {link}"
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')

async def main():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada.")

    # Conecta ao Banco
    print("Conectando ao banco de dados...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        print("Analisando preços...")
    # 1. Pega preço atual no site
        current_price = await get_best_price()
    
        if current_price:
            print(f"Preço atual detectado: R$ {current_price}")
            # 2. Pega último preço no banco
            last_price = get_last_price(cursor)
        
            # 3. Lógica de Comparação
            if last_price is None:
                print("Primeira execução. Salvando preço inicial.")
                save_price(cursor, conn, current_price)
        
            elif current_price < last_price:
                print("Preço caiu! Enviando alerta...")
                await send_telegram_alert(current_price, last_price)
                save_price(cursor, conn, current_price)
            
            elif current_price > last_price:
                print("Preço subiu. Atualizando registro.")
                save_price(cursor, conn, current_price)
            else:
                print("Preço se manteve.")
                # Opcional: Salvar mesmo se manteve para ter histórico de horário?
                # save_price(cursor, conn, current_price)
            
        else:
            print(f"Nenhum preço encontrado nos horários desejados ({HORARIOS_ALVO}).")

        conn.close()
    except Exception as e:
        print(f"Erro geral... {e}")

if __name__ == "__main__":
    asyncio.run(main())
