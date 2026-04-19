import streamlit as st
import asyncio
import edge_tts
import srt
import os
from pydub import AudioSegment, silence
import io
import time

# --- HÀM CẮT KHOẢNG LẶNG VÀ NỐI ÂM THANH MƯỢT ---
def trim_silence(audio_segment):
    """Cắt bỏ khoảng lặng ở đầu và cuối của một đoạn âm thanh"""
    # Ngưỡng im lặng thường là -50dBFS
    start_trim = silence.detect_leading_silence(audio_segment, silence_threshold=-50.0)
    end_trim = silence.detect_leading_silence(audio_segment.reverse(), silence_threshold=-50.0)
    
    duration = len(audio_segment)
    return audio_segment[start_trim:duration-end_trim]

# --- CẬP NHẬT LOGIC XỬ LÝ SRT TRONG APP ---
# (Chỉ thay đổi phần xử lý dưới nút process_btn)

if 'process_btn' in locals() or True: # Giả định nút đã nhấn
    # ... (Các đoạn code khởi tạo cũ) ...
    
    if "-->" in input_text:
        subs = list(srt.parse(input_text))
        total_ms = int(subs[-1].end.total_seconds() * 1000) + 2000
        final_audio = AudioSegment.silent(duration=total_ms)
        
        last_end_ms = 0 # Lưu mốc kết thúc của câu trước đó
        
        prog = st.progress(0)
        for i, sub in enumerate(subs):
            chunk = asyncio.run(run_tts_with_retry(sub.content, voice))
            if chunk:
                # 1. Load âm thanh và CẮT KHOẢNG LẶNG ĐẦU/CUỐI
                seg = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
                seg = trim_silence(seg) 
                
                # 2. Tính toán thời gian
                start_ms = int(sub.start.total_seconds() * 1000)
                duration_allowed = (sub.end - sub.start).total_seconds() * 1000
                
                # KIỂM TRA NỐI CÂU MƯỢT:
                # Nếu câu trước không kết thúc bằng dấu câu, nối sát vào mốc kết thúc của câu trước
                prev_text = subs[i-1].content.strip() if i > 0 else "."
                is_continuous = not prev_text.endswith(('.', '!', '?', '。', '！', '？'))
                
                if is_continuous and last_end_ms > 0:
                    # Nếu là câu nối tiếp, bắt đầu ngay khi câu trước vừa dứt (cho phép gối đầu 50ms)
                    current_start = max(start_ms, last_end_ms - 50)
                else:
                    current_start = start_ms

                # 3. Căn chỉnh tốc độ nếu cần (giữ logic cũ của bạn)
                actual_duration = len(seg)
                if actual_duration > duration_allowed:
                    factor = actual_duration / duration_allowed
                    seg = speedup(seg, playback_speed=min(factor, 2.0))
                
                # 4. Đè âm thanh vào vị trí mới đã tối ưu
                final_audio = final_audio.overlay(seg, position=current_start)
                
                # Cập nhật mốc kết thúc thực tế
                last_end_ms = current_start + len(seg)
            
            prog.progress((i + 1) / len(subs))
            time.sleep(0.1)
