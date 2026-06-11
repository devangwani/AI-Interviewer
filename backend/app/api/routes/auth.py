from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from pydantic import BaseModel

from app.api.deps import get_current_user, get_database
from app.models.user import UserCreate, UserResponse, UserInDB

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_response(doc: dict) -> UserResponse:
    return UserResponse(
        id=str(doc["_id"]),
        firebase_uid=doc["firebase_uid"],
        email=doc["email"],
        display_name=doc.get("display_name"),
        photo_url=doc.get("photo_url"),
        role=doc.get("role"),
        role_switch_count=doc.get("role_switch_count", 0),
        created_at=doc["created_at"],
    )


@router.post("/login", response_model=UserResponse)
async def login_or_register(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Called after the frontend completes Firebase sign-in. Upserts user record."""
    uid = current_user["uid"]
    existing = await db["users"].find_one({"firebase_uid": uid})

    if existing:
        return _to_response(existing)

    user_doc = UserInDB(
        firebase_uid=uid,
        email=current_user.get("email", ""),
        display_name=current_user.get("name"),
        photo_url=current_user.get("picture"),
    ).model_dump(by_alias=True, exclude={"id"})

    result = await db["users"].insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return _to_response(user_doc)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    uid = current_user["uid"]
    user = await db["users"].find_one({"firebase_uid": uid})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return _to_response(user)


class RoleBody(BaseModel):
    role: str   # "candidate" | "recruiter"


@router.patch("/me/role", response_model=UserResponse)
async def update_role(
    body: RoleBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Set the user's role for the first time (candidate or recruiter)."""
    if body.role not in ("candidate", "recruiter"):
        raise HTTPException(status_code=400, detail="Role must be 'candidate' or 'recruiter'.")
    uid = current_user["uid"]
    await db["users"].update_one(
        {"firebase_uid": uid},
        {"$set": {"role": body.role, "updated_at": datetime.utcnow()}},
    )
    user = await db["users"].find_one({"firebase_uid": uid})
    return _to_response(user)


@router.post("/me/switch-role", response_model=UserResponse)
async def switch_role(
    body: RoleBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Allow a user to switch from their current role to the other — exactly once.
    Initial role selection via PATCH /me/role does not consume this allowance.
    """
    if body.role not in ("candidate", "recruiter"):
        raise HTTPException(status_code=400, detail="Role must be 'candidate' or 'recruiter'.")

    uid  = current_user["uid"]
    user = await db["users"].find_one({"firebase_uid": uid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.get("role_switch_count", 0) >= 1:
        raise HTTPException(
            status_code=403,
            detail="Role switch limit reached. You may only switch roles once.",
        )
    if user.get("role") == body.role:
        raise HTTPException(status_code=400, detail="You are already in that role.")

    await db["users"].update_one(
        {"firebase_uid": uid},
        {"$set": {"role": body.role, "updated_at": datetime.utcnow()},
         "$inc": {"role_switch_count": 1}},
    )
    updated = await db["users"].find_one({"firebase_uid": uid})
    return _to_response(updated)


@router.get("/user-by-email", response_model=UserResponse)
async def get_user_by_email(
    email: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Recruiter looks up a candidate by email address to schedule an interview."""
    user = await db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="No user found with that email address.")
    return _to_response(user)
