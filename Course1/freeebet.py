import requests

burp0_url = "https://odibets.com:443/pxy2/streaks"
burp0_cookies = {"odibetskenya": "0bbjhk7vtmlnc2aagcalsumm84"}
burp0_headers = {"Sec-Ch-Ua-Platform": "\"Windows\"",
                  "Authorization": "Bearer eyJraWQiOiJpZHAtZWJiNGUzYjctMzhiMy00MTBjLWE2MTctZGRlN2NhYTMzNGUxIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiIyMjk2NDgxOSIsInRva2VuX3VzZSI6ImFjY2VzcyIsInVzZXJfbmFtZSI6IlNoYWRyYWNrIiwicHJvZmlsZV9pZCI6MjI5NjQ4MTksInNjb3BlIjoiYXBpLnJlYWQiLCJyb2xlcyI6WyJVU0VSIl0sImlzcyI6Imh0dHBzOi8vYWNjb3VudHMtYXBpLmFwcHMub2RpYmV0cy5jb20iLCJleHAiOjE3ODkyMzg5NjgsIm1zaXNkbiI6IjI1NDcxMDE1NjYyNSIsImlhdCI6MTc4OTIzNTM2OCwianRpIjoiNDRkNGYyMWYtNzM5Ny00MTA5LWIxOTItNjY3ZmU1Zjk2MTliIiwic2lkIjoiODBhN2RmMzktZTA3Yi00ZTNmLTgyNWQtOGE1ODIyYzc0Mjg5In0.jF6AOZI2qxpzSfwdYXeHE_t_eqS3mnjbXX-2shGXZL8E3_wVj8evKuPqzMO_NsvKST_mj9Pvqvzj78_5ixg-iWw7WWg2oil9W-uGkqy8TQWqAi3cC1kQ6snztfO01tVN6CU_KVqAcYQyX_ffqppaHCHVjcf098hiKoLlSXDclFOlcpT5U1dtZPsYiKi6M5vrOzvTUWqHx8W3gdrOSDGyg-IH9FCEHgM2yB96MPWQEOLCk7aGrNLO35tvjq9zxTYtrF96iY0VAdm8oJspyAj1W375B1xzU1_YDqGy5Has3kEXMNzW9uhH1U5QZzt3rq2QtfvZZAomOgcDFyTBPcuIsA",
                    "Accept-Language": "en-US,en;q=0.9",
                      "Accept": "application/json, text/plain, */*",
                        "Sec-Ch-Ua": "\"Chromium\";v=\"151\", \"Not=A?Brand\";v=\"99\"",
                          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
                            "Sec-Ch-Ua-Mobile": "?0",
                              "Sec-Fetch-Site": "same-origin",
                                "Sec-Fetch-Mode": "cors", 
                                "Sec-Fetch-Dest": "empty", "Referer": "https://odibets.com/account", "Accept-Encoding": "gzip, deflate, br", "Priority": "u=1, i"}
resp1=requests.get(burp0_url, headers=burp0_headers, cookies=burp0_cookies)
mm = resp1.json()

if mm.get("error_code"):
    print("yess")
# Soft sleep window on specific hit limiters
else:
    bl = mm["data"]["current_streak"]
    #gh= bl.get("current_streak")
    print(bl)
