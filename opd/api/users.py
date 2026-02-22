"""User registration and authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt
import re

from opd.db.models import User
from opd.db.session import get_session

router = APIRouter()


class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(..., min_length=3, max_length=20)
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """验证用户名格式"""
        if not re.match(r"^[a-zA-Z0-9_]{3,20}$", v):
            raise ValueError("用户名长度为 3-20 字符，仅支持字母、数字、下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """验证密码强度"""
        if len(v) < 8:
            raise ValueError("密码长度至少为 8 字符")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含小写字母")
        if not re.search(r"[0-9]", v):
            raise ValueError("密码必须包含数字")
        return v


class RegisterResponse(BaseModel):
    """用户注册响应"""

    id: int
    username: str
    email: str
    message: str


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
async def register_user(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    用户注册端点

    验证规则：
    - 用户名：3-20 字符，仅字母、数字、下划线
    - 邮箱：标准邮箱格式
    - 密码：至少 8 字符，包含大写字母、小写字母、数字
    """
    # 检查用户名是否已存在
    stmt = select(User).where(User.username == request.username)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被注册",
        )

    # 检查邮箱是否已存在
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    existing_email = result.scalar_one_or_none()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册",
        )

    # 密码加密
    password_bytes = request.password.encode("utf-8")
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    # 创建用户
    new_user = User(
        username=request.username,
        email=request.email,
        password_hash=password_hash,
    )

    db.add(new_user)
    await db.flush()  # 刷新以获取 ID，但不提交事务

    # 保存用户信息用于响应
    user_id = new_user.id
    username = new_user.username
    email = new_user.email

    return RegisterResponse(
        id=user_id,
        username=username,
        email=email,
        message="注册成功",
    )
