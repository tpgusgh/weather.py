from fastapi import FastAPI, HTTPException
import requests
from datetime import datetime

app = FastAPI()

# OpenWeatherMap API 키
API_KEY = "YOUR_API_KEY"

# 날씨 정보를 위도, 경도로 가져오는 함수
def get_weather(lat: float, lon: float):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric&lang=kr"
    response = requests.get(url)
    data = response.json()

    if response.status_code == 200:
        location = data.get("name", "알 수 없음")
        weather = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        return {
            "location": location,
            "temperature": temp,
            "weather": weather
        }
    else:
        raise HTTPException(status_code=response.status_code, detail=data)

# 날씨 API 엔드포인트
@app.get("/weather")
def weather_api(lat: float, lon: float):
    """
    위도(lat), 경도(lon)를 쿼리 파라미터로 받아 날씨 정보 반환
    예시: /weather?lat=37.5665&lon=126.9780
    """
    return get_weather(lat, lon)

# 현재 시간 API 엔드포인트
@app.get("/time")
def time_api():
    """
    현재 서버 시간을 반환
    """
    now = datetime.now()
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S")
    }
