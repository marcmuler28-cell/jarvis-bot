from assistant import ReActAgent, SelfImprover
from ui import VoiceInterface
from config import MODEL_FAST, MODEL_POWERFUL

def main():
    agent = ReActAgent(MODEL_FAST, MODEL_POWERFUL)
    voice = VoiceInterface()
    improver = SelfImprover(voice, agent)
    
    # Mensaje de inicio
    voice.speak("Estoy encendido ¿Qué vamos a hacer hoy?")
    if voice.wake_model:
        voice.passive_mode = True  # Entrar en modo pasivo si hay detector local

    while True:
        user_input = voice.listen()
        if user_input:
            response, actions = agent.process(user_input)
            voice.speak(response)
            if voice.wake_model:
                voice.passive_mode = True  # Volver a modo pasivo si hay detector local (modo "dormir")

if __name__ == '__main__':
    main()
