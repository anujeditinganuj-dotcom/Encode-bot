# Developed by ARGON telegram: @REACTIVEARGON
# Re-export encode and related utilities for backward compatibility
from bot.func.encode import encode, resume_encoding_job, safe_download_media, active_encodings

__all__ = ["encode", "resume_encoding_job", "safe_download_media", "active_encodings"]
