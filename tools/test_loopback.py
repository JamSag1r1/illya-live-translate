import os, sys, time, threading, wave, struct, math, tempfile
import numpy as np
import pyaudiowpatch as pyaudio

# ---- 1. locate WASAPI loopback of the current default output device ----
p = pyaudio.PyAudio()
try:
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
except OSError:
    print("no WASAPI"); sys.exit(1)
default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
print("default output:", default_out["name"], "sr", default_out["defaultSampleRate"])

target = default_out
if not default_out.get("isLoopbackDevice"):
    for lb in p.get_loopback_device_info_generator():
        if default_out["name"] in lb["name"]:
            target = lb
            break
    else:
        print("NO loopback twin found for default output; loopbacks available:")
        for lb in p.get_loopback_device_info_generator():
            print("   ", lb["name"])
        sys.exit(1)
print("loopback device:", target["name"], "ch", target["maxInputChannels"], "sr", target["defaultSampleRate"])

rate = int(target["defaultSampleRate"])
ch = int(target["maxInputChannels"])

# ---- 2. make a test wav and play it to the default output (ASUNC) ----
wav = os.path.join(tempfile.gettempdir(), "lb_tone.wav")
sr = 48000
buf = bytearray()
for n in range(int(sr * 2.5)):
    v = int(12000 * math.sin(2 * math.pi * 440 * n / sr))
    buf += struct.pack("<hh", v, v)
with wave.open(wav, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(bytes(buf))

import winsound
winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)

# ---- 3. capture ----
CHUNK = 1024
frames = []
stream = p.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                input_device_index=target["index"], frames_per_buffer=CHUNK)
t0 = time.time()
while time.time() - t0 < 2.0:
    data = stream.read(CHUNK, exception_on_overflow=False)
    frames.append(np.frombuffer(data, dtype=np.int16))
stream.stop_stream(); stream.close(); p.terminate()
winsound.PlaySound(None, winsound.SND_PURGE)

a = np.concatenate(frames).astype(np.float32) / 32768.0
print(f"captured {len(a)/rate:.2f}s  rms={np.sqrt((a**2).mean()):.5f} peak={np.abs(a).max():.4f} "
      f"-> {'LOOPBACK WORKS' if np.abs(a).max() > 0.01 else 'SILENT (loopback gives nothing)'}")
