from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from config import MISTRAL_API_KEY

client = MistralClient(api_key=MISTRAL_API_KEY)

async def analyze_text(text, pos, neg):
    prompt = f"Текст: {text}\nИнтересы: {pos}\nИгнор: {neg}\nОтветь только YES или NO."
    try:
        response = client.chat(model="mistral-tiny", messages=[ChatMessage(role="user", content=prompt)])
        return "YES" in response.choices[0].message.content.upper()
    except: return False