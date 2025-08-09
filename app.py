import streamlit as st
import time
import csv
import requests
import subprocess
import re
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, SessionNotCreatedException
import undetected_chromedriver as uc
import io
import os

# Streamlit page configuration
st.set_page_config(page_title="Crypto Analysis App", layout="wide")

def get_chrome_version():
    """Get the current Chrome version"""
    try:
        result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            version_match = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', result.stdout)
            if version_match:
                return int(version_match.group(1))
    except:
        pass
    return 138  # Default fallback

def create_chrome_driver():
    chrome_version = get_chrome_version()
    st.write(f"🔍 Detected Chrome version: {chrome_version}")

    options = uc.ChromeOptions()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = uc.Chrome(options=options)
        st.write("✅ Chrome driver created successfully")
        return driver
    except Exception as e:
        st.error(f"❌ Error creating Chrome driver: {e}")
        raise e


def get_token_info_from_map(symbol, cmc_api_key):
    """Get contract address from CoinMarketCap API"""
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map"
    headers = {"X-CMC_PRO_API_KEY": cmc_api_key}
    response = requests.get(url, headers=headers).json()

    for item in response['data']:
        if item['symbol'].upper() == symbol.upper():
            token_address = item.get('platform', {}).get('token_address')
            platform_name = item.get('platform', {}).get('name')
            return {
                "id": item["id"],
                "name": item["name"],
                "symbol": item["symbol"],
                "platform": platform_name,
                "contract_address": token_address
            }
    return None

def get_token_holders(token_address, max_holders=100):
    """Scrape token holders from Etherscan - get exactly 100 top holders"""
    st.write(f"🔍 Scraping top {max_holders} token holders for contract: {token_address}")
    
    driver = create_chrome_driver()
    all_holders = []

    try:
        page = 1
        while len(all_holders) < max_holders:
            url = f"https://etherscan.io/token/generic-tokenholders2?a={token_address}&sid=&m=light&s=0&p={page}"
            driver.get(url)

            wait = WebDriverWait(driver, 30)
            st.write(f"[*] Processing page {page}...")

            wait.until(EC.presence_of_element_located((By.ID, "maintable")))
            st.write("[+] Page Loaded")

            time.sleep(2)

            rows = driver.find_elements(By.CSS_SELECTOR, "#maintable tbody tr")

            for row in rows:
                if len(all_holders) >= max_holders:
                    break
                    
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 5:
                    continue

                address_elem = cols[1].find_element(By.TAG_NAME, "a")
                href = address_elem.get_attribute("href")

                try:
                    contract_address = href.split("/token/")[1].split("?")[0]
                    wallet_address = href.split("a=")[-1]
                except IndexError:
                    contract_address = token_address
                    wallet_address = "unknown"

                rank = cols[0].text.strip()
                quantity = cols[2].text.strip()
                value = cols[4].text.strip()

                all_holders.append({
                    "Rank": rank,
                    "Contract Address": contract_address,
                    "Wallet Address": wallet_address,
                    "Quantity": quantity,
                    "Value": value
                })

            st.write(f"✅ Page {page} completed - Found {len(rows)} holders (Total: {len(all_holders)})")
            
            if len(rows) == 0:
                break
                
            page += 1

    except Exception as e:
        st.error(f"❌ Error occurred: {e}")
    finally:
        driver.quit()

    st.write(f"✅ Total holders collected: {len(all_holders)}")
    return all_holders

def fetch_30_day_balances(wallet_data, test_limit=100):
    """Get 30-day old balances for wallets (limit to test_limit for testing)"""
    st.write(f"📊 Getting 60-day balances for {min(len(wallet_data), test_limit)} wallets (testing mode)...")
    
    test_wallets = wallet_data[:test_limit]
    driver = create_chrome_driver()
    wait = WebDriverWait(driver, 15)
    balance_results = []
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    date_30_days_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    try:
        driver.get("https://etherscan.io/balancecheck-tool")
        st.write("🌐 Page loaded, waiting for elements...")
        time.sleep(5)

        for i, wallet_info in enumerate(test_wallets, 1):
            contract = wallet_info["Contract Address"]
            wallet = wallet_info["Wallet Address"]
            
            st.write(f"🔍 [{i}/{len(test_wallets)}] Checking balance for: {wallet}")

            try:
                dropdown = wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_ddlOptionType")))
                dropdown.click()
                token_option = driver.find_element(By.CSS_SELECTOR, "select#ContentPlaceHolder1_ddlOptionType > option[value='2']")
                token_option.click()
                time.sleep(1)

                wallet_input = wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_txtAddress")))
                wallet_input.clear()
                wallet_input.send_keys(wallet)

                contract_input = wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_txtTokenContractAddress")))
                contract_input.clear()
                contract_input.send_keys(contract)

                date_field = wait.until(EC.element_to_be_clickable((By.ID, "date")))
                driver.execute_script("arguments[0].removeAttribute('readonly')", date_field)
                date_30_days_ago_str = (datetime.now() - timedelta(days=60)).strftime("%m/%d/%Y")
                
                date_field.clear()
                driver.execute_script(f"arguments[0].value = '{date_30_days_ago_str}';", date_field)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", date_field)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", date_field)
                time.sleep(2)

                lookup_btn = wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_Button1")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", lookup_btn)
                time.sleep(2)
                
                try:
                    lookup_btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", lookup_btn)
                
                time.sleep(5)

                quantity = "N/A"
                try:
                    fs6_elements = driver.find_elements(By.CLASS_NAME, "fs-6")
                    for elem in fs6_elements:
                        text = elem.text.strip()
                        if text and any(char.isdigit() for char in text) and len(text) > 10:
                            quantity = text
                            st.write(f"✅ Balance found: {quantity}")
                            break
                    else:
                        st.write("⚠️ No balance found")
                except Exception as e:
                    st.error(f"❌ Error extracting balance: {e}")

                balance_results.append({
                    "Wallet Address": wallet,
                    date_30_days_ago: quantity
                })

            except Exception as e:
                st.error(f"❌ Error processing wallet {wallet}: {e}")
                balance_results.append({
                    "Wallet Address": wallet,
                    date_30_days_ago: "N/A"
                })

            time.sleep(3)
            driver.get("https://etherscan.io/balancecheck-tool")
            time.sleep(2)

    finally:
        driver.quit()

    return balance_results, current_date, date_30_days_ago

def compare_balances_and_analyze(holders_data, balance_data, current_date, date_30_days_ago):
    """Compare current vs 30-day balances and determine Buy/Sell/Hold with 5% threshold"""
    st.write("📈 Analyzing trading patterns with 5% threshold...")
    
    balance_lookup = {item["Wallet Address"]: item[date_30_days_ago] for item in balance_data}
    
    for holder in holders_data:
        wallet = holder["Wallet Address"]
        current_balance = holder["Quantity"]
        old_balance = balance_lookup.get(wallet, "N/A")
        
        action = "HOLD"
        if old_balance != "N/A" and current_balance != "N/A":
            try:
                current = float(current_balance.replace(",", ""))
                old = float(old_balance.replace(",", ""))
                
                if old > 0:
                    percentage_change = ((current - old) / old) * 100
                    if percentage_change >= 5:
                        action = "BUY"
                    elif percentage_change <= -5:
                        action = "SELL"
                    else:
                        action = "HOLD"
                else:
                    action = "HOLD"
            except:
                action = "HOLD"
        
        holder[current_date] = current_balance
        holder[date_30_days_ago] = old_balance
        holder["Action"] = action
        if "Quantity" in holder:
            del holder["Quantity"]
    
    return holders_data

def save_results_to_buffer(data, symbol):
    """Save results to a CSV buffer for download"""
    output = io.StringIO()
    fieldnames = ["Rank", "Contract Address", "Wallet Address", "Value", "Action"]
    date_columns = [col for col in data[0].keys() if col not in fieldnames and col != "Quantity"]
    fieldnames = fieldnames[:3] + date_columns + fieldnames[3:]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    
    return output.getvalue()

def analyze_single_coin(symbol, cmc_api_key):
    """Analyze a single coin"""
    st.write(f"\n{'='*50}")
    st.write(f"🚀 Starting analysis for {symbol}")
    st.write(f"{'='*50}")
    
    st.write(f"\n1️⃣ Getting contract address for {symbol}...")
    token_info = get_token_info_from_map(symbol, cmc_api_key)
    
    if not token_info:
        st.error(f"❌ Could not find token info for {symbol}")
        return None
    
    contract_address = token_info["contract_address"]
    st.write(f"✅ Contract address: {contract_address}")
    
    st.write(f"\n2️⃣ Scraping token holders for {symbol}...")
    holders_data = get_token_holders(contract_address, max_holders=100)
    
    if not holders_data:
        st.error(f"❌ No holders data found for {symbol}")
        return None
    
    st.write(f"✅ Found {len(holders_data)} token holders")
    
    st.write(f"\n3️⃣ Getting 30-day balances for {symbol}...")
    balance_data, current_date, date_30_days_ago = fetch_30_day_balances(holders_data, test_limit=100)
    
    st.write(f"\n4️⃣ Analyzing trading patterns for {symbol}...")
    final_data = compare_balances_and_analyze(holders_data, balance_data, current_date, date_30_days_ago)
    
    st.write(f"\n5️⃣ Preparing results for {symbol}...")
    csv_data = save_results_to_buffer(final_data, symbol)
    
    actions = [item["Action"] for item in final_data]
    buy_count = actions.count("BUY")
    sell_count = actions.count("SELL")
    hold_count = actions.count("HOLD")
    
    st.write(f"\n📊 Analysis Summary for {symbol}:")
    st.write(f"🟢 BUY: {buy_count}")
    st.write(f"🔴 SELL: {sell_count}")
    st.write(f"🟡 HOLD: {hold_count}")
    st.write(f"\n📅 Date Range: {date_30_days_ago} to {current_date}")
    
    return {
        "symbol": symbol,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "hold_count": hold_count,
        "total_holders": len(final_data),
        "csv_data": csv_data
    }

# Streamlit UI
st.title("🪙 Crypto Token Holder Analysis")
st.markdown("Enter coin symbols to analyze their top holders and trading patterns over the last 60 days.")

# Input for coin symbols
coin_input = st.text_input("Enter coin symbols (comma-separated, e.g., GALA,ETH,BTC):", "GALA")
cmc_api_key = "c3652959-4640-4c03-ae0d-7627bd3bfccb"  # Consider using st.secrets for production

if st.button("Analyze Coins"):
    if coin_input:
        coins = [coin.strip() for coin in coin_input.split(",")]
        results = []
        
        with st.spinner("Analyzing coins... This may take a while."):
            for coin in coins:
                try:
                    result = analyze_single_coin(coin, cmc_api_key)
                    if result:
                        results.append(result)
                except Exception as e:
                    st.error(f"❌ Error analyzing {coin}: {e}")
                    continue
        
        st.write(f"\n{'='*60}")
        st.write("📊 OVERALL ANALYSIS SUMMARY")
        st.write(f"{'='*60}")
        
        for result in results:
            st.write(f"\n{result['symbol']}:")
            st.write(f"  🟢 BUY: {result['buy_count']}")
            st.write(f"  🔴 SELL: {result['sell_count']}")
            st.write(f"  🟡 HOLD: {result['hold_count']}")
            st.write(f"  📊 Total Holders: {result['total_holders']}")
            
            # Provide download button for CSV
            st.download_button(
                label=f"Download {result['symbol']} Analysis CSV",
                data=result['csv_data'],
                file_name=f"{result['symbol']}_analysis.csv",
                mime="text/csv"
            )
        
        st.write(f"\n✅ Analysis complete for {len(results)} coins!")
    else:
        st.error("Please enter at least one coin symbol.")
