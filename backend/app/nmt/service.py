import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .model import NLLBTranslatorWrapper

# Initialize the translator once at the module level to avoid reloading for every request
translator = NLLBTranslatorWrapper()

class TranslationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def translate_stt_result(self, stt_data: dict, target_lang: str, source_lang: Optional[str] = None):
        """Translates STT results without batching or chunking."""
        return await asyncio.to_thread(
            translator.translate_stt_result,
            stt_data,
            src_lang=source_lang,
            tgt_lang=target_lang
        )
