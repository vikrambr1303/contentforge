from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from models.content import ContentItem
from models.platform_account import PlatformAccount
from models.post_history import PostHistory
from plugins.registry import get_plugin, list_plugins, load_plugins
from schemas.platform import AccountCreate, PlatformAccountOut, PostHistoryOut, PostRequest
from tasks.post_content import post_to_platform
from utils.crypto import encrypt_credentials

router = APIRouter(tags=["platforms"])


@router.get("/platforms")
def platforms_list() -> list[dict]:
    load_plugins()
    out = []
    for p in list_plugins():
        out.append(
            {
                "name": p.name,
                "display_name": p.display_name,
                "supported_content_types": p.supported_content_types,
                "credentials_schema": p.credentials_schema(),
            }
        )
    return out


@router.get("/accounts", response_model=list[PlatformAccountOut])
def accounts_list(db: Session = Depends(get_db)) -> list[PlatformAccount]:
    q = select(PlatformAccount).order_by(PlatformAccount.id.desc())
    return list(db.scalars(q).all())


@router.post("/accounts", response_model=PlatformAccountOut)
def accounts_create(body: AccountCreate, db: Session = Depends(get_db)) -> PlatformAccount:
    load_plugins()
    try:
        plugin = get_plugin(body.platform)
    except KeyError as e:
        raise HTTPException(400, "Unknown platform") from e
    if not plugin.validate_credentials(body.credentials):
        raise HTTPException(400, "Credential validation failed")
    row = PlatformAccount(
        platform=body.platform,
        display_name=body.display_name,
        credentials_encrypted=encrypt_credentials(body.credentials),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/accounts/{account_id}", status_code=204)
def accounts_delete(account_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(PlatformAccount, account_id)
    if not row:
        raise HTTPException(404)
    db.delete(row)
    db.commit()


@router.post("/post")
def post(body: PostRequest, db: Session = Depends(get_db)) -> dict:
    load_plugins()
    if not db.get(ContentItem, body.content_item_id):
        raise HTTPException(404, "Content not found")
    if not db.get(PlatformAccount, body.account_id):
        raise HTTPException(404, "Account not found")
    async_result = post_to_platform.delay(body.content_item_id, body.account_id)
    result = async_result.get(timeout=600)
    return result


@router.get("/post-history", response_model=list[PostHistoryOut])
def post_history(
    account_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[PostHistory]:
    q = select(PostHistory).order_by(PostHistory.id.desc())
    if account_id is not None:
        q = q.where(PostHistory.platform_account_id == account_id)
    if status:
        q = q.where(PostHistory.status == status)
    return list(db.scalars(q).all())
