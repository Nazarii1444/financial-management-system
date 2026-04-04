from fastapi.security import HTTPBearer
from fastapi import Security

bearer_scheme = HTTPBearer(bearerFormat="JWT", scheme_name="AccessToken")
