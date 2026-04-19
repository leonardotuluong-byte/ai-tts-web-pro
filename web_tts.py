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
st.info("Phiên bản sửa lỗi sập App và tối ưu hóa bộ nhớ.")

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
        default_index = countries.index("vi-VN") + 1 if "vi-VN" in countries else 0
        sel_country = st.selectbox("Quốc gia:", ["Tất cả"] + countries, index=default_index)
        
        sel_gender = st.selectbox("Giới tính:", ["Tất cả", "Male", "Female"])
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

# --- HÀM XỬ LÝ TTS ---
async def process_tts_chunk(text, voice):
    if not text.strip(): return None
    try:
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except:
        return None

# --- XỬ LÝ CHÍNH ---
if st.button("🚀 BẮT ĐẦU TẠO ÂM THANH", type="primary", use_container_width=True):
    if not input_text:
        st.error("Vui lòng nhập nội dung!")
    elif not sel_voice_code:
        st.error("Vui lòng chọn giọng đọc!")
    else:
        with st.status("Đang xử lý... (Vui lòng không tắt trình duyệt)", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                
                if not is_srt:
                    # Văn bản thường
                    audio_bytes = asyncio.run(process_tts_chunk(input_text, sel_voice_code))
                    if audio_bytes:
                        st.audio(audio_bytes, format="audio/mp3")
                        st.download_button("📥 Tải MP3", audio_bytes, file_name="voice.mp3")
                else:
                    # File SRT
                    subs = list(srt.parse(input_text))
                    
                    # Cảnh báo nếu file quá dài có thể gây tràn RAM
                    if len(subs) > 500:
                        st.warning("⚠️ File SRT khá dài, hệ thống đang nỗ lực xử lý bộ nhớ...")

                    total_ms = int(subs[-1].end.total_seconds() * 1000) + 1000
                    final_audio = AudioSegment.silent(duration=total_ms)
                    
                    progress_bar = st.progress(0)
                    
                    # Chạy xử lý từng dòng
                    for i, sub in enumerate(subs):
                        audio_data = asyncio.run(process_tts_chunk(sub.content, sel_voice_code))
                        
                        if audio_data:
                            try:
                                chunk_io = io.BytesIO(audio_data)
                                segment = AudioSegment.from_file(chunk_io, format="mp3")
                                start_pos = int(sub.start.total_seconds() * 1000)
                                final_audio = final_audio.overlay(segment, position=start_pos)
                            except Exception as e:
                                print(f"Lỗi dòng {i}: {e}")
                        
                        progress_bar.progress((i + 1) / len(subs))
                        time.sleep(0.05) # Nghỉ cực ngắn để server không bị quá tải
                    
                    # Xuất kết quả
                    output_buffer = io.BytesIO()
                    final_audio.export(output_buffer, format="mp3")
                    st.audio(output_buffer.getvalue(), format="audio/mp3")
                    st.download_button("📥 Tải file hoàn chỉnh", output_buffer.getvalue(), file_name="dub_final.mp3")

                status.update(label="✅ Hoàn thành!", state="complete")
            except Exception as e:
                st.error(f"App đã dừng do lỗi: {e}. Vui lòng kiểm tra file packages.txt đã có ffmpeg chưa.")
