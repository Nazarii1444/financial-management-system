from pydantic import BaseModel


class TwoFASetupResponse(BaseModel):
    qr_code_base64: str
    secret: str


class TwoFAVerifyRequest(BaseModel):
    code: str
