import os
import tempfile
import wave

import sounddevice as sd
import soundfile as sf
import numpy as np
from scipy.io.wavfile import write
from openai import OpenAI


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#hi

def record_audio(filename="student_input.wav", samplerate=16000):
    print("Press Enter to START recording")
    input()

    print("Recording... Press Enter to STOP")

    audio_data = []

    def callback(indata, frames, time, status):
        audio_data.append(indata.copy())

    with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", callback=callback):
        input()

    audio = np.concatenate(audio_data, axis=0)
    write(filename, samplerate, audio)

    print("Recording finished.\n")
    return filename


def transcribe_audio(file_path):
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file
        )
    return transcript.text


def text_to_speech(text, output_file="mentora_reply.mp3"):
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    ) as response:
        response.stream_to_file(output_file)

    return output_file


def play_audio(file_path):
    data, samplerate = sf.read(file_path)
    sd.play(data, samplerate)
    sd.wait()