import os
import torch
import sys
from datasets import load_dataset, concatenate_datasets
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments
)
import sacrebleu

# --- CONFIGURATION ---
# The notebook mentions a finetuned model, but if it's not available, we use the base model.
BASE_MODEL = "facebook/nllb-200-distilled-600M"
GDRIVE_LINK = "https://drive.google.com/drive/folders/1OgyH-YCKFNSVPvD41_Uf2GCG_-nEI5yw?usp=sharing"
MODEL_DIR = "nllb-edu-en-ar-finetuned-v3"
DEVICE = "cpu" # Default fallback

def get_device():
    if torch.cuda.is_available():
        major, minor = torch.cuda.get_device_capability()
        gpu_arch = f"sm_{major}{minor}"
        if gpu_arch in torch.cuda.get_arch_list():
            return "cuda"
        else:
            print(f"Warning: GPU {gpu_arch} not supported by this Torch build. Falling back to CPU.")
    return "cpu"

def download_model():
    """Attempts to download the model from Google Drive."""
    # Temporarily disabled to avoid hanging on inaccessible link
    # if not os.path.exists(MODEL_DIR):
    #     print(f"Downloading model from Google Drive to {MODEL_DIR}...")
    #     cmd = f'{sys.executable} -m gdown --folder 1OgyH-YCKFNSVPvD41_Uf2GCG_-nEI5yw -O {MODEL_DIR}'
    #     status = os.system(cmd)
    #     if status != 0:
    #         print("Warning: Google Drive download failed or link inaccessible. Falling back to base model.")
    #         return False
    #     return True
    return os.path.exists(MODEL_DIR)

def prepare_data(tokenizer, sample_size=1000):
    """Loads and prepares UNPC and Tatoeba datasets as per the notebook."""
    print(f"Preparing datasets (using {sample_size} samples for demo)...")
    
    # UNPC Dataset
    print("Loading UNPC...")
    unpc = load_dataset("Helsinki-NLP/un_pc", "ar-en", split="train")
    unpc = unpc.shuffle(seed=42).select(range(min(sample_size, len(unpc))))
    
    def flip_unpc(example):
        return {
            "source": example["translation"]["en"],
            "target": example["translation"]["ar"]
        }
    unpc = unpc.map(flip_unpc, remove_columns=unpc.column_names)

    # Tatoeba Dataset
    print("Loading Tatoeba...")
    tatoeba = load_dataset("ymoslem/Tatoeba-EN-AR", split="train")
    tatoeba = tatoeba.shuffle(seed=42).select(range(min(sample_size, len(tatoeba))))
    
    def clean_tatoeba(example):
        return {
            "source": example["English"],
            "target": example["Arabic"]
        }
    tatoeba = tatoeba.map(clean_tatoeba, remove_columns=tatoeba.column_names)

    # Combine and Tokenize
    dataset = concatenate_datasets([unpc, tatoeba]).shuffle(seed=42)
    
    def tokenize_fn(batch):
        return tokenizer(
            batch["source"],
            text_target=batch["target"],
            max_length=128,
            truncation=True,
            padding="max_length"
        )
    
    print("Tokenizing...")
    tokenized_dataset = dataset.map(tokenize_fn, batched=True, remove_columns=dataset.column_names)
    return tokenized_dataset

def translate(text, tokenizer, model):
    """Single sentence translation."""
    tgt_lang = "arb_Arab"
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    outputs = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_lang),
        max_length=128
    )
    
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def main():
    has_custom_model = download_model()
    model_path = os.path.abspath(MODEL_DIR) if has_custom_model else BASE_MODEL
    
    device = get_device()
    print(f"Loading model from: {model_path} on {device}")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(device)
    
    print("\n--- Example Translations ---")
    test_sentences = [
        "Welcome to the world of machine translation.",
        "Education is a powerful tool for change.",
        "Artificial intelligence is transforming our lives.",
        "i'm try to test nmt model locally.",

    ]
    
    for s in test_sentences:
        res = translate(s, tokenizer, model)
        print(f"EN: {s}")
        print(f"AR: {res}")
        print("-" * 20)

    # If the user wants to run evaluation/training, they can add flags or code here.
    # For now, this script provides the inference logic from the notebook.

if __name__ == "__main__":
    main()
