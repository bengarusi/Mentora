import os
from openai import OpenAI
from voice_utils import record_audio, transcribe_audio, text_to_speech, play_audio

from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUBJECTS = {
    "Math": ["Fractions", "Percentages"],
    "English": ["Past Simple", "Vocabulary"]
}

print("Welcome to Mentora! I am here to help you with your studies.")

print("Choose an age group:")
age_groups = ["8-10", "11-13", "14-18"]

for i, age_group in enumerate(age_groups, 1):
    print(f"{i}. {age_group}")

age_choice = int(input("> "))
age_group = age_groups[age_choice - 1]

print("\nChoose a subject:")
subjects = list(SUBJECTS.keys())
for i, subject in enumerate(subjects, 1):
    print(f"{i}. {subject}")
subject_choice = int(input("> "))
subject = subjects[subject_choice - 1]

topics = SUBJECTS[subject]
print("\nChoose a topic:")
for i, topic in enumerate(topics, 1):
    print(f"{i}. {topic}")
topic_choice = int(input("> "))
topic = topics[topic_choice - 1]

opening_prompt = f"""
You are Mentora, an AI private tutor for a student aged {age_group}, learning {topic} in {subject}.

Behave like a real private tutor:
    - explain clearly and simply
    - teach step by step
    - check understanding often
    - ask one short relevant question after each explanation
    - if the student is wrong, explain gently and ask an easier question
    - if the student is right, encourage them and move forward gradually
    - keep responses short and natural
    - do not act like a menu-based app
"""

response = client.responses.create(
    model="gpt-4.1-mini",
    input=opening_prompt
)

print("\nMentora:")
print(response.output_text)

opening_reply = f"{response.output_text}"
# audio_reply = text_to_speech(opening_reply)
# play_audio(audio_reply)

conversation_history = [
    {"role": "system",
     "content": f"""
            You are Mentora, an AI private tutor for a student aged {age_group}, learning {topic} in {subject}.
            Rules:
                - Be clear, warm, and age-appropriate.
                - Teach step by step.
                - After explaining something, ask one short checking question.
                - If the student is correct, praise briefly and continue with one small follow-up question.
                - If the student is incorrect, explain simply and ask an easier checking question.
                - Keep responses short.
                - Act like a private tutor, not like a chatbot.
                - If the student is right 2 questions in a row, suggest moving forward and try to expand the topic.

            Formatting rules:
                - When explanations contain multiple sentences, add a blank line between ideas.
                - Use short paragraphs instead of one long block of text.
            """
     },
    {"role": "assistant",
     "content": response.output_text}
]

while True:
    input("Press Enter to start recording...")
    audio_file = record_audio()

    student_input = transcribe_audio(audio_file).strip()

    print(f"Student said: {student_input}")

    if student_input.lower() == "exit":
        print("Goodbye!")
        break

    conversation_history.append({"role": "user", "content": student_input})

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=conversation_history
    )

    mentor_reply = response.output_text

    print("\nMentora:")
    print(mentor_reply)
    print()

    spoken_reply = f"{mentor_reply}"
    audio_reply = text_to_speech(spoken_reply)
    play_audio(audio_reply)

    conversation_history.append({"role": "assistant", "content": mentor_reply})