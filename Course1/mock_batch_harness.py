import concurrent.futures
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime


burp0_url = "https://accounts-api.apps.odibets.com:443/accounts-api/api/v1/auth/login"
burp0_headers = {"X-Link-Id": "cmYMzgDO1cDO3EjKxUTMqUWbvJHaDpCZp9mck5WQqETOsZTczMGOlVTOzU3ZqVTa4MHZ3EWbzDE=", "Sec-Ch-Ua-Platform": "\"Android\"", "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-A7160 Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/151.0.7922.85 Mobile Safari/537.36", "Accept": "application/json, text/plain, */*", "Sec-Ch-Ua": "\"Not=A?Brand\";v=\"99\", \"Android WebView\";v=\"151\", \"Chromium\";v=\"151\"", "Content-Type": "application/json", "Sec-Ch-Ua-Mobile": "?1", "Origin": "https://odibets.com", "X-Requested-With": "com.odibetsmini", "Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty", "Referer": "https://odibets.com/", "Accept-Encoding": "gzip, deflate, br", "Accept-Language": "en-US,en;q=0.9", "Priority": "u=1, i"}

json_payload1 = {"msisdn": "0701735557", "password": "fx@#098"}
resp1 = requests.post(burp0_url, headers=burp0_headers,json=json_payload1)
resp1.raise_for_status()
tt = resp1.json()
print(tt)