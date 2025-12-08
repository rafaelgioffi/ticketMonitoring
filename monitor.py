import os
import asyncio
import re
import psycopg2
from playwright.async_api import async_playwright
from telegram import Bot

# --- CONFIGURAÇÕES ---
URL_ALVO = "https://www.autoviacao1001.com.br/disponibilidade?data_ida=10022026&origem_id=14245&destino_id=14199&num_psgr=2&num_chda=0&num_chds=1&deep=false"
DATABASE_URL = os.getenv("DATABASE_URL") # String de conexão do NeonDB
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Configuração da Faixa de Horário (Hora cheia)
HORA_INICIO = 23 # 23:00
HORA_FIM = 0     # 00:00 (Meia noite)

async def get_current_price():
    async with async_playwright() as p:
        # Lança um browser headless (sem interface gráfica)
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Acessando o site...")
        await page.goto(URL_ALVO, timeout=60000)
        
        # Espera o seletor de preço aparecer. 
        # NOTA: O seletor abaixo (class) é um exemplo comum. 
        # Você precisará Inspecionar Elemento no site da 1001 para pegar a classe exata do preço (ex: .seat-price, .value, etc).
        # Vamos assumir uma busca genérica pelo símbolo de moeda se a classe mudar muito.
        try:
            # Tenta esperar por algo que pareça um preço
            await page.wait_for_selector("text=R$", timeout=20000)
            
            # Pega todo o texto da página para filtrar preços (método bruto mas eficaz se as classes mudam)
            content = await page.content()
            
            # Regex para achar preços no formato R$ 123,45
            precos = re.findall(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', content)
            
            if not precos:
                print("Nenhum preço encontrado.")
                return None
            
            # Converte para float (Brasil usa vírgula, Python usa ponto)
            valores_float = [float(p.replace('.', '').replace(',', '.')) for p in precos]
            
            # Assume que o menor preço encontrado na página é o da passagem desejada
            menor_preco = min(valores_float)
            return menor_preco
            
        except Exception as e:
            print(f"Erro ao capturar preço: {e}")
            return None
        finally:
            await browser.close()

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