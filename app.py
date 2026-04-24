import streamlit as st
from supabase import create_client
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import random
from scipy import stats
import os

# 1. 초기 설정 및 DB 연결
st.set_page_config(page_title="미래 내 인생의 사건들 예상", layout="wide")

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except:
    st.error("데이터베이스 연결 설정(secrets.toml)을 확인해주세요.")

# 2. 8개 핵심 문항 정의
QUESTIONS = [
    "결혼 후 몇 년 이내에 이혼하게 됨",
    "40세 이전에 심장마비를 겪음",
    "직장에서 해고당함",
    "자동차 사고로 부상을 당함",
    "졸업 후 6개월 동안 직장을 구하지 못함",
    "잘못된 진로를 선택했다고 나중에 후회함",
    "강도나 노상강도의 피해자가 됨",
    "암에 걸림"
]

# 조사(이/가) 판별 함수
def get_josa(text):
    last_char = text[-1]
    if '가' <= last_char <= '힣':
        if (ord(last_char) - ord('가')) % 28 > 0:
            return "이"
        else:
            return "가"
    return "이"

# 3. 세션 초기화
if "logged_in" not in st.session_state:
    st.session_state.update({"logged_in": False, "user_type": None, "class_name": None, "step": 0, "responses": {}})

# 4. 로그인 화면
if not st.session_state.logged_in:
    st.title("미래 내 인생의 사건들 예상")
    user_type = st.radio("로그인", ["학생", "교수"])
    if user_type == "교수":
        pw = st.text_input("비밀번호", type="password")
        if pw == "3383" and st.button("로그인"):
            st.session_state.update({"logged_in": True, "user_type": "prof"})
            st.rerun()
    else:
        name = st.text_input("별명")
        if name and st.button("참여하기"):
            all_states = supabase.table("future_state").select("*").execute()
            available_classes = [r['class_name'] for r in all_states.data if r['current_state'] in ['standby', 'active']]
            
            if available_classes:
                active_class = available_classes[0]
                
                # 그룹 배정 로직 (A: 50%, B: 50%)
                current_logs = supabase.table("student_logs").select("id").eq("class_name", active_class).execute().data
                group = "Group_A" if len(current_logs) % 2 == 0 else "Group_B"
                
                st.session_state.update({
                    "logged_in": True, "user_type": "student", 
                    "student_name": name, "class_name": active_class, "group": group
                })
                supabase.table("student_logs").insert({"class_name": active_class, "student_name": name}).execute()
                st.rerun()
            else:
                st.warning("현재 열려 있는 수업이 없습니다.")

# 5. 교수 화면 (Admin Panel)
elif st.session_state.user_type == "prof":
    st.sidebar.title("관리자 패널")
    target_cls = st.sidebar.selectbox("수업 선택", ["인하대 행동재무학", "숙대 1", "숙대 2"])
    
    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("실험 대기"): 
        for c in ["인하대 행동재무학", "숙대 1", "숙대 2"]:
            state_val = "standby" if c == target_cls else "result"
            supabase.table("future_state").update({"current_state": state_val}).eq("class_name", c).execute()
    if c2.button("실험 시작"): 
        for c in ["인하대 행동재무학", "숙대 1", "숙대 2"]:
            state_val = "active" if c == target_cls else "result"
            supabase.table("future_state").update({"current_state": state_val}).eq("class_name", c).execute()
    if c3.button("결과 확인"): 
        supabase.table("future_state").update({"current_state": "result"}).eq("class_name", target_cls).execute()
    if c4.button("새로고침"): st.rerun()
    if c5.button("데이터 초기화"):
        supabase.table("future_results").delete().eq("class_name", target_cls).execute()
        supabase.table("student_logs").delete().eq("class_name", target_cls).execute()
        st.success(f"'{target_cls}' 데이터 초기화 완료.")
        st.rerun()

    # 로그인한 학생 수, 응답 제출한 학생 수 표시
    login_count = len(supabase.table("student_logs").select("student_name", count="exact").eq("class_name", target_cls).execute().data)
    res_data_count = supabase.table("future_results").select("student_name").eq("class_name", target_cls).execute().data
    df_count = pd.DataFrame(res_data_count)
    complete_count = len(df_count['student_name'].unique()) if not df_count.empty else 0
    
    st.sidebar.metric("로그인한 학생 수", f"{login_count}명")
    st.sidebar.metric("응답 완료 학생 수", f"{complete_count}명")

    st.header(f"📊 {target_cls} 실험 결과 분석")
    data = supabase.table("future_results").select("*").eq("class_name", target_cls).execute()
    df = pd.DataFrame(data.data)

    if not df.empty:
        avg_scores = df.groupby("group_type")["score"].mean()
        
        # 차트 제목 수정
        st.subheader("비교 대상에 따른 자기 우월평가 차이")
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ['#ff9999' if 'A' in g else '#66b3ff' for g in avg_scores.index]
        bars = ax.bar(avg_scores.index, avg_scores.values, color=colors)
        ax.set_ylabel("Average Bias Score (-10 to +10)")
        
        # 글자 겹침 방지를 위해 Y축 여백 확대
        ax.set_ylim(-12, 2)
        ax.axhline(0, color='black', linewidth=0.8)
        
        # 텍스트 위치 및 정렬 최적화
        for bar in bars:
            yval = bar.get_height()
            offset = -0.5 if yval < 0 else 0.5
            va = 'top' if yval < 0 else 'bottom'
            ax.text(bar.get_x() + bar.get_width()/2, yval + offset, f"{yval:.2f}", ha='center', va=va, fontweight='bold')
            
        st.pyplot(fig)
        
        # 이론적 배경 문구 수정
        st.info("💡 **이론적 배경:** Alicke et al.(1995)에 따르면, 비교 대상이 '평균적 대학생(Group A)'과 같이 추상적일 때보다 '얼굴 사진(Group B)'과 같이 개별화(Individuated)될 때 자기 우월평가 편향이 유의미하게 감소합니다. 즉 Group A의 평균 점수가 Group B의 평균 점수보다 작습니다.")

# 6. 학생 화면
else:
    state = supabase.table("future_state").select("*").eq("class_name", st.session_state.class_name).execute().data[0]
    st.title(f"📍 {st.session_state.class_name}")
    
    if state['current_state'] == "standby":
        st.info("교수님이 시작하실 때까지 대기하세요.")
        if st.button("새로고침"): st.rerun()
        
    elif state['current_state'] == "active":
        if st.session_state.step < 8:
            st.subheader(f"문항 {st.session_state.step + 1} / 8")
            
            # 동적 조사(이/가) 및 비교 문구 처리
            josa = get_josa(QUESTIONS[st.session_state.step])
            
            if st.session_state.group == "Group_A":
                st.markdown("### 비교 대상: **우리 학교의 평균적인 대학생**")
                compare_text = "대상과 비교해"
            else:
                st.markdown("### 비교 대상: **아래 사진 속의 학생**")
                compare_text = "이 학생과 비교해"
                if os.path.exists("front.jpg"):
                    st.image("front.jpg", width=350)
                else:
                    st.warning("정면 사진 파일(front.jpg)을 찾을 수 없습니다.")

            st.write(f"**질문: 귀하에게 '{QUESTIONS[st.session_state.step]}'{josa} 일어날 가능성은 {compare_text} 어느 정도입니까?**")
            score = st.select_slider("확률 선택", options=list(range(-10, 11)), value=0, key=f"q_{st.session_state.step}")
            st.caption("-10: 나에게 일어날 확률이 훨씬 낮음 | 0: 비슷함 | +10: 나에게 일어날 확률이 훨씬 높음")
            
            if st.button("다음"):
                supabase.table("future_results").insert({
                    "class_name": st.session_state.class_name,
                    "student_name": st.session_state.student_name,
                    "group_type": st.session_state.group,
                    "q_idx": st.session_state.step,
                    "score": score
                }).execute()
                st.session_state.step += 1
                st.rerun()
        else:
            st.success("🎉 모든 응답이 완료되었습니다. 교수님의 화면을 통해 집단 전체 결과를 확인해 보세요.")
    else:
        st.warning("실험이 종료되었습니다.")
