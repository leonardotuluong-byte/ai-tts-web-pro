import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment
import io
import time

# CẤU HÌNH GIAO DIỆN
st.set_page_config(page_title="AI TTS Web Pro - Fixed", layout="wide")

st.title("🎙️ HỆ THỐNG LỒNG TIẾNG ĐA NĂNG (BẢN WEB)")
st.info("Phiên bản sửa lỗi 503 Throttling và lỗi nhận diện âm thanh.")

# --- KHU VỰC NHẬP LIỆU ---
col1, col2 = st.columns([2, 1])

with col1:
    input_text = st.text_area("Dán kịch bản hoặc nội dung SRT vào đây:", height=400, placeholder="Nhập nội dung phim tại đây...")

with col2:
    @st.cache_data
    def get_voices_sync():
        async def fetch():
            return await edge_tts.list_voices()
        return asyncio.run(fetch())

    try:
        all_voices = get_voices_sync()
        countries = sorted(list(set([v['Locale'] for v in all_voices])))
        # Mặc định chọn Việt Nam
        default_index = countries.index("vi-VN") + 1 if "vi-VN" in countries else 0
        sel_country = st.selectbox("Quốc gia:", ["Tất cả"] + countries, index=default_index)
        
        genders = ["Tất cả", "Male", "Female"]
        sel_gender = st.selectbox("Giới tính:", genders)
        
        search_name = st.text_input("Tìm tên giọng (VD: HoaiMy):", "")

        filtered = [v for v in all_voices if 
                    (sel_country == "Tất cả" or v['Locale'] == sel_country) and
                    (sel_gender == "Tất cả" or v['Gender'] == sel_gender) and
                    (search_name.lower() in v['ShortName'].lower())]
        
        voice_options = [f"[{v['Locale']}] {v['ShortName']} ({v['Gender']})" for v in filtered]
        if voice_options:
            sel_voice_str = st.selectbox("Chọn giọng đọc:", voice_options)
            sel_voice_code = sel_voice_str.split(" ")[1]
        else:
            st.warning("Không tìm thấy giọng phù hợp.")
            sel_voice_code = None
    except Exception as e:
        st.error(f"Lỗi tải danh sách giọng: {e}")

# --- HÀM XỬ LÝ TTS CHO TỪNG ĐOẠN ---
async def text_to_speech_bytes(text, voice):
    if not text.strip():
        return None
    try:
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        return None

# --- XỬ LÝ LỒNG TIẾNG ---
if st.button("🚀 BẮT ĐẦU TẠO ÂM THANH", type="primary", use_container_width=True):
    if not input_text:
        st.error("Vui lòng nhập nội dung văn bản hoặc SRT!")
    elif not sel_voice_code:
        st.error("Vui lòng chọn giọng đọc!")
    else:
        with st.status("Đang xử lý âm thanh... vui lòng chờ...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                
                if not is_srt:
                    # Xử lý văn bản thường
                    audio_bytes = asyncio.run(text_to_speech_bytes(input_text, sel_voice_code))
                    if audio_bytes:
                        st.audio(audio_bytes, format="audio/mp3")
                        st.download_button("📥 Tải file MP3", audio_bytes, file_name="AI_Voice.mp3")
                else:
                    # Xử lý file SRT
                    subs = list(srt.parse(input_text))
                    # Tính tổng thời lượng (ms)
                    total_duration_ms = int(subs[-1].end.total_seconds() * 1000) + 1000
                    final_audio = AudioSegment.silent(duration=total_duration_ms)
                    
                    progress_bar = st.progress(0)
                    
                    for i, sub in enumerate(subs):
                        # Chống lỗi 503 bằng cách nghỉ nhẹ 0.1s mỗi câu
                        time.sleep(0.1) 
                        
                        audio_data = asyncio.run(text_to_speech_bytes(sub.content, sel_voice_code))
                        
                        if audio_data:
                            # Chuyển bytes sang segment audio
                            segment = AudioSegment.from_file(io.BytesIO(audio_data), format="mp3")
                            start_pos = int(sub.start.total_seconds() * 1000)
                            # Đè âm thanh vào đúng vị trí thời gian
                            final_audio = final_audio.overlay(segment, position=start_pos)
                        
                        progress_bar.progress((i + 1) / len(subs))
                    
                    # Xuất kết quả cuối cùng
                    buffer = io.BytesIO()
                    final_audio.export(buffer, format="mp3")
                    st.audio(buffer.getvalue(), format="audio/mp3")
                    st.download_button("📥 Tải file hoàn chỉnh", buffer.getvalue(), file_name="Phim_Final_Voice.mp3")

                status.update(label="✅ Đã xử lý xong!", state="complete")
            except Exception as e:
                st.error(f"Lỗi hệ thống: {e}")
