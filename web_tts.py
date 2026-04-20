import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment, silence, effects
from pydub.effects import speedup, normalize
import io
import time
import threading

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="AI TTS Pro - Studio Quality", layout="wide", page_icon="🎙️")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stTextArea textarea { font-size: 16px !important; color: #000; background-color: #fff !important; border-radius: 10px; }
    .stButton>button { width: 100%; border-radius: 10px; font-weight: bold; background: linear-gradient(45deg, #22c55e, #10b981); color: white; border: none; }
    </style>
""", unsafe_allow_html=True)

# --- 2. HÀM CHẠY ASYNC AN TOÀN ---
def run_async_safe(coro):
    result, exception = None, None
    def thread_target():
        nonlocal result, exception
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
        except Exception as e: exception = e
        finally: loop.close()
    t = threading.Thread(target=thread_target)
    t.start()
    t.join()
    if exception: raise exception
    return result

# --- 3. HÀM XỬ LÝ ÂM THANH CHỐNG RÈ ---
def process_high_quality_segment(seg, speed=1.0):
    """Xử lý phân đoạn âm thanh: Cắt lặng, Fade, Tốc độ và Chuẩn hóa"""
    # Cắt khoảng lặng rác
    start_trim = silence.detect_leading_silence(seg, silence_threshold=-50.0)
    end_trim = silence.detect_leading_silence(seg.reverse(), silence_threshold=-50.0)
    seg = seg[start_trim:len(seg)-end_trim]
    
    # Ép tần số mẫu về 44100Hz để đồng nhất
    seg = seg.set_frame_rate(44100).set_channels(1)
    
    # Xử lý tốc độ (nếu cần) - Dùng kỹ thuật crossfade để giảm rè khi speedup
    if speed > 1.0:
        seg = speedup(seg, playback_speed=speed, chunk_size=30, crossfade=15)
    
    # Thêm fade in/out cực ngắn (10ms) để tránh tiếng 'pụp' khi nối câu
    seg = seg.fade_in(10).fade_out(10)
    
    return seg

async def get_tts_data(text, voice):
    if not text.strip(): return None
    communicate = edge_tts.Communicate(text, voice)
    data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": data += chunk["data"]
    return data

# --- 4. GIAO DIỆN & LOGIC ---
if 'selected_voice' not in st.session_state:
    st.session_state.selected_voice = "vi-VN-HoaiMyNeural"

with st.sidebar:
    st.markdown("### ⚙️ Cấu hình")
    @st.cache_data
    def get_all_voices():
        async def fetch(): return await edge_tts.list_voices()
        return run_async_safe(fetch())
    voices = get_all_voices()
    lang = st.selectbox("🌐 Ngôn ngữ:", sorted(list(set([v['Locale'] for v in voices]))), index=0)
    
# ... (Phần UI chọn giọng giữ nguyên như code cũ của bạn) ...

input_text = st.text_area("Kịch bản:", height=300)
process_btn = st.button("🚀 BẮT ĐẦU LỒNG TIẾNG")

if process_btn and input_text:
    with st.status("🔮 Đang xử lý âm thanh chất lượng Studio...", expanded=True):
        try:
            is_srt = " --> " in input_text
            voice = st.session_state.selected_voice
            
            if not is_srt:
                res = run_async_safe(get_tts_data(input_text, voice))
                if res:
                    seg = AudioSegment.from_file(io.BytesIO(res), format="mp3")
                    seg = normalize(process_high_quality_segment(seg)) # Chuẩn hóa âm lượng
                    
                    buf = io.BytesIO()
                    seg.export(buf, format="mp3", bitrate="192k")
                    st.audio(buf.getvalue())
            else:
                subs = list(srt.parse(input_text))
                # Khởi tạo file silent với frame rate chuẩn
                final_audio = AudioSegment.silent(duration=int(subs[-1].end.total_seconds()*1000)+1000, frame_rate=44100)
                
                for sub in subs:
                    chunk = run_async_safe(get_tts_data(sub.content, voice))
                    if chunk:
                        seg = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
                        
                        # Tính toán tốc độ cần thiết
                        allowed_ms = (sub.end - sub.start).total_seconds() * 1000
                        actual_ms = len(seg)
                        speed_factor = max(1.0, actual_ms / allowed_ms) if actual_ms > allowed_ms else 1.0
                        
                        # Xử lý chất lượng cao
                        seg = process_high_quality_segment(seg, speed=speed_factor)
                        
                        start_ms = int(sub.start.total_seconds() * 1000)
                        final_audio = final_audio.overlay(seg, position=start_start_ms if 'start_start_ms' in locals() else start_ms)
                
                # BƯỚC QUAN TRỌNG: Chuẩn hóa toàn bộ file cuối cùng để chống rè
                final_audio = normalize(final_audio)
                
                buf = io.BytesIO()
                final_audio.export(buf, format="mp3", bitrate="192k")
                st.audio(buf.getvalue())
                st.download_button("📥 Tải Audio sạch", buf.getvalue(), "clean_audio.mp3", "audio/mpeg")

        except Exception as e:
            st.error(f"Lỗi: {e}")
