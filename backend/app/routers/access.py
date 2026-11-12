"""Log in with the site's access key, check whether you are in, log out."""
import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.services import access

router = APIRouter(prefix="/api", tags=["access"])

ONE_YEAR = 365 * 24 * 3600


class LoginIn(BaseModel):
    key: str


@router.get("/session")
async def session(request: Request) -> dict:
    return {"required": access.required(), "ok": access.authorised(request)}


@router.post("/login", status_code=204)
async def login(body: LoginIn, request: Request, response: Response):
    if access.required() and not access.key_matches(body.key.strip()):
        await asyncio.sleep(1)   # slows down guessing
        raise HTTPException(401, "Wrong access key")
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(access.COOKIE, access.token(), max_age=ONE_YEAR, httponly=True,
                        samesite="lax", secure=secure, path="/")


@router.post("/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie(access.COOKIE, path="/")
