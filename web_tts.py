import streamlit as st
import asyncio
import edge_tts
import srt
import tempfile
import os
from pydub import AudioSegment
import io
from static_ffmpeg import add_paths

# Tự động sửa lỗi "Couldn't find ffmpeg"
try:
    add_paths()
except:
    pass

# Cấu hình giao diện Web Pro
st.set_page_config(page_title="AI TTS Web Pro", layout="wide")

st.title("🎙️ HỆ THỐNG LỒNG TIẾNG ĐA NĂNG (BẢN WEB)")
st.info("Phiên bản Web giúp dứt điểm hoàn toàn lỗi nhảy cửa sổ trên mọi máy tính.")

# --- KHU VỰC NHẬP LIỆU ---
col1, col2 = st.columns([2, 1])

with col1:
    input_text = st.text_area("Dán kịch bản (Text) hoặc nội dung SRT vào đây:", height=400, placeholder="Nhập nội dung phim tại đây...")

with col2:
    @st.cache_data
    def get_voices_sync():
        async def fetch():
            return await edge_tts.list_voices()
        return asyncio.run(fetch())

    try:
        all_voices = get_voices_sync()
        countries = sorted(list(set([v['Locale'] for v in all_voices])))
        sel_country = st.selectbox("Quốc gia:", ["Tất cả"] + countries, index=countries.index("vi-VN") + 1 if "vi-VN" in countries else 0)
        
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
    except Exception as e:
        st.error(f"Lỗi tải danh sách giọng: {e}")

# --- XỬ LÝ LỒNG TIẾNG ---
if st.button("🚀 BẮT ĐẦU TẠO ÂM THANH", type="primary", use_container_width=True):
    if not input_text:
        st.error("Vui lòng nhập nội dung văn bản hoặc SRT!")
    else:
        with st.status("Đang xử lý... vui lòng chờ...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                
                if not is_srt:
                    # Dịch văn bản thường
                    communicate = edge_tts.Communicate(input_text, sel_voice_code)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        asyncio.run(communicate.save(tmp.name))
                        with open(tmp.name, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3")
                        st.download_button("📥 Tải file MP3", audio_bytes, file_name="AI_Voice_Output.mp3")
                    os.remove(tmp.name)
                else:
                    # Dịch file SRT (Ghép khớp mốc thời gian) [cite: 11]
                    subs = list(srt.parse(input_text))
                    total_duration_ms = int(subs[-1].end.total_seconds() * 1000) + 2000
                    final_audio = AudioSegment.silent(duration=total_duration_ms)
                    
                    progress_bar = st.progress(0)
                    for i, sub in enumerate(subs):
                        comm = edge_tts.Communicate(sub.content, sel_voice_code)
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_chunk:
                            asyncio.run(comm.save(tmp_chunk.name))
                            segment = AudioSegment.from_file(tmp_chunk.name, format="mp3")
                            os.remove(tmp_chunk.name)
                        
                        start_pos = int(sub.start.total_seconds() * 1000)
                        final_audio = final_audio.overlay(segment, position=start_pos)
                        progress_bar.progress((i + 1) / len(subs))
                    
                    buffer = io.BytesIO()
                    final_audio.export(buffer, format="mp3")
                    st.audio(buffer.getvalue(), format="audio/mp3")
                    st.download_button("📥 Tải file lồng tiếng phim hoàn chỉnh", buffer.getvalue(), file_name="Phim_Final_Voice.mp3")

                status.update(label="✅ Đã xử lý xong!", state="complete")
            except Exception as e:
                st.error(f"Lỗi xử lý âm thanh: {e}")