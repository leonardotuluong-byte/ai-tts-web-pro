import asyncio
import io
import os
import threading
import time
import edge_tts
from pydub import AudioSegment, silence
from pydub.effects import normalize, speedup
import srt
import streamlit as st

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(
    page_title="AI TTS Pro - Studio Lồng Tiếng",
    layout="wide",
    page_icon="🎙️",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .stTextArea textarea { 
        font-size: 16px !important; color: #000000 !important; 
        background-color: #ffffff !important; border-radius: 10px;
    }
    .stButton>button { 
        width: 100%; border-radius: 10px; font-weight: bold; height: 3.5em; 
        background: linear-gradient(45deg, #22c55e, #10b981); color: white; border: none;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# --- KHỞI TẠO SESSION STATE ---
if "selected_voice" not in st.session_state:
  st.session_state.selected_voice = "es-US-AlonsoNeural"
if "audio_bytes" not in st.session_state:
  st.session_state.audio_bytes = None
if "status_message" not in st.session_state:
  st.session_state.status_message = ""


# --- HÀM XỬ LÝ ASYNC TOÀN DIỆN CHO TOÀN BỘ KỊCH BẢN ---
async def process_audio_async(input_text, voice_code):
  is_srt = " --> " in input_text

  if not is_srt:
    # Xử lý văn bản thường: Chia nhỏ đoạn văn thành các câu để gọi TTS an toàn
    paragraphs = [p.strip() for p in input_text.split("\n") if p.strip()]
    if not paragraphs:
      paragraphs = [input_text]

    combined_audio = AudioSegment.silent(
        duration=0, frame_rate=44100
    ).set_channels(1).set_sample_width(2)

    for para in paragraphs:
      sentences = [s.strip() for s in para.split(".") if s.strip()]
      if not sentences:
        sentences = [para]

      for sentence in sentences:
        if not sentence:
          continue
        full_sentence = (
            sentence if sentence.endswith((".", "!", "?")) else sentence + "."
        )

        audio_chunk = None
        for attempt in range(3):
          try:
            communicate = edge_tts.Communicate(full_sentence, voice_code)
            audio_data = bytearray()
            async for chunk in communicate.stream():
              if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
            if audio_data:
              audio_chunk = bytes(audio_data)
              break
          except:
            await asyncio.sleep(1)

        if audio_chunk:
          seg = AudioSegment.from_file(io.BytesIO(audio_chunk), format="mp3")
          seg = seg.set_frame_rate(44100).set_channels(1).set_sample_width(2)
          seg = normalize(seg)
          combined_audio += seg + AudioSegment.silent(
              duration=300, frame_rate=44100
          )
        await asyncio.sleep(0.2)

    if len(combined_audio) > 0:
      combined_audio = normalize(combined_audio)
      buf = io.BytesIO()
      combined_audio.export(buf, format="mp3", bitrate="192k")
      return buf.getvalue(), "✅ Xử lý văn bản thành công tuyệt đối!"
    else:
      return None, "❌ Không thể tải giọng đọc từ máy chủ. Vui lòng thử lại!"

  else:
    # Xử lý file SRT chuẩn
    subs = list(srt.parse(input_text))
    if not subs:
      return None, "❌ Định dạng SRT không hợp lệ!"

    total_ms = int(subs[-1].end.total_seconds() * 1000) + 2000
    final_audio = AudioSegment.silent(
        duration=total_ms, frame_rate=44100
    ).set_channels(1).set_sample_width(2)
    last_end_ms = 0

    for i, sub in enumerate(subs):
      text_content = sub.content.strip()
      if not text_content:
        continue

      audio_chunk = None
      for attempt in range(3):
        try:
          communicate = edge_tts.Communicate(text_content, voice_code)
          audio_data = bytearray()
          async for chunk in communicate.stream():
            if chunk["type"] == "audio":
              audio_data.extend(chunk["data"])
          if audio_data:
            audio_chunk = bytes(audio_data)
            break
        except:
          await asyncio.sleep(1)

      if audio_chunk:
        seg = AudioSegment.from_file(io.BytesIO(audio_chunk), format="mp3")
        seg = seg.set_frame_rate(44100).set_channels(1).set_sample_width(2)

        try:
          start_trim = silence.detect_leading_silence(
              seg, silence_threshold=-50.0
          )
          end_trim = silence.detect_leading_silence(
              seg.reverse(), silence_threshold=-50.0
          )
          if start_trim + end_trim < len(seg):
            seg = seg[start_trim : len(seg) - end_trim]
        except:
          pass

        srt_start_ms = int(sub.start.total_seconds() * 1000)
        duration_allowed_ms = (sub.end - sub.start).total_seconds() * 1000
        if duration_allowed_ms <= 0:
          duration_allowed_ms = 100

        prev_text = subs[i - 1].content.strip() if i > 0 else "."
        is_continuous = not any(
            prev_text.endswith(p)
            for p in [".", "!", "?", "。", "！", "？", ";", ":"]
        )

        if is_continuous and last_end_ms > 0:
          current_start = max(srt_start_ms, last_end_ms - 30)
        else:
          current_start = srt_start_ms

        actual_duration_ms = len(seg)
        if actual_duration_ms > duration_allowed_ms:
          factor = actual_duration_ms / duration_allowed_ms
          if factor > 1.0:
            try:
              seg = speedup(
                  seg,
                  playback_speed=min(factor, 2.0),
                  chunk_size=30,
                  crossfade=15,
              )
            except:
              pass
          seg = seg[: int(duration_allowed_ms)]

        try:
          seg = seg.fade_in(15).fade_out(15)
        except:
          pass

        final_audio = final_audio.overlay(seg, position=current_start)
        last_end_ms = current_start + len(seg)
      await asyncio.sleep(0.2)

    final_audio = normalize(final_audio)
    buf = io.BytesIO()
    final_audio.export(buf, format="mp3", bitrate="192k")
    return buf.getvalue(), "✅ Xử lý đồng bộ SRT hoàn tất xuất sắc!"


# --- HÀM GỌI THREAD AN TOÀN DUY NHẤT ---
def run_processing(input_text, voice_code):
  result = [None]
  exception = [None]

  def target():
    try:
      if os.name == "nt":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )
      result[0] = asyncio.run(process_audio_async(input_text, voice_code))
    except Exception as e:
      exception[0] = e

  t = threading.Thread(target=target)
  t.start()
  t.join()
  if exception[0]:
    raise exception[0]
  return result[0]


# --- THANH BÊN (SIDEBAR) CẤU HÌNH ---
with st.sidebar:
  st.markdown("### ⚙️ Cài đặt Giọng đọc")


  @st.cache_data
  def get_all_voices():
    # Lấy danh sách giọng an toàn
    res_list = [None]

    def t_func():
      if os.name == "nt":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )
      res_list[0] = asyncio.run(edge_tts.list_voices())

    th = threading.Thread(target=t_func)
    th.start()
    th.join()
    return res_list[0] or []


  voices = get_all_voices()
  locales = sorted(list(set([v["Locale"] for v in voices]))) if voices else []
  default_loc = (
      "es-US"
      if "es-US" in locales
      else ("vi-VN" if "vi-VN" in locales else (locales[0] if locales else ""))
  )

  lang_filter = st.selectbox(
      "🌐 Ngôn ngữ:",
      locales if locales else ["es-US"],
      index=locales.index(default_loc) if default_loc in locales else 0,
  )
  gender_filter = st.radio(
      "👤 Giới tính:", ["All", "Male", "Female"], horizontal=True
  )

  st.divider()
  st.markdown("💡 **Mẹo:** Hỗ trợ cả văn bản thường và file SRT.")

# --- GIAO DIỆN CHÍNH ---
st.markdown(
    "<h2 style='text-align: center; color: #22c55e;'>🎙️ AI TTS Pro - Studio"
    " Lồng Tiếng Chuyên Nghiệp</h2>",
    unsafe_allow_html=True,
)
st.write("")

col_input, col_settings = st.columns([2, 1], gap="medium")

with col_input:
  st.markdown("#### 📝 1. Nhập Kịch bản hoặc SRT")
  input_text = st.text_area(
      "Dán nội dung vào đây:",
      height=320,
      placeholder="Dán văn bản hoặc file SRT có chứa -->...",
  )

with col_settings:
  st.markdown("#### 🎙️ 2. Chọn Giọng Đọc")
  if voices:
    v_list = [v for v in voices if v["Locale"] == lang_filter]
    if gender_filter != "All":
      v_list = [v for v in v_list if v["Gender"] == gender_filter]

    voice_options = {
        f"{v['ShortName']} ({v['Gender']})": v["ShortName"] for v in v_list
    }
    selected_label = st.selectbox(
        "Danh sách giọng khả dụng:",
        options=list(voice_options.keys())
        if voice_options
        else ["Không có giọng"],
    )
    if voice_options:
      st.session_state.selected_voice = voice_options[selected_label]

st.write("")
process_btn = st.button(
    "🚀 BẮT ĐẦU XỬ LÝ VÀ TẠO FILE ÂM THANH", type="primary", use_container_width=True
)

# --- XỬ LÝ KHI BẤM NÚT ---
if process_btn:
  if not input_text.strip():
    st.error("❌ Vui lòng nhập nội dung kịch bản trước khi bấm bắt đầu!")
  else:
    with st.spinner(
        "⏳ Đang kết nối máy chủ, xử lý và tạo file âm thanh..."
    ):
      try:
        audio_bytes, msg = run_processing(
            input_text, st.session_state.selected_voice
        )
        if audio_bytes:
          st.session_state.audio_bytes = audio_bytes
          st.session_state.status_message = msg
        else:
          st.session_state.audio_bytes = None
          st.error(msg)
      except Exception as e:
        st.error(f"❌ Lỗi hệ thống: {str(e)}")

# --- HIỂN THỊ KẾT QUẢ VÀ NÚT TẢI FILE ---
if st.session_state.audio_bytes is not None:
  st.markdown("---")
  st.markdown("### 🎵 3. Kết Quả File Âm Thanh Hoàn Chỉnh")
  st.success(st.session_state.status_message)

  st.audio(st.session_state.audio_bytes, format="audio/mp3")

  st.download_button(
      label="📥 TẢI FILE ÂM THANH HOÀN CHỈNH (.MP3)",
      data=st.session_state.audio_bytes,
      file_name="ai_tts_output.mp3",
      mime="audio/mpeg",
      use_container_width=True,
  )
