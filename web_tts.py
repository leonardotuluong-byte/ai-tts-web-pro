import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment
from pydub.effects import speedup
import io
import time

# --- 1. CẤU HÌNH GIAO DIỆN CHUYÊN NGHIỆP ---
st.set_page_config(page_title="AI TTS Pro - Auto Timing", layout="wide", page_icon="🎙️")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    /* Khung nhập liệu: Nền trắng, Chữ đen */
    .stTextArea textarea { 
        font-size: 16px !important; color: #000000 !important; 
        background-color: #ffffff !important; border-radius: 10px;
    }
    .voice-card {
        padding: 10px; border-radius: 8px; background-color: #1e293b;
        border: 1px solid #334155; margin-bottom: 8px; color: white;
    }
    .selected-voice { border: 2px solid #22c55e; background-color: #064e3b; }
    .stButton>button { 
        width: 100%; border-radius: 10px; font-weight: bold; height: 3.5em; 
        background: linear-gradient(45deg, #22c55e, #10b981); color: white; border: none;
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
        except:
            if attempt < retries - 1:
                time.sleep(1)
                continue
    return None

# --- 4. SIDEBAR SETTINGS ---
with st.sidebar:
    st.markdown("### ⚙️ Cấu hình")
    @st.cache_data
    def get_all_voices():
        async def fetch(): return await edge_tts.list_voices()
        return asyncio.run(fetch())

    voices = get_all_voices()
    locales = sorted(list(set([v['Locale'] for v in voices])))
    lang_filter = st.selectbox("🌐 Ngôn ngữ:", locales, index=locales.index("vi-VN") if "vi-VN" in locales else 0)
    gender_filter = st.radio("👤 Giới tính:", ["All", "Male", "Female"], horizontal=True)
    
    st.divider()
    st.markdown("💎 **Credits: 5,000**")

# --- 5. GIAO DIỆN CHÍNH ---
col_in, col_vo = st.columns([1.8, 1.2])

with col_in:
    st.markdown("### 📝 Kịch bản (Hỗ trợ SRT)")
    input_text = st.text_area("Dán nội dung vào đây (Chữ đen rõ ràng):", height=400)
    process_btn = st.button("🚀 BẮT ĐẦU LỒNG TIẾNG", type="primary", use_container_width=True)

with col_vo:
    st.markdown("### 🎙️ Danh sách giọng")
    v_list = [v for v in voices if v['Locale'] == lang_filter]
    if gender_filter != "All": v_list = [v for v in v_list if v['Gender'] == gender_filter]

    voice_container = st.container(height=380)
    with voice_container:
        for v in v_list:
            is_sel = st.session_state.selected_voice == v['ShortName']
            if st.button(f"{'✅' if is_sel else '👤'} {v['ShortName'].split('-')[-1]}", key=v['ShortName'], use_container_width=True):
                st.session_state.selected_voice = v['ShortName']
                st.rerun()

# --- 6. LOGIC XỬ LÝ VÀ CĂN CHỈNH TỐC ĐỘ ---
if process_btn:
    if not input_text:
        st.error("Vui lòng nhập kịch bản!")
    else:
        with st.status("🔮 Đang xử lý âm thanh và khớp thời gian...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                voice = st.session_state.selected_voice
                
                if not is_srt:
                    # Chế độ văn bản thường
                    res = asyncio.run(run_tts_with_retry(input_text, voice))
                    if res:
                        st.audio(res, format="audio/mp3")
                else:
                    # CHẾ ĐỘ SRT - CĂN CHỈNH TỐC ĐỘ (AUTO-TIMING)
                    subs = list(srt.parse(input_text))
                    total_ms = int(subs[-1].end.total_seconds() * 1000) + 1000
                    final_audio = AudioSegment.silent(duration=total_ms)
                    
                    prog = st.progress(0)
                    for i, sub in enumerate(subs):
                        chunk = asyncio.run(run_tts_with_retry(sub.content, voice))
                        if chunk:
                            # 1. Load âm thanh AI vừa tạo
                            seg = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
                            
                            # 2. Tính toán thời gian cho phép trong SRT
                            duration_allowed_ms = (sub.end - sub.start).total_seconds() * 1000
                            actual_duration_ms = len(seg)
                            
                            # 3. NẾU NÓI DÀI HƠN SUB: Tự động tăng tốc độ
                            if actual_duration_ms > duration_allowed_ms:
                                factor = actual_duration_ms / duration_allowed_ms
                                # Giới hạn speedup tối đa 2.0 để không bị quá méo tiếng
                                factor = min(factor, 2.0)
                                seg = speedup(seg, playback_speed=factor)
                                # Cắt bỏ phần thừa nếu vẫn còn dài hơn (để tuyệt đối không đè câu sau)
                                seg = seg[:duration_allowed_ms]
                            
                            # 4. Đặt vào đúng vị trí bắt đầu
                            start_ms = int(sub.start.total_seconds() * 1000)
                            final_audio = final_audio.overlay(seg, position=start_ms)
                        
                        prog.progress((i + 1) / len(subs))
                        time.sleep(0.1) # Độ trễ nhẹ tránh lỗi 503
                    
                    # Xuất kết quả cuối
                    buf = io.BytesIO()
                    final_audio.export(buf, format="mp3")
                    st.audio(buf.getvalue())
                    st.download_button("📥 Tải file hoàn chỉnh (Đã khớp thời gian)", buf.getvalue(), file_name="final_sync.mp3")

                status.update(label="✅ Đã khớp thời gian thành công!", state="complete")
            except Exception as e:
                st.error(f"Lỗi: {str(e)}")
