import os
import sys
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

def run_translation():
    # --- CONFIGURATION ---
    FINETUNED_NAME = "nllb-edu-en-ar-finetuned-v3"
    GDRIVE_LINK = "https://drive.google.com/drive/folders/1OgyH-YCKFNSVPvD41_Uf2GCG_-nEI5yw?usp=sharing"
    
    # Check if finetuned model exists, if not, try to download
    model_path = FINETUNED_NAME
    if not os.path.exists(FINETUNED_NAME):
        print(f"Finetuned model not found at '{FINETUNED_NAME}'.")
        print("Attempting to download from Google Drive...")
        # Note: --folder is used for drive folder links
        cmd = f'"{sys.executable}" -m gdown --folder "{GDRIVE_LINK}" -O "{FINETUNED_NAME}"'
        status = os.system(cmd)
        if status != 0:
            print("Download failed or Google Drive link is inaccessible.")
            print("Please ensure you have access to the model folder.")
            return
        else:
            print("Download successful!")
    
    print(f"Initializing translation using FINETUNED model from '{model_path}'...")
    
    # --- START CUDA FIX ---
    device = "cpu"
    if torch.cuda.is_available():
        major, minor = torch.cuda.get_device_capability()
        gpu_arch = f"sm_{major}{minor}"
        if gpu_arch in torch.cuda.get_arch_list():
            device = "cuda:0"
        else:
            print(f"Warning: GPU {gpu_arch} not supported by this Torch build. Using CPU.")
    # --- END CUDA FIX ---

    print(f"Using device: {device}")

    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(device)

    # an example of how the input and the output will be and the pipeline
    text = [
        "Machine translation models are improving very quickly.",
        "This model supports more than 200 languages.",
        "Google Colab makes testing machine learning easy."
    ]
    src_lang = "eng_Latn"
    tgt_lang = "arb_Arab"

    print("\nTranslating...")
    
    # helper function to mimic the pipeline behavior
    def NMT(texts):
        if isinstance(texts, str):
            texts = [texts]
        
        out = []
        for sentence in texts:
            inputs = tokenizer(sentence, return_tensors="pt").to(device)
            outputs = model.generate(
                **inputs,
                forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_lang),
                max_length=500
            )
            translation = tokenizer.decode(outputs[0], skip_special_tokens=True)
            out.append({'translation_text': translation})
        return out

    translatedScript = NMT(text)

    print("\nResults (Finetuned):")
    print("="*40)
    for i, j in zip(text, translatedScript):
        print(i)
        print(j['translation_text'])
        print()

if __name__ == "__main__":
    run_translation()
