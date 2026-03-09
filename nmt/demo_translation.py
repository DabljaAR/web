import os
import sys
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

class NLLBTranslator:
    """
    A reusable translator class using the NLLB-200 model.
    Handles device selection (CUDA/CPU), long text chunking, and model persistence.
    """
    def __init__(self, model_name="facebook/nllb-200-distilled-600M"):
        self.model_name = model_name
        self.device = self._get_device()
        
        print(f"Initializing NLLBTranslator with model '{model_name}' on {self.device}...")
        
        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(self.device)

    def _get_device(self):
        """Standard CUDA safety check for local environments."""
        device = "cpu"
        if torch.cuda.is_available():
            try:
                major, minor = torch.cuda.get_device_capability()
                gpu_arch = f"sm_{major}{minor}"
                if gpu_arch in torch.cuda.get_arch_list():
                    device = "cuda:0"
                else:

                    print(f"Warning.")
                    # print(f"Warning: GPU {gpu_arch} not supported by this Torch build. Using CPU.")
            except Exception as e:
                print(f"Warning: Error checking CUDA capability: {e}. Defaulting to CPU.")
        return device

    def translate(self, text, src_lang="eng_Latn", tgt_lang="arb_Arab", max_length=512):
        """
        Translates text with support for long strings and lists of strings.
        
        Args:
            text: String or list of strings to translate.
            src_lang: Source language code (e.g., 'eng_Latn').
            tgt_lang: Target language code (e.g., 'arb_Arab').
            max_length: Maximum tokens per chunk.
            
        Returns:
            Translated string or list of strings.
        """
        if not text:
            return "" if isinstance(text, str) else []

        if isinstance(text, list):
            return [self.translate(t, src_lang, tgt_lang, max_length) for t in text]

        # Check token count to decide if chunking is needed
        inputs = self.tokenizer(text, return_tensors="pt")
        num_tokens = inputs.input_ids.shape[1]

        if num_tokens <= max_length:
            return self._run_inference(text, tgt_lang, max_length)
        else:
            return self._translate_long_text(text, tgt_lang, max_length)

    def _run_inference(self, text, tgt_lang, max_length):
        """Internal method to perform the actual model inference."""
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        outputs = self.model.generate(
            **inputs,
            forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_lang),
            max_length=max_length
        )
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def _translate_long_text(self, text, tgt_lang, max_length):
        """Splits long text into manageable chunks based on token counts."""
        # Split by spaces but preserve newlines roughly
        words = text.replace('\n', ' \n ').split(' ')
        chunks = []
        current_words = []
        
        for word in words:
            if not word: continue
            
            test_words = current_words + [word]
            test_str = " ".join(test_words).replace(' \n ', '\n')
            
            # Use the tokenizer to get exact token count
            token_count = self.tokenizer(test_str, return_tensors="pt").input_ids.shape[1]
            
            if token_count > max_length - 10:  # Buffer for special tokens
                if current_words:
                    chunk_str = " ".join(current_words).replace(' \n ', '\n')
                    chunks.append(self._run_inference(chunk_str, tgt_lang, max_length))
                    current_words = [word]
                else:
                    # Word itself is too long (rarely happens with subword tokenizers)
                    chunks.append(self._run_inference(word, tgt_lang, max_length))
                    current_words = []
            else:
                current_words = test_words
        
        if current_words:
            chunk_str = " ".join(current_words).replace(' \n ', '\n')
            chunks.append(self._run_inference(chunk_str, tgt_lang, max_length))
            
        return " ".join(chunks)

# --- REUSABLE FUNCTION INTERFACE ---
_global_translator = None

def translate_text(text, src_lang="eng_Latn", tgt_lang="arb_Arab", model_name="facebook/nllb-200-distilled-600M"):
    """
    Convenience function that maintains a singleton translator instance.
    """
    global _global_translator
    if _global_translator is None or _global_translator.model_name != model_name:
        _global_translator = NLLBTranslator(model_name)
    
    return _global_translator.translate(text, src_lang, tgt_lang)

# --- EXAMPLE USAGE ---
def run_demo():
    print("Running Demo...")
    
    # Example 1: List of short sentences
    texts = [
        "Machine translation models are improving very quickly.",
        "This model supports more than 200 languages.",
        "Google Colab makes testing machine learning easy."
    ]
    
    # Use the function
    results = translate_text(texts)
    
    print("\nResults (Short Texts):")
    print("="*40)
    for original, translated in zip(texts, results):
        print(f"EN: {original}")
        print(f"AR: {translated}\n")

    # Example 2: Long text (to test chunking)
    long_text = (
        "Artificial intelligence is transforming the way we interact with technology. " * 10
    )
    print(f"Testing long text translation (Length: {len(long_text)} chars)...")
    long_result = translate_text(long_text)
    print(f"Translated length: {len(long_result)} chars.")
    print(f"Preview: {long_result[:100]}...")

if __name__ == "__main__":
    run_demo()
