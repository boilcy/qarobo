import pyaudio
import wave
import sys

# 录音参数
FORMAT = pyaudio.paInt16  # 采用16位的PCM格式
CHANNELS = 1  # 单声道
RATE = 16000  # 采样率，例如 44.1kHz
CHUNK = 1024  # 每次读取的音频帧数
RECORD_SECONDS = 5  # 录音时长（秒）
WAVE_OUTPUT_FILENAME = "output.wav"  # 输出文件名

p = pyaudio.PyAudio()

# 检查可用的音频输入设备
info = p.get_host_api_info_by_index(0)
numdevices = info.get("deviceCount")

input_device_index = -1
print("------ Sound Devices ------")
for i in range(0, numdevices):
    if (p.get_device_info_by_host_api_device_index(0, i).get("maxInputChannels")) > 0:
        print(
            "Input Device id ",
            i,
            " - ",
            p.get_device_info_by_host_api_device_index(0, i).get("name"),
        )
        # 尝试自动选择默认输入设备，或者你可以根据打印的信息手动设置 input_device_index
        if p.get_device_info_by_host_api_device_index(0, i).get("defaultInputDevice"):
            input_device_index = i
            print(f"  (Selected as default input device: {input_device_index})")

if input_device_index == -1:
    print("Error: No input audio device found. Please check your mic connection.")
    input_device_index = 1

print(f"\nUsing input device index: {input_device_index}")

try:
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        input_device_index=input_device_index,
    )  # 指定输入设备

    print(f"* 正在录音，请说 {RECORD_SECONDS} 秒...")

    frames = []

    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("* 录音结束")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # 将录音数据保存到WAV文件
    wf = wave.open(WAVE_OUTPUT_FILENAME, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))
    wf.close()

    print(f"录音已保存到 {WAVE_OUTPUT_FILENAME}")
    print("您可以播放此文件来确认录音效果。")

except Exception as e:
    print(f"录音过程中发生错误: {e}")
    # 尝试关闭Stream和PyAudio对象，防止资源泄露
    if "stream" in locals() and stream.is_active():
        stream.stop_stream()
        stream.close()
    if "p" in locals():
        p.terminate()
    sys.exit(1)
