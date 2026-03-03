from typing import Optional
from pydantic import BaseModel

class STTData(BaseModel):
    # Depending on what stt_data looks like, we could define it more strictly.
    # But for now, since router uses dict, we can leave it or define a basic one.
    pass
