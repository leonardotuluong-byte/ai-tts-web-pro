# --- HÀM TTS CÓ CƠ CHẾ THỬ LẠI (RETRY LOGIC) ---
async def run_tts_with_retry(text, voice_code, retries=3):
    if not text.strip():
        return None
    
    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(text, voice_code)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            if audio_data:
                return audio_data
        except Exception as e:
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2 # Đợi 2s, 4s nếu lỗi
                time.sleep(wait_time)
                continue
            else:
                return None
    return None

# --- PHẦN XỬ LÝ KHI NHẤN NÚT ---
if process_btn:
    if not input_text:
        st.toast("⚠️ Vui lòng nhập nội dung!", icon="❌")
    else:
        with st.status("🔮 Đang xử lý âm thanh (Chế độ chống chặn IP)...", expanded=True) as status:
            try:
                is_srt = " --> " in input_text
                voice = st.session_state.selected_voice
                
                if not is_srt:
                    # Xử lý văn bản thường
                    res_bytes = asyncio.run(run_tts_with_retry(input_text, voice))
                    if res_bytes:
                        st.audio(res_bytes, format="audio/mp3")
                        st.download_button("📥 Tải MP3", res_bytes, file_name="ai_audio.mp3")
                else:
                    # Xử lý SRT (Dứt điểm lỗi 503)
                    subs = list(srt.parse(input_text))
                    total_ms = int(subs[-1].end.total_seconds() * 1000) + 2000
                    final_audio = AudioSegment.silent(duration=total_ms)
                    
                    prog = st.progress(0)
                    for i, sub in enumerate(subs):
                        # Gửi yêu cầu với cơ chế thử lại
                        chunk_bytes = asyncio.run(run_tts_with_retry(sub.content, voice))
                        
                        if chunk_bytes:
                            try:
                                seg = AudioSegment.from_file(io.BytesIO(chunk_bytes), format="mp3")
                                start_ms = int(sub.start.total_seconds() * 1000)
                                final_audio = final_audio.overlay(seg, position=start_ms)
                            except:
                                pass # Bỏ qua dòng lỗi âm thanh
                        
                        prog.progress((i + 1) / len(subs))
                        # Tăng độ trễ lên để Server Microsoft không "nổi giận"
                        time.sleep(0.5) 
                    
                    # Xuất file kết quả
                    out_buffer = io.BytesIO()
                    final_audio.export(out_buffer, format="mp3")
                    st.audio(out_buffer.getvalue())
                    st.download_button("📥 Tải Audio hoàn chỉnh", out_buffer.getvalue(), file_name="dub_srt.mp3")

                status.update(label="✅ Hoàn tất!", state="complete")
            except Exception as e:
                st.error(f"Lỗi: {str(e)}. Gợi ý: Hãy thử lại sau 1 phút hoặc đổi giọng đọc khác.")
