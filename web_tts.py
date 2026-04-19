import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment
import io
import time

# --- CẤU HÌNH GIAO DIỆN CHUYÊN NGHIỆP ---
st.set_page_config(page_title="Pro Voice - AI TTS Dashboard", layout="wide", page_icon="🎙️")

# CSS Tùy chỉnh phong cách Luvvoice
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }
    
    .stApp { background-color: #f8fafc; }
    
    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    
    /* Voice Card Style */
    .voice-card {
        padding: 15px;
        border-radius: 12px;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        margin-bottom: 10px;
        transition: all 0.3s ease;
        cursor: pointer;
    }
    .voice-card:hover { border-color: #3b82f6; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
    .selected-voice { border: 2px solid #3b82f6; background-color: #eff6ff; }
    
    /* Input Area */
    .stTextArea textarea { 
        border-radius: 12px; border: 1px solid #e2e8f0; font-size: 15px !important; 
        background-color: #ffffff !important; color: #1e293b !important;
    }
    
    /* Credit Badge */
    .credit-badge {
        padding: 8px 15px; border-radius: 20px;
        background: linear-gradient(90deg, #3b82f6, #2563eb);
        color: white; font-weight: bold; font-size: 14px;
        margin-bottom: 20px; display: inline-block;
    }
    </style>
""", unsafe_allow_html=True)

# --- KHỞI TẠO DỮ LIỆU ---
if 'selected_voice' not in st.session_state:
    st.session_state.selected_voice = "vi-VN-HoaiMyNeural"
if 'user_credits' not in st.session_state:
    st.session_state.user_credits = 5000 # Giả lập 5000 credits cho kinh doanh

# --- SIDEBAR: BỘ LỌC CHUYÊN NGHIỆP ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/8002/8002150.png", width=80)
    st.title("Settings")
    
    st.markdown(f'<div class="credit-badge">💎 Credits: {st.session_state.user_credits:,}</div>', unsafe_allow_html=True)
    
    @st.cache_data
    def get_all_voices():
        async def fetch(): return await edge_tts.list_voices()
        return asyncio.run(fetch())

    try:
        all_voices = get_all_voices()
        locales = sorted(list(set([v['Locale'] for v in all_voices])))
        
        # Chọn Quốc gia với Emoji cờ (Tạm thời dùng mã vùng)
        lang_filter = st.selectbox("🌐 Ngôn ngữ:", locales, index=locales.index("vi-VN") if "vi-VN" in locales else 0)
        
        gender_filter = st.radio("👤 Giới tính:", ["All", "Male", "Female"], horizontal=True)
        
        search_q = st.text_input("🔍 Tìm tên giọng:", placeholder="VD: HoaiMy...")
        
        st.divider()
        st.caption("Pro Voice v2.5 - Business Edition")
    except Exception as e:
        st.error("Không thể tải giọng đọc.")

# --- KHU VỰC CHÍNH ---
col_input, col_voices = st.columns([1.8, 1.2])

with col_input:
    st.markdown("### 📝 Nội dung kịch bản")
    input_text = st.text_area("Hỗ trợ văn bản thuần hoặc file SRT chuẩn:", height=450, 
                             placeholder="Dán kịch bản phim của bạn vào đây...")
    
    process_btn = st.button("🚀 BẮT ĐẦU CHUYỂN ĐỔI (TRỪ CREDIT)", type="primary", use_container_width=True)

with col_voices:
    st.markdown("### 🎙️ Chọn Giọng Đọc")
    
    # Lọc danh sách giọng
    filtered_voices = [v for v in all_voices if v['Locale'] == lang_filter]
    if gender_filter != "All":
        filtered_voices = [v for v in filtered_voices if v['Gender'] == gender_filter]
    if search_q:
        filtered_voices = [v for v in filtered_voices if search_q.lower() in v['ShortName'].lower()]

    # Hiển thị danh sách Voice theo kiểu Card
    voice_container = st.container(height=420)
    with voice_container:
        for v in filtered_voices:
            is_selected = st.session_state.selected_voice == v['ShortName']
            card_class = "voice-card selected-voice" if is_selected else "voice-card"
            
            # Dùng button ẩn để chọn giọng
            if st.button(f"{'✅' if is_selected else '👤'} {v['ShortName'].split('-')[-1]} ({v['Gender']})", 
                         key=v['ShortName'], use_container_width=True):
                st.session_state.selected_voice = v['ShortName']
                st.rerun()

# --- XỬ LÝ TTS (ASYNC OPTIMIZED) ---
async def run_tts(text, voice_code):
    communicate = edge_tts.Communicate(text, voice_code)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

if process_btn:
    if not input_text:
        st.toast("⚠️ Vui lòng nhập nội dung!", icon="❌")
    else:
        with st.status("🔮 Đang xử lý âm thanh chất lượng cao...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                voice = st.session_state.selected_voice
                
                if not is_srt:
                    # Xử lý văn bản
                    res_bytes = asyncio.run(run_tts(input_text, voice))
                    st.audio(res_bytes, format="audio/mp3")
                    st.download_button("📥 Tải MP3", res_bytes, file_name="ai_audio.mp3")
                else:
                    # Xử lý SRT chuẩn (Dứt điểm lỗi sập)
                    subs = list(srt.parse(input_text))
                    total_ms = int(subs[-1].end.total_seconds() * 1000) + 1500
                    final_audio = AudioSegment.silent(duration=total_ms)
                    
                    prog = st.progress(0)
                    for i, sub in enumerate(subs):
                        chunk_bytes = asyncio.run(run_tts(sub.content, voice))
                        if chunk_bytes:
                            seg = AudioSegment.from_file(io.BytesIO(chunk_bytes), format="mp3")
                            start_ms = int(sub.start.total_seconds() * 1000)
                            final_audio = final_audio.overlay(seg, position=start_ms)
                        
                        prog.progress((i + 1) / len(subs))
                        time.sleep(0.05) # Giãn cách để tránh lỗi 503
                    
                    # Xuất file
                    out_buffer = io.BytesIO()
                    final_audio.export(out_buffer, format="mp3")
                    st.audio(out_buffer.getvalue())
                    st.download_button("📥 Tải Audio hoàn chỉnh", out_buffer.getvalue(), file_name="dub_srt.mp3")
                    
                    # Trừ credit (Ví dụ: mỗi dòng 1 credit)
                    st.session_state.user_credits -= len(subs)

                status.update(label="✅ Xử lý hoàn tất!", state="complete")
            except Exception as e:
                st.error(f"Lỗi hệ thống: {str(e)}")
