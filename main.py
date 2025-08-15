import requests

# OpenWeatherMap API 키 (회원가입 후 발급)
API_KEY = "YOUR_API_KEY"

def get_weather_by_coords(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric&lang=kr"
    response = requests.get(url)
    data = response.json()

    if response.status_code == 200:
        location = data["name"]
        weather = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        print(f"📍 {location}의 현재 날씨:")
        print(f"🌡 온도: {temp}°C")
        print(f"☁ 상태: {weather}")
    else:
        print("날씨 정보를 가져오는 데 실패했습니다:", data)

# 예시: 서울 위도, 경도
latitude = 37.5665
longitude = 126.9780
get_weather_by_coords(latitude, longitude)
