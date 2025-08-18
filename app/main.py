import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

# ----- 설정 -----
load_dotenv()
KMA_SERVICE_KEY = os.getenv("KMA_SERVICE_KEY") or os.getenv("KMA_API_KEY") or ""
if not KMA_SERVICE_KEY:
    print("[경고] 환경변수 KMA_SERVICE_KEY가 비어있습니다. .env 또는 서버 환경변수로 설정하세요.")

KMA_BASE_URL = "https://apis.data.go.kr/1360000"
TZ_KST = timezone(timedelta(hours=9))

app = FastAPI(title="K-Weather (FastAPI)", version="1.0.0", description="기상청(공공데이터) 래핑 한국 날씨 API")


# ----- 위경도→기상청 격자 변환(Lambert Conformal Conic, 5km grid) -----
# 공식 매뉴얼에 나오는 상수값
import math
RE = 6371.00877  # 지구 반경(km)
GRID = 5.0       # 격자 간격(km)
SLAT1 = 30.0     # 표준위도1(deg)
SLAT2 = 60.0     # 표준위도2(deg)
OLON = 126.0     # 기준점 경도(deg)
OLAT = 38.0      # 기준점 위도(deg)
XO = 43          # 기준점 X좌표(GRID)
YO = 136         # 기준점 Y좌표(GRID)

def latlon_to_xy(lat: float, lon: float) -> Dict[str, int]:
    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * (math.cos(slat1) / sn)
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)
    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    x = (ra * math.sin(theta)) + XO + 0.5
    y = (ro - ra * math.cos(theta)) + YO + 0.5
    return {"nx": int(x), "ny": int(y)}


# ----- 공통: 기상청 요청 -----
async def kma_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{KMA_BASE_URL}/{path}"
    qp = {
        "serviceKey": KMA_SERVICE_KEY,
        "dataType": "JSON",
        **params,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=qp)
        r.raise_for_status()
        data = r.json()
    try:
        return data["response"]["body"]
    except Exception:
        raise HTTPException(status_code=502, detail=f"KMA 응답 형식이 예상과 다릅니다: {data}")


# ----- 코드 → 한글 매핑 -----
PTY_MAP = {
    "0": "없음",
    "1": "비",
    "2": "비/눈",
    "3": "눈",
    "4": "소나기",
    "5": "빗방울",
    "6": "빗방울/눈날림",
    "7": "눈날림",
}
SKY_MAP = {
    "1": "맑음",
    "3": "구름많음",
    "4": "흐림",
}

def choose_recent_base_for_ultra_ncst(now_kst: datetime) -> List[datetime]:
    # 초단기실황(getUltraSrtNcst)는 보통 매시 40분 전후부터 조회 가능이라고 알려져 있습니다.
    # 안전하게 최근 3시간의 정시(HH00)들을 최신순으로 시도합니다.
    candidates = []
    base = now_kst.replace(minute=0, second=0, microsecond=0)
    for i in range(0, 3):
        candidates.append(base - timedelta(hours=i))
    return candidates

def recent_base_for_vilage_fcst(now_kst: datetime) -> datetime:
    # 단기예보(getVilageFcst) 기준시각: 02,05,08,11,14,17,20,23
    slots = [2,5,8,11,14,17,20,23]
    base = now_kst.astimezone(TZ_KST)
    base = base.replace(minute=0, second=0, microsecond=0)
    hour = base.hour
    chosen = max([h for h in slots if h <= hour], default=23)
    if hour < min(slots):  # 새벽 0~1시는 전날 23시를 사용
        base = base - timedelta(days=1)
    return base.replace(hour=chosen)


# ----- 스키마 -----
class NowResponse(BaseModel):
    baseDate: str
    baseTime: str
    nx: int
    ny: int
    temperature: Optional[float] = None  # T1H (°C)
    humidity: Optional[int] = None       # REH (%)
    windSpeed: Optional[float] = None    # WSD (m/s)
    windDir: Optional[int] = None        # VEC (deg)
    sky: Optional[str] = None            # SKY(코드→문자)
    pty: Optional[str] = None            # PTY(코드→문자)
    rainfall1h: Optional[str] = None     # RN1 (mm)


class FcstItem(BaseModel):
    fcstDate: str
    fcstTime: str
    tmp: Optional[float] = None
    pop: Optional[int] = None
    pcp: Optional[str] = None
    sky: Optional[str] = None
    pty: Optional[str] = None


class ForecastResponse(BaseModel):
    baseDate: str
    baseTime: str
    nx: int
    ny: int
    items: List[FcstItem]


# ----- 헬스체크 -----
@app.get("/health")
async def health():
    return {"ok": True, "time_kst": datetime.now(TZ_KST).isoformat()}


# ----- 현재 날씨 (초단기실황) -----
@app.get("/weather/now", response_model=NowResponse)
async def weather_now(
    lat: float = Query(..., description="위도 (WGS84)"),
    lon: float = Query(..., description="경도 (WGS84)"),
):
    if not KMA_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="KMA_SERVICE_KEY가 설정되어 있지 않습니다.")
    grid = latlon_to_xy(lat, lon)
    now_kst = datetime.now(TZ_KST)
    # 최신 기준시각 여러 개 시도
    for base_dt in choose_recent_base_for_ultra_ncst(now_kst):
        base_date = base_dt.strftime("%Y%m%d")
        base_time = base_dt.strftime("%H%M")
        try:
            body = await kma_get(
                "VilageFcstInfoService_2.0/getUltraSrtNcst",
                {
                    "numOfRows": 200,
                    "pageNo": 1,
                    "base_date": base_date,
                    "base_time": base_time,
                    "nx": grid["nx"],
                    "ny": grid["ny"],
                },
            )
            items = body.get("items", {}).get("item", [])
            if not items:
                continue

            # 카테고리별 값 뽑기
            by_cat = {it["category"]: it["obsrValue"] for it in items if "category" in it}
            res = NowResponse(
                baseDate=body["items"]["item"][0]["baseDate"],
                baseTime=body["items"]["item"][0]["baseTime"],
                nx=grid["nx"],
                ny=grid["ny"],
                temperature=float(by_cat.get("T1H")) if by_cat.get("T1H") not in (None, " ") else None,
                humidity=int(by_cat.get("REH")) if by_cat.get("REH") not in (None, " ") else None,
                windSpeed=float(by_cat.get("WSD")) if by_cat.get("WSD") not in (None, " ") else None,
                windDir=int(by_cat.get("VEC")) if by_cat.get("VEC") not in (None, " ") else None,
                sky=SKY_MAP.get(str(by_cat.get("SKY"))) if by_cat.get("SKY") is not None else None,
                pty=PTY_MAP.get(str(by_cat.get("PTY"))) if by_cat.get("PTY") is not None else None,
                rainfall1h=by_cat.get("RN1"),
            )
            return res
        except Exception:
            # 다음 후보 기준시각 시도
            continue

    raise HTTPException(status_code=502, detail="기상청 초단기실황 최신 자료를 가져오지 못했습니다.")


# ----- 단기예보(3시간 간격, 몇 시간치) -----
@app.get("/weather/forecast", response_model=ForecastResponse)
async def weather_forecast(
    lat: float = Query(..., description="위도 (WGS84)"),
    lon: float = Query(..., description="경도 (WGS84)"),
    hours: int = Query(24, ge=3, le=72, description="가져올 시간 범위(시간)"),
):
    if not KMA_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="KMA_SERVICE_KEY가 설정되어 있지 않습니다.")
    grid = latlon_to_xy(lat, lon)
    now_kst = datetime.now(TZ_KST)
    base_dt = recent_base_for_vilage_fcst(now_kst)
    base_date = base_dt.strftime("%Y%m%d")
    base_time = base_dt.strftime("%H%M")

    body = await kma_get(
        "VilageFcstInfoService_2.0/getVilageFcst",
        {
            "numOfRows": 1000,
            "pageNo": 1,
            "base_date": base_date,
            "base_time": base_time,
            "nx": grid["nx"],
            "ny": grid["ny"],
        },
    )
    items = body.get("items", {}).get("item", [])
    if not items:
        raise HTTPException(status_code=502, detail="기상청 단기예보 자료가 비어있습니다.")

    # (fcstDate, fcstTime) 단위로 묶고 필요한 카테고리만 추려서 정리
    bucket: Dict[str, Dict[str, Any]] = {}
    want = {"TMP", "POP", "PCP", "SKY", "PTY"}  # 기온, 강수확률, 강수량, 하늘, 강수형태
    for it in items:
        if it.get("category") not in want:
            continue
        key = f"{it['fcstDate']}_{it['fcstTime']}"
        bucket.setdefault(key, {"fcstDate": it["fcstDate"], "fcstTime": it["fcstTime"]})
        bucket[key][it["category"]] = it["fcstValue"]

    # 시간 정렬 & 요청한 시간 범위로 제한
    def dt_of(k: str) -> datetime:
        d, t = k.split("_")
        return datetime.strptime(d + t, "%Y%m%d%H%M").replace(tzinfo=TZ_KST)

    ordered_keys = sorted(bucket.keys(), key=dt_of)
    end_time = now_kst + timedelta(hours=hours)
    trimmed: List[FcstItem] = []
    for k in ordered_keys:
        dtk = dt_of(k)
        if dtk < now_kst - timedelta(hours=1):
            continue
        if dtk > end_time:
            break
        row = bucket[k]
        trimmed.append(
            FcstItem(
                fcstDate=row["fcstDate"],
                fcstTime=row["fcstTime"],
                tmp=float(row["TMP"]) if row.get("TMP") not in (None, "", " ") else None,
                pop=int(row["POP"]) if row.get("POP") not in (None, "", " ") else None,
                pcp=row.get("PCP"),
                sky=SKY_MAP.get(str(row.get("SKY"))) if row.get("SKY") is not None else None,
                pty=PTY_MAP.get(str(row.get("PTY"))) if row.get("PTY") is not None else None,
            )
        )

    return ForecastResponse(
        baseDate=base_date,
        baseTime=base_time,
        nx=grid["nx"],
        ny=grid["ny"],
        items=trimmed,
    )


