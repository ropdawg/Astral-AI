from llama_cpp import Llama
import os

# Resolve model path relative to this script (points to scripts/models/...)
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
MODEL_FILE = "mistral-7b-v0.1.Q3_K_M.gguf"
MODEL_PATH = os.path.join(SCRIPT_DIR, "models", MODEL_FILE)

llm = Llama(model_path=MODEL_PATH)

# Initial prompt for XENI
xeni_prompt = (
    "You are XENI, a friendly, emotional support AI and personal chatbot. "
    "You respond with kindness, encouragement, and helpful advice. "
    "Always stay positive and supportive."
)

print("Hello! I am XENI, your emotional support chatbot. Type 'exit' to quit.")

while True:
    user_input = input("You: ")
    if user_input.lower() in ["exit", "quit"]:
        print("XENI: Goodbye! Take care!")
        break

    # Combine the initial prompt with user input
    full_prompt = f"{xeni_prompt}\nUser: {user_input}\nXENI:"

    # Generate response
    response = llm(full_prompt, max_tokens=200)
    print("XENI:", response['choices'][0]['text'])
