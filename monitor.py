import os
import asyncio
import re
import random
import urllib.parse
import psycopg2
from playwright.async_api import async_playwright
from telegram import Bot

# --- CONFIGURAÇÕES ---
BASE_URL = "https://www.autoviacao1001.com.br/disponibilidade"

PARAMS = {
    "data_ida": "10022026",  # Formato DDMMAAAA
    "origem_id": "14245",
    "destino_id": "14199",
    "num_psgr": "2",         # Adultos
    "num_chda": "0",         # Crianças de colo? (verificar site)
    "num_chds": "1",         # Crianças
    "deep": "false"
}
#URL_ALVO = "https://www.autoviacao1001.com.br/disponibilidade?data_ida=10022026&origem_id=14245&destino_id=14199&num_psgr=2&num_chda=0&num_chds=1&deep=false"

# Configuração da Faixa de Horário (Hora cheia)
HORA_INICIO = 23 # 23:00
HORA_FIM = 1     # 01:00

# Ambiente
DATABASE_URL = os.getenv("DATABASE_URL") # String de conexão do NeonDB
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def build_url():
    """Constrói a URL dinamicamente com os parâmetros."""
    query_string = urllib.parse.urlencode(PARAMS)
    return f"{BASE_URL}?{query_string}" 
    
async def get_best_price_in_range():
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
            viewport={'width': 1280, 'height': 720}
            )
        
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        
        print(f"Acessando {url}...")
        
        try:        
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(3000, 5000))
            # Tenta esperar por algo que pareça um preço
            await page.wait_for_selector("text=R$", timeout=30000)
            
        except Exception as e:
            print(f"Erro ao capturar preço: {e}")
            await browser.close()
            return None
        
        content = await page.content()
        await browser.close()

        return process_html_content(content)

def process_html_content(html_content):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    precos_encontrados = []
    
    # Busca textual bruta para evitar quebra com CSS dinâmico
    text = soup.get_text(" | ", strip=True)
    parts = text.split("|")
    
    last_seen_hour = -1
    time_pattern = re.compile(r'(\d{2}):(\d{2})')
    
    for part in parts:
        # Tenta achar horário
        match_time = time_pattern.search(part)
        if match_time:
            last_seen_hour = int(match_time.group(1))

        # Tenta achar preço associado ao último horário visto
        if "R$" in part and last_seen_hour != -1:
            price_str = re.search(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', part)
            if price_str:
                valor = float(price_str.group(1).replace('.', '').replace(',', '.'))
                
                # Valida horário (23h ou 00h)
                if last_seen_hour == HORA_INICIO or last_seen_hour == HORA_FIM:
                    print(f"Válido: {last_seen_hour}h -> R$ {valor}")
                    precos_encontrados.append(valor)
    
    if not precos_encontrados:
        return None
        
    return min(precos_encontrados)

def get_last_price(cursor):
    cursor.execute("SELECT valor FROM historico_precos ORDER BY data_registro DESC LIMIT 1;")
    result = cursor.fetchone()
    return float(result[0]) if result else None

def save_price(cursor, conn, price):
    cursor.execute("INSERT INTO historico_precos (valor) VALUES (%s)", (price,))
    conn.commit()

async def send_telegram_alert(price, old_price):
    bot = Bot(token=TELEGRAM_TOKEN)
    msg = (
        f"🚨 **BAIXOU O PREÇO!** 🚨\n\n"
        f"De: R$ {old_price:.2f}\n"
        f"Para: R$ {price:.2f}\n\n"
        f"Corre para comprar: {URL_ALVO}"
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')

async def main():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada.")

    # Conecta ao Banco
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # 1. Pega preço atual no site
    current_price = await get_current_price()
    
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

    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
