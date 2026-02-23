import sys
import os
import arabic_reshaper
from bidi.algorithm import get_display

# Ensure the nmt directory is in the path if running from elsewhere
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from demo_translation import translate_text

def format_arabic(text):
    """
    Reshapes Arabic text and applies the BiDi algorithm for correct terminal display.
    """
    # Reshape the characters (connect letters)
    reshaped_text = arabic_reshaper.reshape(text)
    # Apply BiDi (Right-to-Left logic)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def main():
    print("--- NLLB Translator CLI ---")
    print("Type your text below to translate from English to Arabic.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            user_input = input("Enter English text: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['exit', 'quit']:
                print("Goodbye!")
                break

            print("Translating...")
            # Using the modular function
            translation = translate_text(user_input, src_lang="eng_Latn", tgt_lang="arb_Arab")
            
            # Format for terminal display
            formatted_translation = format_arabic(translation)
            
            print(f"\nArabic Translation:\n{formatted_translation}")
            print("-" * 30)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
