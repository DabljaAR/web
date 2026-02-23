import torch
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM

def main():
    model_name = "facebook/nllb-200-distilled-600M"
    print(f"Loading model {model_name}...")
    
    # Check for GPU and architectural compatibility
    device_str = "cpu"
    if torch.cuda.is_available():
        # Get GPU capability (e.g., 6.1 for 1080 Ti)
        major, minor = torch.cuda.get_device_capability()
        gpu_arch = f"sm_{major}{minor}"
        
        # Check if this architecture is included in the current torch build
        supported_archs = torch.cuda.get_arch_list()
        
        if gpu_arch in supported_archs:
            device_str = "cuda:0"
            print(f"GPU detected ({torch.cuda.get_device_name()})! Using CUDA.")
        else:
            print(f"Warning: Your GPU ({torch.cuda.get_device_name()}) has architecture {gpu_arch}, "
                  f"which is not supported by this PyTorch installation.")
            print("Falling back to CPU. To use your GPU, reinstall PyTorch with a compatible version.")
    else:
        print("No GPU detected. Using CPU.")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(device_str)

    sentences = [
        "Machine translation models are improving very quickly.",
        "This model supports more than 200 languages.",
        "The weather today is sunny with a slight chance of rain.",
        "Artificial intelligence is transforming the world rapidly."
    ]

    print("\nTarget language: Arabic (arb_Arab)")
    print("-" * 30)

    for sentence in sentences:
        print(f"Input : {sentence}")
        
        inputs = tokenizer(sentence, return_tensors="pt").to(model.device)
        
        # NLLB requires forced_bos_token_id for target language
        # For Arabic, it's 'arb_Arab'
        # tokenizer.lang_code_to_id['arb_Arab']
        
        outputs = model.generate(
            **inputs, 
            forced_bos_token_id=tokenizer.convert_tokens_to_ids("arb_Arab"),
            max_length=500
        )
        
        translation = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print(f"Output: {translation}")
        print("-" * 30)

if __name__ == "__main__":
    main()
