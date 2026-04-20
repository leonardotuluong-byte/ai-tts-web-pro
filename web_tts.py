import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment, silence
from pydub.effects import speedup
import io
import time

# --- 1. CẤU HÌNH GIAO DIỆN CHUYÊN NGHIỆP ---
st.set_page_config(page_title="AI TTS Pro - Smooth Storytelling", layout="wide", page_icon="🎙️")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
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

# SỬA LỖI CRASH: TẠO HÀM CHẠY ASYNC AN TOÀN CHO STREAMLIT
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# --- 3. HÀM HỖ TRỢ XỬ LÝ ÂM THANH MƯỢT ---
def trim_audio_silence(audio_segment):
    """Cắt bỏ khoảng lặng 'rác' ở đầu và cuối do AI tạo ra"""
    start_trim = silence.detect_leading_silence(audio_segment, silence_threshold=-50.0)
    end_trim = silence.detect_leading_silence(audio_segment.reverse(), silence_threshold=-50.0)
    duration = len(audio_segment)
    return audio_segment[start_trim:duration-end_trim]

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
        except Exception as e:
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
        return run_async(fetch())

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

# --- 6. LOGIC XỬ LÝ VÀ CĂN CHỈNH TỐC ĐỘ MƯỢT ---
if process_btn:
    if not input_text:
        st.error("Vui lòng nhập kịch bản!")
    else:
        with st.status("🔮 Đang xử lý âm thanh mượt và khớp thời gian...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                voice = st.session_state.selected_voice
                
                # SỬA LỖI CRASH: Khởi tạo luồng xử lý đồng bộ 1 lần duy nhất
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                if not is_srt:
                    # Chế độ văn bản thường
                    res = loop.run_until_complete(run_tts_with_retry(input_text, voice))
                    if res:
                        st.audio(res, format="audio/mp3")
                        # SỬA LỖI ĐỊNH DẠNG: Đã thêm mime="audio/mpeg" và nút tải cho văn bản thường
                        st.download_button(
                            label="📥 Tải file hoàn chỉnh (.mp3)", 
                            data=res, 
                            file_name="audio_thuong.mp3", 
                            mime="audio/mpeg",
                            use_container_width=True
                        )
                else:
                    # CHẾ ĐỘ SRT - XỬ LÝ NỐI CÂU MƯỢT
                    subs = list(srt.parse(input_text))
                    total_ms = int(subs[-1].end.total_seconds() * 1000) + 2000
                    final_audio = AudioSegment.silent(duration=total_ms)
                    
                    last_end_ms = 0  
                    prog = st.progress(0)
                    
                    for i, sub in enumerate(subs):
                        chunk = loop.run_until_complete(run_tts_with_retry(sub.content, voice))
                        if chunk:
                            seg = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
                            seg = trim_audio_silence(seg)
                            
                            srt_start_ms = int(sub.start.total_seconds() * 1000)
                            duration_allowed_ms = (sub.end - sub.start).total_seconds() * 1000
                            
                            prev_text = subs[i-1].content.strip() if i > 0 else "."
                            is_continuous = not any(prev_text.endswith(p) for p in ['.', '!', '?', '。', '！', '？', ';', ':'])
                            
                            if is_continuous and last_end_ms > 0:
                                current_start = max(srt_start_ms, last_end_ms - 30)
                            else:
                                current_start = srt_start_ms

                            actual_duration_ms = len(seg)
                            if actual_duration_ms > duration_allowed_ms:
                                factor = actual_duration_ms / duration_allowed_ms
                                seg = speedup(seg, playback_speed=min(factor, 2.0))
                                seg = seg[:int(duration_allowed_ms)] 
                            
                            final_audio = final_audio.overlay(seg, position=current_start)
                            last_end_ms = current_start + len(seg)
                        
                        prog.progress((i + 1) / len(subs))
                        time.sleep(0.05)
                    
                    loop.close() # Đóng luồng an toàn
                    
                    buf = io.BytesIO()
                    final_audio.export(buf, format="mp3")
                    st.audio(buf.getvalue(), format="audio/mp3")
                    
                    # SỬA LỖI ĐỊNH DẠNG: Bổ sung mime="audio/mpeg" giúp trình duyệt nhận diện file MP3
                    st.download_button(
                        label="📥 Tải file hoàn chỉnh (Đã xử lý mượt)", 
                        data=buf.getvalue(), 
                        file_name="final_smooth_sync.mp3", 
                        mime="audio/mpeg",
                        use_container_width=True
                    )

                status.update(label="✅ Đã xử lý mượt và khớp thời gian!", state="complete")
            except Exception as e:
                st.error(f"Lỗi: {str(e)}")
