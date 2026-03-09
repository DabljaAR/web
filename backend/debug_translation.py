
import logging
import sys
import os

# Add the current directory to sys.path to import app
sys.path.append(os.getcwd())

from app.nmt.service import NLLBTranslatorWrapper

logging.basicConfig(level=logging.INFO)

def test_paragraph():
    translator = NLLBTranslatorWrapper()
    
    para = "This article explores the many dimensions of this transformation. We will examine the rise of AI-assisted coding and what it means for the role of human developers. We will look at quantum computing and its potential to unlock solutions to problems currently considered intractable. We will consider the growing importance of low-code and no-code platforms and their role in democratizing software creation. We will explore new programming paradigms, the evolution of programming languages, the transformation of software development workflows, cybersecurity challenges, the ethics of automated code generation, and the long-term vision of what programming might look like at the end of the twenty-first century."
    
    print(f"--- Testing Paragraph ---")
    print(f"Input: {para}")
    
    result = translator.translate(para, tgt_lang="arb_Arab")
    
    print(f"Output: {result}")
    
    if result.strip() == para.strip():
        print("FAIL: Model returned original input!")
    else:
        print("SUCCESS: Model produced some translation.")

if __name__ == "__main__":
    test_paragraph()
