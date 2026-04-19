import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment
import io
import time

# --- 1. CẤU HÌNH GIAO DIỆN CHUYÊN NGHIỆP ---
st.set_page_config(page_title="AI TTS Pro Dashboard", layout="wide", page_icon="🎙️")

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    /* Voice Card Style */
    .voice-card {
        padding: 10px; border-radius: 8px; background-color: #ffffff;
        border: 1px solid #e2e8f0; margin-bottom: 8px; transition: all 0.2s;
    }
    .selected-voice { border: 2px solid #3b82f6; background-color: #eff6ff; }
    /* Khung nhập liệu: Nền trắng, Chữ đen rõ ràng */
    .stTextArea textarea { 
        font-size: 16px !important; color: #000000 !important; 
        background-color: #ffffff !important; border: 1px solid #cbd5e1;
    }
    .credit-badge {
        padding: 5px 12px; border-radius: 15px; background: #3b82f6;
        color: white; font-weight: bold; font-size: 14px; margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. KHỞI TẠO TRẠNG THÁI ---
if 'selected_voice' not in st.session_state:
    st.session_state.selected_voice = "vi-VN-HoaiMyNeural"

# --- 3. HÀM XỬ LÝ TTS CHỐNG CHẶN (ANTI-503) ---
async def run_tts_with_retry(text, voice_code, retries=3):
    if not text.strip(): return None
    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(text, voice_code)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            if audio_data: return audio_data
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1)) # Nghỉ tăng dần nếu bị chặn
                continue
    return None

# --- 4. SIDEBAR (BỘ LỌC) ---
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.markdown('<div class="credit-badge">💎 Credits: 5,000</div>', unsafe_allow_html=True)
    
    @st.cache_data
    def get_all_voices():
        async def fetch(): return await edge_tts.list_voices()
        return asyncio.run(fetch())

    voices = get_all_voices()
    locales = sorted(list(set([v['Locale'] for v in voices])))
    lang_filter = st.selectbox("🌐 Ngôn ngữ:", locales, index=locales.index("vi-VN") if "vi-VN" in locales else 0)
    gender_filter = st.radio("👤 Giới tính:", ["All", "Male", "Female"], horizontal=True)
    search_q = st.text_input("🔍 Tìm tên giọng:", placeholder="VD: HoaiMy...")

# --- 5. GIAO DIỆN CHÍNH ---
col_in, col_vo = st.columns([1.8, 1.2])

with col_in:
    st.markdown("### 📝 Nội dung kịch bản")
    input_text = st.text_area("Hỗ trợ Văn bản hoặc SRT (Màu chữ đen rõ ràng):", height=400, placeholder="Dán nội dung phim...")
    # ĐỊNH NGHĨA NÚT BẤM (Fix lỗi NameError)
    process_btn = st.button("🚀 BẮT ĐẦU CHUYỂN ĐỔI (TRỪ CREDIT)", type="primary", use_container_width=True)

with col_vo:
    st.markdown("### 🎙️ Chọn Giọng Đọc")
    v_list = [v for v in voices if v['Locale'] == lang_filter]
    if gender_filter != "All": v_list = [v for v in v_list if v['Gender'] == gender_filter]
    if search_q: v_list = [v for v in v_list if search_q.lower() in v['ShortName'].lower()]

    voice_container = st.container(height=380)
    with voice_container:
        for v in v_list:
            is_sel = st.session_state.selected_voice == v['ShortName']
            if st.button(f"{'✅' if is_sel else '👤'} {v['ShortName'].split('-')[-1]}", key=v['ShortName'], use_container_width=True):
                st.session_state.selected_voice = v['ShortName']
                st.rerun()

# --- 6. XỬ LÝ KHI NHẤN NÚT ---
if process_btn:
    if not input_text:
        st.error("Vui lòng nhập kịch bản!")
    else:
        with st.status("🔮 Đang xử lý âm thanh chất lượng cao...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                voice = st.session_state.selected_voice
                
                if not is_srt:
                    # Chế độ văn bản
                    res = asyncio.run(run_tts_with_retry(input_text, voice))
                    if res:
                        st.audio(res, format="audio/mp3")
                        st.download_button("📥 Tải MP3", res, file_name="ai_voice.mp3")
                else:
                    # Chế độ SRT chuẩn
                    subs = list(srt.parse(input_text))
                    total_ms = int(subs[-1].end.total_seconds() * 1000) + 2000
                    final_audio = AudioSegment.silent(duration=total_ms)
                    
                    prog = st.progress(0)
                    for i, sub in enumerate(subs):
                        # Xử lý từng dòng với Retry
                        chunk = asyncio.run(run_tts_with_retry(sub.content, voice))
                        if chunk:
                            seg = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
                            start_ms = int(sub.start.total_seconds() * 1000)
                            final_audio = final_audio.overlay(seg, position=start_ms)
                        
                        prog.progress((i + 1) / len(subs))
                        time.sleep(0.4) # Độ trễ an toàn chống 503
                    
                    # Xuất kết quả
                    buf = io.BytesIO()
                    final_audio.export(buf, format="mp3")
                    st.audio(buf.getvalue())
                    st.download_button("📥 Tải Audio hoàn chỉnh", buf.getvalue(), file_name="dub_final.mp3")

                status.update(label="✅ Đã xử lý xong!", state="complete")
            except Exception as e:
                st.error(f"Lỗi hệ thống: {str(e)}")
