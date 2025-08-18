pip install fastapi uvicorn requests
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload


{
  "baseDate": "20250819",   // 기준 날짜 (YYYYMMDD) → 2025년 8월 19일
  "baseTime": "0800",       // 기준 시각 (HHMM) → 오전 8시 00분 발표 자료
  "nx": 60,                 // 기상청 격자 X 좌표 (서울 종로구 일대)
  "ny": 127,                // 기상청 격자 Y 좌표 (서울 종로구 일대)
  "temperature": 27.7,      // 기온 (℃)
  "humidity": 85,           // 상대습도 (%) → 공기 중 습기 정도
  "windSpeed": 3.2,         // 풍속 (m/s) → 초속 3.2m (약 11.5 km/h 바람)
  "windDir": 204,           // 풍향 (도, 0=북, 90=동, 180=남, 270=서)
  "sky": null,              // 하늘 상태 (맑음/구름많음/흐림), 초단기실황엔 제공 안 될 수 있음
  "pty": "없음",            // 강수 형태 (없음/비/눈/소나기 등)
  "rainfall1h": "0"         // 1시간 동안 누적 강수량 (mm) → 0이면 비가 안 옴
}
