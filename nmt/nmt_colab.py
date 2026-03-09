import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

def translate_nmt_colab(text, model, tokenizer, device, src_lang="eng_Latn", tgt_lang="arb_Arab", max_length=512):
    """
    Standalone version of the NMT translation function optimized for Google Colab/local use.
    
    Args:
        text: The source text to translate.
        model: Loaded NLLB model instance.
        tokenizer: Loaded NLLB tokenizer instance.
        device: 'cuda' or 'cpu'.
        src_lang: NLLB language code for source (e.g., 'eng_Latn').
        tgt_lang: NLLB language code for target (e.g., 'arb_Arab').
        max_length: Maximum token length for chunks.
    """
    if not text:
        return ""
    
    # Split input into lines and skip empty ones
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return text
        
    # Set the tokenizer source language
    tokenizer.src_lang = src_lang
    
    def run_inference_batch(texts):
        """Internal helper for batch model inference."""
        inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True).to(device)
        outputs = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_lang),
            max_length=max_length,
            num_beams=2,  # Faster CPU performance
            early_stopping=True
        )
        return tokenizer.batch_decode(outputs, skip_special_tokens=True)

    def translate_long_text(long_text):
        """Internal helper to split massive lines into smaller chunks for translation."""
        # Simple word-based chunking that respects token limits
        words = long_text.replace('\n', ' \n ').split(' ')
        chunks = []
        current_words = []
        
        for word in words:
            if not word: continue
            test_words = current_words + [word]
            test_str = " ".join(test_words).replace(' \n ', '\n')
            
            # Check token count for the potential chunk
            token_count = tokenizer(test_str, return_tensors="pt").input_ids.shape[1]
            
            if token_count > max_length - 10:  # Buffer for special tokens/BOS
                if current_words:
                    chunk_str = " ".join(current_words).replace(' \n ', '\n')
                    chunks.append(run_inference_batch([chunk_str])[0])
                    current_words = [word]
                else:
                    # Single word is too long (fallback)
                    chunks.append(run_inference_batch([word])[0])
                    current_words = []
            else:
                current_words = test_words
        
        if current_words:
            chunk_str = " ".join(current_words).replace(' \n ', '\n')
            chunks.append(run_inference_batch([chunk_str])[0])
            
        return " ".join(chunks)

    # Processing parameters
    batch_size = 4 
    all_translated_lines = []
    
    # Process lines in batches
    for i in range(0, len(lines), batch_size):
        batch_segment = lines[i:i + batch_size]
        
        # Prepare placeholders for this batch
        segment_results = [None] * len(batch_segment)
        batch_to_translate = []
        indices_to_translate = []
        
        for idx, line in enumerate(batch_segment):
            # Peak at token count to see if we need special chunking
            inputs = tokenizer(line, return_tensors="pt").to(device)
            if inputs.input_ids.shape[1] > max_length:
                # This line is too massive even for a single batch item, chunk it separately
                segment_results[idx] = translate_long_text(line)
            else:
                # Add to the standard batch for inference
                batch_to_translate.append(line)
                indices_to_translate.append(idx)
        
        # Run inference for the standard-length lines in this segment
        if batch_to_translate:
            batch_outputs = run_inference_batch(batch_to_translate)
            for idx, output in zip(indices_to_translate, batch_outputs):
                segment_results[idx] = output
        
        # Collect results
        all_translated_lines.extend(segment_results)
            
    return "\n".join(all_translated_lines)

# --- GOOGLE COLAB SETUP & USAGE EXAMPLE ---
if __name__ == "__main__":
    # 1. Install dependencies (Uncomment in Colab)
    # !pip install torch transformers sentencepiece

    MODEL_NAME = "facebook/nllb-200-distilled-600M"
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
    print(f"Loading model '{MODEL_NAME}' on {DEVICE}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME).to(DEVICE)
    
    input_text = """Hello, how are you?
This is a test of the Neural Machine Translation system.
Neural networks have revolutionized the way we translate languages by capturing context more effectively than traditional methods."""

    print("\nOriginal Text:")
    print(input_text)
    
    print("\nTranslating...")
    translated = translate_nmt_colab(input_text, model, tokenizer, DEVICE)
    
    print("\nTranslated Text (Arabic):")
    print(translated)
