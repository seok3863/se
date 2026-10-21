
import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# 앱의 제목과 화면 배치를 설정합니다.
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

# API 주소에는 인증키를 넣지 않습니다.
API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 시간 기준으로 어제 날짜를 계산합니다.
# 배포 서버가 다른 시간대를 사용해도 한국 날짜를 기준으로 합니다.
KST = ZoneInfo("Asia/Seoul")
yesterday = (
    datetime.datetime.now(KST).date()
    - datetime.timedelta(days=1)
)
target_dt = yesterday.strftime("%Y%m%d")


@st.cache_data(ttl=3600)
def fetch_boxoffice(date_text, api_key):
    """KOBIS API에서 지정한 날짜의 영화 데이터를 가져옵니다."""
    response = requests.get(
        API_URL,
        params={
            "key": api_key,
            "targetDt": date_text,
        },
        timeout=20,
    )

    # HTTP 요청 자체가 실패한 경우 오류를 발생시킵니다.
    response.raise_for_status()

    # JSON 형식의 응답을 파이썬 자료형으로 변환합니다.
    return response.json()


# 앱 제목과 조회 날짜를 표시합니다.
st.title("🎬 어제의 박스오피스")
st.caption(
    f"조회 날짜: {yesterday:%Y년 %m월 %d일} "
    "(한국 시간 기준)"
)

# 인증키는 코드에 직접 적지 않고 Streamlit Secrets에서 읽습니다.
try:
    api_key = st.secrets["KOBIS_KEY"]
except Exception:
    st.error("KOBIS 인증키를 찾을 수 없습니다.")
    st.info(
        "Streamlit Cloud의 앱 설정에서 Settings → Secrets로 이동해 "
        'KOBIS_KEY = "발급받은_인증키" 형식으로 등록해 주세요.'
    )
    st.stop()

if not str(api_key).strip():
    st.error("KOBIS_KEY 값이 비어 있습니다.")
    st.info("Secrets에 유효한 인증키를 입력해 주세요.")
    st.stop()

# KOBIS API에 접속해 데이터를 가져옵니다.
try:
    data = fetch_boxoffice(target_dt, str(api_key).strip())

except requests.exceptions.Timeout:
    st.error("KOBIS 서버의 응답 시간이 초과되었습니다.")
    st.info("잠시 기다린 후 새로고침해 주세요.")
    st.stop()

except requests.exceptions.HTTPError as error:
    st.error(f"KOBIS 서버 HTTP 오류: {error}")
    st.info("API 주소와 KOBIS 서버 상태를 확인해 주세요.")
    st.stop()

except requests.exceptions.RequestException as error:
    st.error(f"KOBIS 서버에 연결하지 못했습니다: {error}")
    st.info("인터넷 연결과 API 주소를 확인해 주세요.")
    st.stop()

except ValueError:
    st.error("KOBIS 응답을 JSON으로 해석할 수 없습니다.")
    st.info("API 응답 형식과 서버 상태를 확인해 주세요.")
    st.stop()

# JSON 응답이 딕셔너리인지 확인합니다.
if not isinstance(data, dict):
    st.error("KOBIS에서 예상하지 못한 응답을 받았습니다.")
    st.info("KOBIS API 응답 형식을 확인해 주세요.")
    st.stop()

# 인증키가 틀리면 상태코드가 200이어도 faultInfo가 올 수 있습니다.
if "faultInfo" in data:
    fault = data.get("faultInfo") or {}
    message = fault.get("message", "상세 오류 메시지가 없습니다.")
    error_code = fault.get("errorCode", "코드 없음")

    st.error(
        f"KOBIS API 오류: {message} "
        f"(오류 코드: {error_code})"
    )
    st.info(
        "Settings → Secrets에서 KOBIS_KEY가 정확한지 확인하세요. "
        "인증키가 유효하고 사용 가능한 상태인지도 확인해 주세요."
    )
    st.stop()

# 응답에서 박스오피스 결과와 영화 목록을 가져옵니다.
boxoffice_result = data.get("boxOfficeResult")

if not isinstance(boxoffice_result, dict):
    st.error("박스오피스 결과를 찾을 수 없습니다.")
    st.info("KOBIS API 응답 구조를 확인해 주세요.")
    st.stop()

movies = boxoffice_result.get("dailyBoxOfficeList") or []

# 영화 목록이 없으면 빈 화면 대신 안내 메시지를 보여줍니다.
if not movies:
    st.warning("해당 날짜의 영화 목록이 비어 있습니다.")
    st.info(
        "KOBIS의 해당 날짜 집계가 완료되었는지 확인해 주세요. "
        "조회 날짜와 인증키, API 응답도 확인해 주세요."
    )
    st.stop()

# 영화 목록을 표와 그래프에 사용할 데이터프레임으로 변환합니다.
df = pd.DataFrame(movies)

# API의 숫자 값은 문자열이므로 숫자로 변환합니다.
number_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]

for column in number_columns:
    if column not in df.columns:
        df[column] = 0

    df[column] = (
        pd.to_numeric(df[column], errors="coerce")
        .fillna(0)
        .astype(int)
    )

# 필요한 문자 열이 없더라도 오류가 나지 않도록 처리합니다.
for column in ["movieNm", "openDt"]:
    if column not in df.columns:
        df[column] = ""

# 순위 순서대로 정렬합니다.
df = df.sort_values("rank").reset_index(drop=True)

# 1위 영화 정보를 가져옵니다.
top_movie = df.iloc[0]

st.subheader(f"🏆 1위 영화: {top_movie['movieNm']}")

# 첫 번째 영화의 주요 지표 세 가지를 카드로 표시합니다.
card1, card2, card3 = st.columns(3)

card1.metric(
    label="어제 관객수",
    value=f"{top_movie['audiCnt']:,}명",
)

card2.metric(
    label="누적 관객수",
    value=f"{top_movie['audiAcc']:,}명",
)

card3.metric(
    label="스크린수",
    value=f"{top_movie['scrnCnt']:,}개",
)

# 전체 영화의 순위표를 만듭니다.
st.subheader("📋 일일 박스오피스 순위표")

table = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()

# 열 이름을 한국어로 바꿉니다.
table.columns = [
    "순위",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]

# 큰 숫자를 읽기 쉽게 천 단위 쉼표로 표시합니다.
for column in ["관객수", "누적관객", "스크린수"]:
    table[column] = table[column].map(lambda value: f"{value:,}")

st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
)

# 어제 관객수 기준 상위 5편을 뽑습니다.
st.subheader("📊 관객수 상위 5편")

top5 = df.nlargest(5, "audiCnt").copy()
top5["관객수(명)"] = top5["audiCnt"]

# 가로 막대그래프에서 관객수가 적은 영화부터 표시합니다.
top5 = top5.sort_values("audiCnt", ascending=True)

fig = px.bar(
    top5,
    x="관객수(명)",
    y="movieNm",
    orientation="h",
    text="관객수(명)",
    labels={
        "movieNm": "영화명",
        "관객수(명)": "어제 관객수",
    },
)

# 막대 끝에 관객수를 표시합니다.
fig.update_traces(
    texttemplate="%{text:,}명",
    textposition="outside",
    cliponaxis=False,
)

fig.update_layout(
    xaxis_title="어제 관객수",
    yaxis_title="영화명",
    margin=dict(l=10, r=70, t=20, b=10),
)

st.plotly_chart(fig, use_container_width=True)

# 데이터 출처를 표시합니다.
st.caption(
    "자료 출처: 영화진흥위원회(KOBIS) "
    "일일 박스오피스 Open API"
)
